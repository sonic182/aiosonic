import asyncio
from typing import TYPE_CHECKING, Optional

import h2.events

from aiosonic.exceptions import ConnectionDisconnected, MissingEvent
from aiosonic.types import ParsedBodyType
from aiosonic.utils import get_debug_logger

dlogger = get_debug_logger()

IGNORED_EVENTS = tuple(
    evt
    for evt in (
        getattr(h2.events, "PriorityUpdated", None),
        getattr(h2.events, "UnknownFrameReceived", None),
        getattr(h2.events, "AlternativeServiceAvailable", None),
        getattr(h2.events, "PushPromiseReceived", None),
        getattr(h2.events, "PushedStreamReset", None),
        getattr(h2.events, "PushedStreamClosed", None),
    )
    if evt is not None
)

DISCONNECT_EVENTS = tuple(
    evt
    for evt in (
        getattr(h2.events, "GoAwayReceived", None),
        getattr(h2.events, "ConnectionTerminated", None),
    )
    if evt is not None
)

if TYPE_CHECKING:
    import aiosonic
    from aiosonic.connection import Connection


class Http2Handler(object):
    """HTTP/2 handler attached to a Connection.

    This class is protocol-like: it consumes bytes read from the underlying
    StreamReader, feeds them to the h2 connection and handles events.
    It uses loop-bound futures and events to coordinate flow-control and
    stream lifetime.
    """

    def __init__(self, connection: "Connection"):
        assert connection
        self.connection = connection
        h2conn = connection.h2conn
        assert h2conn

        self.loop = asyncio.get_event_loop()
        h2conn.initiate_connection()

        self.requests = {}

        self._window_updated = asyncio.Event()

        self.writer.write(h2conn.data_to_send())
        try:
            self.loop.create_task(self.writer.drain())
        except Exception:
            pass

        self.reader_task = self.loop.create_task(self.reader_t())

    @property
    def writer(self):
        # prefer explicitly set writer (tests/mocks), fallback to connection
        w = getattr(self, "_writer", None)
        if w is not None:
            return w
        assert self.connection.writer
        return self.connection.writer

    @writer.setter
    def writer(self, value):
        self._writer = value

    @property
    def reader(self):
        # prefer explicitly set reader (tests/mocks), fallback to connection
        r = getattr(self, "_reader", None)
        if r is not None:
            return r
        assert self.connection.reader
        return self.connection.reader

    @reader.setter
    def reader(self, value):
        self._reader = value

    @property
    def h2conn(self):
        # prefer explicitly set h2conn (tests/mocks), fallback to connection
        h = getattr(self, "_h2conn", None)
        if h is not None:
            return h
        assert self.connection.h2conn
        return self.connection.h2conn

    @h2conn.setter
    def h2conn(self, value):
        self._h2conn = value

    async def request(
        self, headers: "aiosonic.HeadersType", body: Optional[ParsedBodyType]
    ):
        from aiosonic import HttpResponse

        if body is None:
            normalized_body = b""
        elif isinstance(body, bytes):
            normalized_body = body
        elif isinstance(body, bytearray):
            normalized_body = bytes(body)
        elif isinstance(body, memoryview):
            normalized_body = body.tobytes()
        else:
            raise ValueError("HTTP/2 requests currently require a bytes-like body")

        stream_id = self.h2conn.get_next_available_stream_id()
        headers_param = headers.items() if isinstance(headers, dict) else headers

        future = self.loop.create_future()
        self.requests[stream_id] = {
            "request_body": normalized_body,
            "response_body": bytearray(),
            "headers": headers_param,
            "future": future,
            "data_sent": False,
            "send_scheduled": False,
            "send_started": False,
        }

        # schedule sending immediately to avoid stalls when settings already negotiated
        try:
            # mark scheduled to avoid duplicate scheduling from SettingsAcknowledged
            self.requests[stream_id]["send_scheduled"] = True
            self.loop.create_task(self.send_body(stream_id))
        except Exception:
            # ensure flag is cleared on failure
            try:
                self.requests[stream_id]["send_scheduled"] = False
            except Exception:
                pass

        try:
            await future
        except Exception:
            try:
                del self.requests[stream_id]
            except KeyError:
                pass
            raise

        res = self.requests.pop(stream_id, {})

        response = HttpResponse()
        for key, val in res.get("headers", []):
            k = key.decode() if isinstance(key, (bytes, bytearray)) else key
            v = val.decode() if isinstance(val, (bytes, bytearray)) else val
            if k == ":status":
                response.response_initial = {"version": "2", "code": v}
            else:
                response._set_header(k, v)

        response_body = res.get("response_body")
        if response_body:
            response._set_body(bytes(response_body))

        return response

    async def reader_t(self):
        """Reader task."""
        if not hasattr(self, "loop"):
            self.loop = asyncio.get_event_loop()
        if not hasattr(self, "_window_updated"):
            self._window_updated = asyncio.Event()
        if not hasattr(self, "requests"):
            self.requests = {}
        read_size = 16 * 1024

        while True:
            try:
                data = await self.reader.read(read_size)
            except asyncio.CancelledError:
                break

            if not data:
                self._fail_all_pending(ConnectionDisconnected())
                break

            try:
                events = self.h2conn.receive_data(data)
            except Exception:
                dlogger.debug("h2 receive_data failed", exc_info=True)
                self._fail_all_pending(ConnectionDisconnected())
                break

            if events:
                dlogger.debug(("received events", events))
                try:
                    await self.handle_events(events)
                except Exception:
                    dlogger.debug("--- Some Exception!", exc_info=True)
                    raise
                else:
                    await self.check_to_write()

    async def handle_events(self, events):
        """Handle http2 events."""
        if not hasattr(self, "requests"):
            self.requests = {}
        h2conn = self.h2conn

        for event in events:
            try:
                sid = getattr(event, "stream_id", None)
            except Exception:
                sid = None

            if isinstance(event, h2.events.StreamEnded):
                dlogger.debug(f"--- exit stream, id: {event.stream_id}")
                req = self.requests.get(event.stream_id)
                if req and not req["future"].done():
                    req["future"].set_result(bytes(req["response_body"]))
            elif isinstance(event, h2.events.DataReceived):
                req = self.requests.get(event.stream_id)
                if not req:
                    dlogger.debug("data for unknown stream %s", event.stream_id)
                    continue
                req["response_body"].extend(event.data)

                if (
                    event.stream_id in h2conn.streams
                    and not h2conn.streams[event.stream_id].closed
                    and event.flow_controlled_length
                ):
                    h2conn.increment_flow_control_window(
                        event.flow_controlled_length, event.stream_id
                    )
                dlogger.info(f"Flow increment: {event.flow_controlled_length}")
                if event.flow_controlled_length:
                    h2conn.increment_flow_control_window(event.flow_controlled_length)
            elif isinstance(event, h2.events.ResponseReceived):
                req = self.requests.get(event.stream_id)
                if not req:
                    dlogger.debug("response for unknown stream %s", event.stream_id)
                    continue
                req["headers"] = event.headers
                # If the stream is already closed (server sent headers with END_STREAM),
                # complete the future so requests don't hang waiting for StreamEnded.
                try:
                    stream_obj = h2conn.streams.get(event.stream_id)
                except Exception:
                    stream_obj = None
                if (not stream_obj) or getattr(stream_obj, "closed", False):
                    if not req["future"].done():
                        req["future"].set_result(bytes(req.get("response_body", bytearray())))
            elif isinstance(event, h2.events.SettingsAcknowledged):
                # After settings ack we may be allowed to send body data
                for stream_id, req in list(self.requests.items()):
                    if not req["data_sent"] and not req["send_scheduled"]:
                        req["send_scheduled"] = True
                        try:
                            self.loop.create_task(self.send_body(stream_id))
                        except Exception:
                            req["send_scheduled"] = False
            elif isinstance(event, h2.events.WindowUpdated):
                # notify senders waiting for window updates (don't clear here;
                # waiters will clear after waking)
                self._window_updated.set()
            elif isinstance(event, h2.events.StreamReset):
                exc = ConnectionDisconnected()
                req = self.requests.get(event.stream_id)
                if req and not req["future"].done():
                    req["future"].set_exception(exc)
            elif isinstance(event, DISCONNECT_EVENTS):
                self._fail_all_pending(ConnectionDisconnected())
            elif isinstance(event, h2.events.TrailersReceived):
                req = self.requests.get(event.stream_id)
                if req:
                    try:
                        req["headers"] = list(req.get("headers", [])) + list(event.headers)
                    except Exception:
                        pass
            elif isinstance(event, IGNORED_EVENTS):
                dlogger.debug("ignoring http2 event %s", event.__class__.__name__)
            elif isinstance(
                event,
                (
                    h2.events.PingReceived,
                    h2.events.RemoteSettingsChanged,
                ),
            ):
                pass
            else:
                raise MissingEvent(f"another event {event.__class__.__name__}")

    async def check_to_write(self):
        """Writer task."""
        h2conn = self.h2conn
        data_to_send = h2conn.data_to_send()

        if data_to_send:
            dlogger.debug(("writing data", data_to_send))
            self.writer.write(data_to_send)
            try:
                await self.writer.drain()
            except Exception:
                pass

    async def send_body(self, stream_id):
        if not hasattr(self, "_window_updated"):
            self._window_updated = asyncio.Event()
        if not hasattr(self, "requests"):
            self.requests = {}
        def chunks(lst, n):
            for i in range(0, len(lst), n):
                yield lst[i : i + n]

        request = self.requests.get(stream_id)
        if not request:
            dlogger.debug("send_body called for unknown stream %s", stream_id)
            return

        request.setdefault("send_started", False)
        request.setdefault("send_scheduled", False)
        request.setdefault("data_sent", False)
        if request["send_started"]:
            return
        request["send_started"] = True

        body_bytes = request.get("request_body")
        if body_bytes is None and "body" in request:
            body_bytes = request["body"]
            if isinstance(body_bytes, bytearray):
                body_bytes = bytes(body_bytes)
            elif isinstance(body_bytes, memoryview):
                body_bytes = body_bytes.tobytes()
            elif not isinstance(body_bytes, (bytes, type(None))):
                body_bytes = b""
        headers = request["headers"]

        end_stream = False if body_bytes else True
        # send headers (end_stream if no body)
        self.h2conn.send_headers(stream_id, headers, end_stream=end_stream)
        await self.check_to_write()

        if not body_bytes:
            request["data_sent"] = True
            request["request_body"] = None
            request["send_scheduled"] = False
            return

        remaining = len(body_bytes)
        offset = 0
        while remaining > 0:
            to_split = self.h2conn.local_flow_control_window(stream_id)
            if not to_split or to_split <= 0:
                try:
                    self._window_updated.clear()
                except Exception:
                    pass
                coro = self._window_updated.wait()
                try:
                    await asyncio.wait_for(coro, timeout=5)
                except Exception:
                    try:
                        coro.close()
                    except Exception:
                        pass
                    to_split = getattr(self.h2conn, "max_outbound_frame_size", 65535)
                else:
                    to_split = self.h2conn.local_flow_control_window(stream_id)
                    try:
                        self._window_updated.clear()
                    except Exception:
                        pass

            if not to_split or to_split <= 0:
                to_split = getattr(self.h2conn, "max_outbound_frame_size", 65535)

            for chunk in chunks(body_bytes[offset : offset + remaining], to_split):
                last = (offset + len(chunk)) >= len(body_bytes)
                self.h2conn.send_data(stream_id, chunk, end_stream=last)
                offset += len(chunk)
                remaining -= len(chunk)
                # ensure bytes are flushed
                await self.check_to_write()

        request["data_sent"] = True
        if "request_body" in request:
            request["request_body"] = None
        request["send_scheduled"] = False

    def cleanup(self):
        """Cancel and schedule waiting for the reader task to finish."""
        try:
            self.reader_task.cancel()
        except Exception:
            pass
        # schedule a background task to await the cancelled task
        try:
            self.loop.create_task(self._wait_reader_cancel())
        except Exception:
            pass

    async def _wait_reader_cancel(self):
        try:
            await self.reader_task
        except asyncio.CancelledError:
            pass

    def _fail_all_pending(self, exc: Exception):
        reqs = getattr(self, "requests", {}) or {}
        for stream_id, req in list(reqs.items()):
            future = req.get("future")
            if future and not future.done():
                future.set_exception(exc)
