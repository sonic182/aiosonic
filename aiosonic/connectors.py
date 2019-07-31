"""Connector stuffs."""

import asyncio
import ssl
from ssl import SSLContext
from urllib.parse import ParseResult

from concurrent import futures
from aiosonic.exceptions import ConnectTimeout


class TCPConnector:

    def __init__(self, pool_size=25, request_timeout=27, connect_timeout=3,
                 connection_cls=None):
        """Initialize."""
        self.pool_size = pool_size
        self.request_timeout = request_timeout
        self.connect_timeout = connect_timeout
        self.pool = asyncio.Queue(pool_size)
        connection_cls = connection_cls or Connection

        for _ in range(pool_size):
            self.pool.put_nowait(connection_cls(self))

    async def acquire(self):
        """Acquire connection."""
        return await self.pool.get()

    def release(self, conn):
        """Acquire connection."""
        return self.pool.put_nowait(conn)


class Connection:
    """Connection class."""

    def __init__(self, connector: TCPConnector):
        self.connector = connector
        self.reader = None
        self.writer = None
        self.keep = False
        self.key = None
        self.temp_key = None

    async def connect(self, urlparsed: ParseResult, verify: bool,
                      ssl_context: SSLContext):
        """Connet with timeout."""
        try:
            await asyncio.wait_for(
                self._connect(urlparsed, verify, ssl_context),
                timeout=self.connector.connect_timeout
            )
        except futures._base.TimeoutError:
            raise ConnectTimeout()

    async def _connect(self, urlparsed: ParseResult, verify: bool,
                       ssl_context: SSLContext):
        """Get reader and writer."""
        key = '%s-%s' % (urlparsed.hostname, urlparsed.port)

        if self.writer:
            # python 3.5 and 3.6 doesn't have writer.is_closing
            is_closing = getattr(
                self.writer, 'is_closing', self.writer._transport.is_closing)
        else:
            is_closing = lambda: True  # noqa

        if not (self.key and key == self.key and not is_closing()):
            if urlparsed.scheme == 'https':
                ssl_context = ssl_context or ssl.create_default_context(
                    ssl.Purpose.SERVER_AUTH,
                )
                if not verify:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
            self.reader, self.writer = await asyncio.open_connection(
                urlparsed.hostname, urlparsed.port, ssl=ssl_context)
            self.temp_key = key

    def keep_alive(self):
        """Check if keep alive."""
        self.keep = True

    async def __aenter__(self):
        """Get connection from pool."""
        return self

    async def __aexit__(self, *args, **kwargs):
        """Release connection."""
        if self.keep:
            self.key = self.temp_key
        else:
            self.key = None
            if self.writer:
                self.writer.close()
        self.connector.release(self)
