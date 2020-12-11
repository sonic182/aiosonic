"""Connection stuffs."""

import ssl
from ssl import SSLContext
from asyncio import wait_for, open_connection
from asyncio import StreamReader
from asyncio import StreamWriter
from typing import Dict
from typing import Optional
from urllib.parse import ParseResult

import h2.connection
import h2.events

#from concurrent import futures (unused)
from aiosonic.exceptions import ConnectTimeout
from aiosonic.exceptions import HttpParsingError
from aiosonic.exceptions import TimeoutException
from aiosonic.timeout import Timeouts
from aiosonic.connectors import TCPConnector
from aiosonic.http2 import Http2Handler

from aiosonic.types import ParamsType
from aiosonic.types import ParsedBodyType


class Connection:
    """Connection class."""
    def __init__(self, connector: TCPConnector) -> None:
        self.connector = connector
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None
        self.keep = False  # keep alive flag
        self.key = None
        self.blocked = False
        self.temp_key: Optional[str] = None

        self.h2conn: Optional[h2.connection.H2Connection] = None
        self.h2handler: Optional[Http2Handler] = None

    async def connect(self,
                      urlparsed: ParseResult,
                      verify: bool,
                      ssl_context: SSLContext,
                      timeouts: Timeouts,
                      http2: bool = False) -> None:
        """Connet with timeout."""
        try:
            await wait_for(self._connect(urlparsed, verify,
                                                 ssl_context, http2),
                                   timeout=(timeouts
                                            or self.timeouts).sock_connect)
        except TimeoutException:
            raise ConnectTimeout()

    async def _connect(self, urlparsed: ParseResult, verify: bool,
                       ssl_context: SSLContext, http2: bool) -> None:
        """Get reader and writer."""
        if not urlparsed.hostname:
            raise HttpParsingError('missing hostname')

        key = f'{urlparsed.hostname}-{urlparsed.port}'

        if self.writer:
            # python 3.6 doesn't have writer.is_closing
            is_closing = getattr(
                self.writer, 'is_closing',
                self.writer._transport.is_closing)  # type: ignore
        else:

            def is_closing():
                return True  # noqa

        if not (self.key and key == self.key and not is_closing()):
            self.close()

            if urlparsed.scheme == 'https':
                ssl_context = ssl_context or ssl.create_default_context(
                    ssl.Purpose.SERVER_AUTH, )
                if http2:  # flag will be removed when fully http2 support
                    ssl_context.set_alpn_protocols(['h2', 'http/1.1'])
                if not verify:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
            port = urlparsed.port or (443
                                      if urlparsed.scheme == 'https' else 80)
            self.reader, self.writer = await open_connection(
                urlparsed.hostname, port, ssl=ssl_context)

            self.temp_key = key
            await self._connection_made()

    async def _connection_made(self) -> None:
        tls_conn = self.writer.get_extra_info('ssl_object')
        if not tls_conn:
            return

        # Always prefer the result from ALPN to that from NPN.
        negotiated_protocol = tls_conn.selected_alpn_protocol()
        if negotiated_protocol is None:
            negotiated_protocol = tls_conn.selected_npn_protocol()

        if negotiated_protocol == 'h2':
            self.h2conn = h2.connection.H2Connection()
            self.h2handler = Http2Handler(self)

    def keep_alive(self) -> None:
        """Check if keep alive."""
        self.keep = True

    def block_until_read_chunks(self):
        """Check if keep alive."""
        self.blocked = True

    async def __aenter__(self):
        """Get connection from pool."""
        return self

    async def __aexit__(self, exc_type: None, exc: None, tb: None) -> None:
        """Release connection."""
        if self.keep and not exc:
            self.key = self.temp_key
        else:
            self.key = None
            self.h2conn = None
            if self.writer:
                self.close()

        if not self.blocked:
            await self.release()
            if self.h2handler:
                self.h2handler.cleanup()

    async def release(self) -> None:
        """Release connection."""
        await self.connector.release(self)

    @property
    def timeouts(self) -> Timeouts:
        return self.connector.timeouts

    def __del__(self) -> None:
        """Cleanup."""
        self.close(True)

    def close(self, check_closing: bool=False) -> None:
        """Close connection if opened."""
        if self.writer:
            is_closing = getattr(self.writer, 'is_closing',
                                 self.writer._transport.is_closing)
            if not check_closing or is_closing():
                self.writer.close()

    async def http2_request(self, headers: Dict[str, str],
                            body: Optional[ParsedBodyType]):
        if self.h2handler:
            return await self.h2handler.request(headers, body)
