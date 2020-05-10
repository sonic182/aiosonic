import asyncio
from typing import Optional

import h2.events

from typing import Dict
from typing import Awaitable

from aiosonic.exceptions import MissingEvent
from aiosonic.types import ParamsType
from aiosonic.types import ParsedBodyType


class Http2Handler(object):
    def __init__(self, connection):
        """Initialize."""
        self.connection = connection
        h2conn = connection.h2conn

        loop = asyncio.get_event_loop()
        h2conn.initiate_connection()
        self.writer_q = asyncio.Queue()

        self.requests = {}

        # This reproduces the error in #396, by changing the header table size.
        # h2conn.update_settings({SettingsFrame.HEADER_TABLE_SIZE: 4096})
        self.writer.write(h2conn.data_to_send())
        self.reader_task = loop.create_task(self.reader_t())
        self.writer_task = loop.create_task(self.writer_t())

    @property
    def writer(self):
        return self.connection.writer

    @property
    def reader(self):
        return self.connection.reader

    @property
    def h2conn(self):
        return self.connection.h2conn

    def cleanup(self):
        """Cleanup."""
        self.reader_task.cancel()
        self.writer_task.cancel()

    async def request(self, headers: Dict[str, str],
                      body: Optional[ParsedBodyType]):
        stream_id = self.h2conn.get_next_available_stream_id()
        self.h2conn.send_headers(stream_id, headers.items(), end_stream=True)
        from aiosonic import HttpResponse
        future: Awaitable[bytes] = asyncio.Future()
        self.requests[stream_id] = {
            'body': b'',
            'headers': None,
            'future': future
        }
        await self.writer_q.put(True)
        await future
        res = self.requests[stream_id].copy()
        del self.requests[stream_id]

        response = HttpResponse()
        for key, val in res['headers']:
            if key == b':status':
                response.response_initial = {'version': b'2', 'code': val}
            else:
                response._set_header(key, val)

        if res['body']:
            response._set_body(res['body'])

        return response

    async def reader_t(self):
        """Reader task."""
        read_size = 16000

        while True:
            data = await asyncio.wait_for(self.reader.read(read_size), 3)
            events = self.h2conn.receive_data(data)

            if events:
                self.handle_events(events)

                await self.writer_q.put(True)

    def handle_events(self, events):
        """Handle http2 events."""
        h2conn = self.h2conn

        for event in events:
            if isinstance(event, h2.events.StreamEnded):
                self.requests[event.stream_id]['future'].set_result(
                    self.requests[event.stream_id]['body'])
            elif isinstance(event, h2.events.DataReceived):
                self.requests[event.stream_id]['body'] += event.data

                if (event.stream_id in h2conn.streams
                        and not h2conn.streams[event.stream_id].closed):
                    h2conn.increment_flow_control_window(
                        event.flow_controlled_length, event.stream_id)
                h2conn.increment_flow_control_window(
                    event.flow_controlled_length)
            elif isinstance(event, h2.events.ResponseReceived):
                self.requests[event.stream_id]['headers'] = event.headers
            elif isinstance(event,
                            (h2.events.WindowUpdated, h2.events.PingReceived,
                             h2.events.RemoteSettingsChanged,
                             h2.events.SettingsAcknowledged)):
                pass
            else:
                raise MissingEvent(f'another event {event.__class__.__name__}')

    async def writer_t(self):
        """Writer task."""
        h2conn = self.h2conn

        while True:
            await self.writer_q.get()
            while True:
                data_to_send = h2conn.data_to_send()

                if data_to_send:
                    self.writer.write(data_to_send)
                else:
                    break
