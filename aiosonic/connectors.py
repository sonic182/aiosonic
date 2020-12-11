"""Connector stuffs."""

from asyncio import wait_for
from asyncio import sleep as asyncio_sleep
from ssl import SSLContext
from typing import Coroutine
from urllib.parse import ParseResult

# import h2.connection (unused)
from hyperframe.frame import SettingsFrame

# from concurrent import futures (unused)
from aiosonic.exceptions import ConnectionPoolAcquireTimeout
from aiosonic.exceptions import TimeoutException
from aiosonic.pools import SmartPool
from aiosonic.timeout import Timeouts


class TCPConnector:
    """TCPConnector.

    Holds the main logic for making connections to destination hosts.

    Params:
        * **pool_size**: size for pool of connections
        * **timeouts**: global timeouts to use for connections with this connector. default: :class:`aiosonic.timeout.Timeouts` instance with default args.
        * **connection_cls**: connection class to be used. default: :class:`aiosonic.connection.Connection`
        * **pool_cls**: pool class to be used. default: :class:`aiosonic.pools.SmartPool`

    """

    def __init__(self,
                 pool_size: int = 25,
                 timeouts: Timeouts = None,
                 connection_cls=None,
                 pool_cls=None):
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
        """Release connection."""
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
