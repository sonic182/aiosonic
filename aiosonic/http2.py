import asyncio
from typing import Optional, TYPE_CHECKING

import h2.events

from typing import Awaitable

from aiosonic.exceptions import MissingEvent
from aiosonic.types import ParsedBodyType

from aiosonic.utils import get_debug_logger


dlogger = get_debug_logger()

if TYPE_CHECKING:
    import aiosonic
    from aiosonic.connection import Connection


class Http2Handler(object):
    def __init__(self, connection: "Connection"):
        """Initialize."""
        assert connection
        self.connection = connection
        h2conn = connection.h2conn
        assert h2conn

        loop = asyncio.get_event_loop()
        h2conn.initiate_connection()

        self.requests = {}

        # This reproduces the error in #396, by changing the header table size.
        # h2conn.update_settings({SettingsFrame.HEADER_TABLE_SIZE: 4096})
        self.writer.write(h2conn.data_to_send())
        self.reader_task = loop.create_task(self.reader_t())
        self.writer_task = loop.create_task(self.writer_t())

    @property
    def writer(self):
        assert self.connection.writer
        return self.connection.writer

    @property
    def reader(self):
        assert self.connection.reader
        return self.connection.reader

    @property
    def h2conn(self):
        assert self.connection.h2conn
        return self.connection.h2conn

    def cleanup(self):
        """Cleanup."""
        self.reader_task.cancel()
        self.writer_task.cancel()

    async def request(
        self, headers: "aiosonic.HeadersType", body: Optional[ParsedBodyType]
    ):
        from aiosonic import HttpResponse

        stream_id = self.h2conn.get_next_available_stream_id()
        headers_param = headers.items() if isinstance(headers, dict) else headers
        self.h2conn.send_headers(stream_id, headers_param, end_stream=True)

        future: Awaitable[bytes] = asyncio.Future()
        self.requests[stream_id] = {"body": b"", "headers": None, "future": future}
        await future
        res = self.requests[stream_id].copy()
        del self.requests[stream_id]

        response = HttpResponse()
        for key, val in res["headers"]:
            if key == b":status":
                response.response_initial = {"version": b"2", "code": val}
            else:
                response._set_header(key, val)

        if res["body"]:
            response._set_body(res["body"])

        return response

    async def reader_t(self):
        """Reader task."""
        read_size = 16000

        while True:
            data = await asyncio.wait_for(self.reader.read(read_size), 3)
            events = self.h2conn.receive_data(data)

            if events:
                dlogger.debug(("received events", events))
                try:
                    self.handle_events(events)
                except Exception:
                    dlogger.debug('--- Some Exception!', exc_info=True)
                    raise

    def handle_events(self, events):
        """Handle http2 events."""
        h2conn = self.h2conn

        for event in events:
            if isinstance(event, h2.events.StreamEnded):
                dlogger.debug(f'--- exit stream, id: {event.stream_id}')
                self.requests[event.stream_id]["future"].set_result(
                    self.requests[event.stream_id]["body"]
                )
            elif isinstance(event, h2.events.DataReceived):
                self.requests[event.stream_id]["body"] += event.data

                if (
                    event.stream_id in h2conn.streams
                    and not h2conn.streams[event.stream_id].closed
                    and event.flow_controlled_length
                ):
                    h2conn.increment_flow_control_window(
                        event.flow_controlled_length, event.stream_id
                    )
                dlogger.info(f'Flow increment: {event.flow_controlled_length}')
                if event.flow_controlled_length:
                    h2conn.increment_flow_control_window(event.flow_controlled_length)
            elif isinstance(event, h2.events.ResponseReceived):
                self.requests[event.stream_id]["headers"] = event.headers
            elif isinstance(
                event,
                (
                    h2.events.WindowUpdated,
                    h2.events.PingReceived,
                    h2.events.RemoteSettingsChanged,
                    h2.events.SettingsAcknowledged,
                ),
            ):
                pass
            else:
                raise MissingEvent(f"another event {event.__class__.__name__}")

    async def writer_t(self):
        """Writer task."""
        h2conn = self.h2conn

        while True:
            data_to_send = h2conn.data_to_send()

            if data_to_send:
                dlogger.debug(("writing data", data_to_send))
                self.writer.write(data_to_send)
            else:
                dlogger.debug("stop writing data")
                await asyncio.sleep(0.2)
