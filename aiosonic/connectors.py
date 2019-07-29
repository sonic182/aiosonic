
import asyncio
from urllib.parse import ParseResult

COUNTER = 0


class TCPConnector:

    def __init__(self, pool_size=25):
        """Initialize."""
        self.pool_size = pool_size
        self.pool = asyncio.Queue(pool_size)

        for _ in range(pool_size):
            self.pool.put_nowait(Connection(self))

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

    async def connect(self, urlparsed: ParseResult):
        """Get reader and writer."""
        key = '%s-%s' % (urlparsed.hostname, urlparsed.port)
        if not (self.key and key == self.key and not self.writer.is_closing()):
            self.reader, self.writer = await asyncio.open_connection(
                urlparsed.hostname, urlparsed.port)
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
            self.writer.close()
        self.connector.release(self)
