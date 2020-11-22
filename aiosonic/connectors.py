"""Connector stuffs."""

from asyncio import wait_for
from asyncio import sleep as asyncio_sleep
from asyncio import StreamReader
from asyncio import StreamWriter
import ssl
from ssl import SSLContext
from typing import Coroutine
from typing import Optional
from urllib.parse import ParseResult

#import h2.connection (unused)
from hyperframe.frame import SettingsFrame

#from concurrent import futures (unused)
from aiosonic.exceptions import ConnectTimeout
from aiosonic.exceptions import ConnectionPoolAcquireTimeout
from aiosonic.exceptions import TimeoutException
from aiosonic.pools import SmartPool
from aiosonic.timeout import Timeouts


class TCPConnector:
    def __init__(self,
                 pool_size: int = 25,
                 timeouts: Timeouts = None,
                 connection_cls=None,
                 pool_cls=None):
        """Initialize."""
        from aiosonic.connection import Connection  # avoid circular dependency
        self.pool_size = pool_size
        connection_cls = connection_cls or Connection
        pool_cls = pool_cls or SmartPool
        self.pool = pool_cls(self, pool_size, connection_cls)
        self.timeouts = timeouts or Timeouts()

    async def acquire(self, urlparsed: ParseResult):
        """Acquire connection."""
        # Faster without timeout
        if not self.timeouts.pool_acquire:
            return await self.pool.acquire(urlparsed)

        try:
            return await wait_for(self.pool.acquire(urlparsed),
                                          self.timeouts.pool_acquire)
        except TimeoutException:
            raise ConnectionPoolAcquireTimeout()

    async def release(self, conn):
        """Acquire connection."""
        res = self.pool.release(conn)
        if isinstance(res, Coroutine):
            await res

    async def wait_free_pool(self):
        """Wait until free pool."""
        while True:
            if self.pool.is_all_free():
                return True
            asyncio_sleep(0.02)

    async def cleanup(self):
        """Cleanup connector connections."""
        await self.pool.cleanup()
