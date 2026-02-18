import asyncio
from typing import TYPE_CHECKING, AsyncIterator, Dict, Iterator, List, Optional, Union

import h2.events
import h2.settings

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


def _normalize_body(body: Optional[ParsedBodyType]) -> Union[bytes, AsyncIterator[bytes], Iterator[bytes]]:
    if body is None:
        return b""
    if isinstance(body, (bytes, bytearray, memoryview)):
        return bytes(body) if not isinstance(body, bytes) else body
    if isinstance(body, (AsyncIterator, Iterator)):
        return body
    raise ValueError("HTTP/2 body must be bytes-like or an (async) iterator")


def _resolve_body(request: dict) -> Union[bytes, AsyncIterator[bytes], Iterator[bytes]]:
    body = request.get("request_body")
    if body is None:
        body = request.get("body")
    if body is None:
        return b""
    if isinstance(body, (bytes, bytearray, memoryview)):
        return bytes(body) if not isinstance(body, bytes) else body
    if isinstance(body, (AsyncIterator, Iterator)):
        return body
    return b""


def _build_response(res: dict, queue, sem_release, flow_cb) -> "aiosonic.HttpResponse":
    from aiosonic import HttpResponse

    response = HttpResponse()
    for key, val in res.get("headers", []):
        k = key.decode() if isinstance(key, (bytes, bytearray)) else key
        v = val.decode() if isinstance(val, (bytes, bytearray)) else val
        if k == ":status":
            response.response_initial = {"version": "2", "code": v}
        else:
            response._set_header(k, v)

    response._set_h2_queue(queue, sem_release, flow_cb)
    return response


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

        self.requests: Dict[int, dict] = {}

        self._window_updated = asyncio.Event()
        self._max_streams = 100
        self._stream_sem = asyncio.Semaphore(self._max_streams)
        self._closing = False

        self.writer.write(h2conn.data_to_send())
        try:
            self.loop.create_task(self.writer.drain())
        except Exception:
            pass

        self.reader_task = self.loop.create_task(self.reader_t())

    @property
    def writer(self):
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
        h = getattr(self, "_h2conn", None)
        if h is not None:
            return h
        assert self.connection.h2conn
        return self.connection.h2conn

    @h2conn.setter
    def h2conn(self, value):
        self._h2conn = value

    def _register_stream(self, stream_id: int, headers, body: Union[bytes, AsyncIterator, Iterator]) -> asyncio.Future:
        headers_future = self.loop.create_future()
        chunk_queue: asyncio.Queue = asyncio.Queue()
        self.requests[stream_id] = {
            "request_body": body,
            "headers": headers,
            "future": headers_future,
            "chunk_queue": chunk_queue,
            "data_sent": False,
            "send_scheduled": True,
            "send_started": False,
        }
        return headers_future

    def _deregister_stream(self, stream_id: int) -> dict:
        return self.requests.pop(stream_id, {})

    async def request(self, headers: "aiosonic.HeadersType", body: Optional[ParsedBodyType]):
        if getattr(self, "_closing", False):
            raise ConnectionDisconnected()

        if not hasattr(self, "_stream_sem"):
            self._stream_sem = asyncio.Semaphore(getattr(self, "_max_streams", 100))

        normalized_body = _normalize_body(body)
        headers_param = headers.items() if isinstance(headers, dict) else headers

        await self._stream_sem.acquire()
        stream_id = self.h2conn.get_next_available_stream_id()
        headers_future = self._register_stream(stream_id, headers_param, normalized_body)

        try:
            await self._send_stream(stream_id)
        except Exception:
            try:
                self.requests[stream_id]["send_scheduled"] = False
            except Exception:
                pass

        try:
            await headers_future
        except Exception:
            self.requests.pop(stream_id, None)
            self._stream_sem.release()
            raise

        req = self.requests.get(stream_id, {})
        chunk_queue = req.get("chunk_queue", asyncio.Queue())
        sem_release = self._make_sem_release(stream_id)
        flow_cb = self._make_flow_cb(stream_id)
        return _build_response(req, chunk_queue, sem_release, flow_cb)

    def _make_sem_release(self, stream_id: int):
        def release():
            self._stream_sem.release()
            self.requests.pop(stream_id, None)

        return release

    def _make_flow_cb(self, stream_id: int):
        def flow_cb(length: int):
            try:
                h2conn = self.h2conn
                h2conn.increment_flow_control_window(length, stream_id)
                h2conn.increment_flow_control_window(length)
                self.loop.create_task(self.check_to_write())
            except Exception:
                pass

        return flow_cb

    async def _send_stream(self, stream_id: int) -> None:
        request = self.requests.get(stream_id)
        if not request:
            dlogger.debug("_send_stream called for unknown stream %s", stream_id)
            return

        request.setdefault("send_started", False)
        request.setdefault("send_scheduled", False)
        request.setdefault("data_sent", False)
        if request["send_started"]:
            return
        request["send_started"] = True

        body = _resolve_body(request)
        headers = request["headers"]
        has_body = bool(body) if isinstance(body, bytes) else True

        await self._send_headers(stream_id, headers, end_stream=not has_body)

        if not has_body:
            request["data_sent"] = True
            request["request_body"] = None
            request["send_scheduled"] = False
            return

        await self._send_data(stream_id, body)

        request["data_sent"] = True
        request["request_body"] = None
        request["send_scheduled"] = False

    async def _send_headers(self, stream_id: int, headers, end_stream: bool) -> None:
        self.h2conn.send_headers(stream_id, headers, end_stream=end_stream)
        await self.check_to_write()

    async def _send_data(self, stream_id: int, body: Union[bytes, AsyncIterator[bytes], Iterator[bytes]]) -> None:
        if isinstance(body, bytes):
            await self._send_bytes(stream_id, body)
        elif isinstance(body, AsyncIterator):
            await self._send_async_iter(stream_id, body)
        else:
            await self._send_sync_iter(stream_id, body)

    async def _send_bytes(self, stream_id: int, body_bytes: bytes) -> None:
        max_frame = getattr(self.h2conn, "max_outbound_frame_size", 65535)
        remaining = len(body_bytes)
        offset = 0

        while remaining > 0:
            await self._wait_for_window(stream_id)

            win = self.h2conn.local_flow_control_window(stream_id)
            to_send = min(win, max_frame, remaining)
            chunk = body_bytes[offset : offset + to_send]
            last = (offset + to_send) >= len(body_bytes)

            self.h2conn.send_data(stream_id, chunk, end_stream=last)
            offset += to_send
            remaining -= to_send
            await self.check_to_write()

    async def _send_async_iter(self, stream_id: int, body: AsyncIterator[bytes]) -> None:
        chunks = []
        async for chunk in body:
            if chunk:
                chunks.append(chunk if isinstance(chunk, bytes) else bytes(chunk))
        await self._send_bytes(stream_id, b"".join(chunks))

    async def _send_sync_iter(self, stream_id: int, body: Iterator[bytes]) -> None:
        chunks = [chunk if isinstance(chunk, bytes) else bytes(chunk) for chunk in body if chunk]
        await self._send_bytes(stream_id, b"".join(chunks))

    async def _wait_for_window(self, stream_id: int) -> None:
        while self.h2conn.local_flow_control_window(stream_id) <= 0:
            self._window_updated.clear()
            await self._window_updated.wait()

    async def check_to_write(self) -> None:
        data_to_send = self.h2conn.data_to_send()
        if data_to_send:
            dlogger.debug(("writing data", data_to_send))
            self.writer.write(data_to_send)
            try:
                await self.writer.drain()
            except Exception:
                pass

    async def reader_t(self) -> None:
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

    async def handle_events(self, events: List) -> None:
        for event in events:
            if isinstance(event, h2.events.StreamEnded):
                self._on_stream_ended(event)
            elif isinstance(event, h2.events.DataReceived):
                self._on_data_received(event)
            elif isinstance(event, h2.events.ResponseReceived):
                self._on_response_received(event)
            elif isinstance(event, h2.events.SettingsAcknowledged):
                self._on_settings_acknowledged()
            elif isinstance(event, h2.events.WindowUpdated):
                self._on_window_updated()
            elif isinstance(event, h2.events.StreamReset):
                self._on_stream_reset(event)
            elif isinstance(event, DISCONNECT_EVENTS):
                self._on_disconnect()
            elif isinstance(event, h2.events.TrailersReceived):
                self._on_trailers_received(event)
            elif isinstance(event, IGNORED_EVENTS):
                dlogger.debug("ignoring http2 event %s", event.__class__.__name__)
            elif isinstance(event, h2.events.RemoteSettingsChanged):
                self._on_remote_settings_changed(event)
            elif isinstance(event, h2.events.PingReceived):
                pass
            else:
                raise MissingEvent(f"another event {event.__class__.__name__}")

    def _on_stream_ended(self, event: h2.events.StreamEnded) -> None:
        dlogger.debug(f"--- exit stream, id: {event.stream_id}")
        req = self.requests.get(event.stream_id)
        if not req:
            return
        if not req["future"].done():
            req["future"].set_result(None)
        req["chunk_queue"].put_nowait(None)

    def _on_data_received(self, event: h2.events.DataReceived) -> None:
        req = self.requests.get(event.stream_id)
        if not req:
            dlogger.debug("data for unknown stream %s", event.stream_id)
            return

        if event.data:
            req["chunk_queue"].put_nowait(bytes(event.data))
            dlogger.debug(f"queued {len(event.data)} bytes for stream {event.stream_id}")

    def _on_response_received(self, event: h2.events.ResponseReceived) -> None:
        req = self.requests.get(event.stream_id)
        if not req:
            dlogger.debug("response for unknown stream %s", event.stream_id)
            return

        req["headers"] = event.headers
        if not req["future"].done():
            req["future"].set_result(None)

    def _on_settings_acknowledged(self) -> None:
        for stream_id, req in list(self.requests.items()):
            if not req["data_sent"] and not req["send_scheduled"]:
                req["send_scheduled"] = True
                try:
                    self.loop.create_task(self._send_stream(stream_id))
                except Exception:
                    req["send_scheduled"] = False

    def _on_window_updated(self) -> None:
        self._window_updated.set()

    def _on_stream_reset(self, event: h2.events.StreamReset) -> None:
        req = self.requests.get(event.stream_id)
        if req and not req["future"].done():
            req["future"].set_exception(ConnectionDisconnected())

    def _on_disconnect(self) -> None:
        self._closing = True
        try:
            self.connection.keep = False
        except Exception:
            pass
        self._fail_all_pending(ConnectionDisconnected())

    def _on_trailers_received(self, event: h2.events.TrailersReceived) -> None:
        req = self.requests.get(event.stream_id)
        if req:
            try:
                req["headers"] = list(req.get("headers", [])) + list(event.headers)
            except Exception:
                pass

    def _on_remote_settings_changed(self, event: h2.events.RemoteSettingsChanged) -> None:
        new_max = event.changed_settings.get(h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS)
        if new_max is not None:
            new_limit = int(new_max.new_value)
            if new_limit != self._max_streams:
                inflight = self._max_streams - self._stream_sem._value
                self._max_streams = new_limit
                self._stream_sem._value = max(0, new_limit - inflight)

    def cleanup(self) -> None:
        try:
            self.reader_task.cancel()
        except Exception:
            pass
        try:
            self.loop.create_task(self._wait_reader_cancel())
        except Exception:
            pass

    async def _wait_reader_cancel(self) -> None:
        try:
            await self.reader_task
        except asyncio.CancelledError:
            pass

    def _fail_all_pending(self, exc: Exception) -> None:
        reqs = getattr(self, "requests", {}) or {}
        for stream_id, req in list(reqs.items()):
            future = req.get("future")
            if future and not future.done():
                future.set_exception(exc)
            queue = req.get("chunk_queue")
            if queue:
                queue.put_nowait(None)

    # kept for backward compatibility with tests that call send_body directly
    async def send_body(self, stream_id: int) -> None:
        await self._send_stream(stream_id)
