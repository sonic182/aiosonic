import asyncio
from typing import TYPE_CHECKING, Optional

import h2.events

from aiosonic.exceptions import MissingEvent
from aiosonic.types import ParsedBodyType
from aiosonic.utils import get_debug_logger

dlogger = get_debug_logger()

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

        body = body or b""

        stream_id = self.h2conn.get_next_available_stream_id()
        headers_param = headers.items() if isinstance(headers, dict) else headers

        future = self.loop.create_future()
        self.requests[stream_id] = {
            "body": body,
            "headers": headers_param,
            "future": future,
            "data_sent": False,
        }

        # schedule sending immediately to avoid stalls when settings already negotiated
        try:
            self.loop.create_task(self.send_body(stream_id))
        except Exception:
            pass

        await future

        res = self.requests.get(stream_id, {}).copy()
        # cleanup stored request
        try:
            del self.requests[stream_id]
        except KeyError:
            pass

        response = HttpResponse()
        for key, val in res.get("headers", []):
            k = key.decode() if isinstance(key, (bytes, bytearray)) else key
            v = val.decode() if isinstance(val, (bytes, bytearray)) else val
            if k == ":status":
                response.response_initial = {"version": "2", "code": v}
            else:
                response._set_header(k, v)

        if res.get("body"):
            response._set_body(res["body"])

        return response

    async def reader_t(self):
        """Reader task."""
        read_size = 16 * 1024

        while True:
            try:
                data = await self.reader.read(read_size)
            except asyncio.CancelledError:
                break

            if not data:
                break

            try:
                events = self.h2conn.receive_data(data)
            except Exception:
                dlogger.debug("h2 receive_data failed", exc_info=True)
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
                    req["future"].set_result(req["body"])
            elif isinstance(event, h2.events.DataReceived):
                req = self.requests.get(event.stream_id)
                if not req:
                    dlogger.debug("data for unknown stream %s", event.stream_id)
                    continue
                req["body"] += event.data

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
            elif isinstance(event, h2.events.SettingsAcknowledged):
                # After settings ack we may be allowed to send body data
                for stream_id, req in list(self.requests.items()):
                    if not req["data_sent"]:
                        await self.send_body(stream_id)
            elif isinstance(event, h2.events.WindowUpdated):
                # notify senders waiting for window updates (don't clear here;
                # waiters will clear after waking)
                self._window_updated.set()
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
        def chunks(lst, n):
            for i in range(0, len(lst), n):
                yield lst[i : i + n]

        request = self.requests.get(stream_id)
        if not request:
            dlogger.debug("send_body called for unknown stream %s", stream_id)
            return

        body = request["body"] or b""
        headers = request["headers"]

        end_stream = False if body else True
        # send headers (end_stream if no body)
        self.h2conn.send_headers(stream_id, headers, end_stream=end_stream)

        if not body:
            request["data_sent"] = True
            return

        remaining = len(body)
        offset = 0
        while remaining > 0:
            to_split = self.h2conn.local_flow_control_window(stream_id)
            if not to_split or to_split <= 0:
                try:
                    await asyncio.wait_for(self._window_updated.wait(), timeout=5)
                except Exception:
                    to_split = getattr(self.h2conn, "max_outbound_frame_size", 65535)
                else:
                    to_split = self.h2conn.local_flow_control_window(stream_id)
                    try:
                        self._window_updated.clear()
                    except Exception:
                        pass

            if not to_split or to_split <= 0:
                to_split = getattr(self.h2conn, "max_outbound_frame_size", 65535)

            for chunk in chunks(body[offset : offset + remaining], to_split):
                last = (offset + len(chunk)) >= len(body)
                self.h2conn.send_data(stream_id, chunk, end_stream=last)
                offset += len(chunk)
                remaining -= len(chunk)
                # ensure bytes are flushed
                await self.check_to_write()

        request["data_sent"] = True

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
