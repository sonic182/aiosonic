"""Connector stuffs."""

import asyncio
from asyncio import StreamReader
from asyncio import StreamWriter
import ssl
from typing import Coroutine
from typing import Optional
from ssl import SSLContext
from urllib.parse import ParseResult

import h2.connection
from hyperframe.frame import SettingsFrame

from concurrent import futures
from aiosonic.exceptions import ConnectTimeout
from aiosonic.exceptions import ConnectionPoolAcquireTimeout
from aiosonic.pools import SmartPool
from aiosonic.timeout import Timeouts


class TCPConnector:

    def __init__(self, pool_size: int = 25, timeouts: Timeouts = None,
                 connection_cls=None, pool_cls=None):
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
            return await asyncio.wait_for(
                self.pool.acquire(urlparsed),
                self.timeouts.pool_acquire
            )
        except futures._base.TimeoutError:
            raise ConnectionPoolAcquireTimeout()

    async def release(self, conn):
        """Acquire connection."""
        res = self.pool.release(conn)
        if isinstance(res, Coroutine):
            await res
