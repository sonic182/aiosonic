"""Connection stuffs."""

import asyncio
from asyncio import StreamReader
from asyncio import StreamWriter
import ssl
from typing import Optional
from ssl import SSLContext
from urllib.parse import ParseResult

import h2.connection
from hyperframe.frame import SettingsFrame

from concurrent import futures
from aiosonic.exceptions import ConnectTimeout
from aiosonic.timeout import Timeouts
from aiosonic.connectors import TCPConnector


class Connection:
    """Connection class."""

    def __init__(self, connector: TCPConnector):
        self.connector = connector
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None
        self.keep = False
        self.key = None
        self.blocked = False
        self.temp_key: Optional[str] = None

        self.h2conn: Optional[h2.connection.H2Connection] = None

    async def connect(self, urlparsed: ParseResult, verify: bool,
                      ssl_context: SSLContext, timeouts: Timeouts):
        """Connet with timeout."""
        try:
            await asyncio.wait_for(
                self._connect(urlparsed, verify, ssl_context),
                timeout=(timeouts or self.timeouts).sock_connect
            )
        except futures._base.TimeoutError:
            raise ConnectTimeout()

    async def _connect(self, urlparsed: ParseResult, verify: bool,
                       ssl_context: SSLContext):
        """Get reader and writer."""
        key = '%s-%s' % (urlparsed.hostname, urlparsed.port)

        if self.writer:
            # python 3.6 doesn't have writer.is_closing
            is_closing = getattr(
                self.writer, 'is_closing', self.writer._transport.is_closing)
        else:
            def is_closing(): return True  # noqa

        if not (self.key and key == self.key and not is_closing()):
            if self.writer:
                self.writer.close()

            if urlparsed.scheme == 'https':
                ssl_context = ssl_context or ssl.create_default_context(
                    ssl.Purpose.SERVER_AUTH,
                )
                ssl_context.set_alpn_protocols(['h2', 'http/1.1'])
                if not verify:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
            port = urlparsed.port or (
                443 if urlparsed.scheme == 'https' else 80)
            self.reader, self.writer = await asyncio.open_connection(
                urlparsed.hostname,
                port,
                ssl=ssl_context
            )

            self.temp_key = key
            await self._connection_made()

    async def _connection_made(self):
        tls_conn = self.writer.get_extra_info('ssl_object')
        if not tls_conn:
            return

        # Always prefer the result from ALPN to that from NPN.
        negotiated_protocol = tls_conn.selected_alpn_protocol()
        if negotiated_protocol is None:
            negotiated_protocol = tls_conn.selected_npn_protocol()

        if negotiated_protocol == 'h2':
            self.h2conn = h2.connection.H2Connection()

            self.h2conn.initiate_connection()

            # This reproduces the error in #396, by changing the header table size.
            # self.h2conn.update_settings({SettingsFrame.HEADER_TABLE_SIZE: 4096})
            self.writer.write(self.h2conn.data_to_send())

    def keep_alive(self):
        """Check if keep alive."""
        self.keep = True

    def block_until_read_chunks(self):
        """Check if keep alive."""
        self.blocked = True

    async def __aenter__(self):
        """Get connection from pool."""
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Release connection."""
        if self.keep and not exc:
            self.key = self.temp_key
        else:
            self.key = None
            self.h2conn = None
            if self.writer:
                self.writer.close()

        if not self.blocked:
            await self.release()

    async def release(self):
        """Release connection."""
        await self.connector.release(self)

    @property
    def timeouts(self) -> Timeouts:
        return self.connector.timeouts

    def __del__(self):
        """Cleanup."""
        if self.writer:
            is_closing = getattr(
                self.writer, 'is_closing', self.writer._transport.is_closing)
            if is_closing():
                self.writer.close()
