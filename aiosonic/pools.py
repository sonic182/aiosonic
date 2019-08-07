"""Pools module."""

import asyncio
from urllib.parse import ParseResult


class CyclicQueuePool:
    """Cyclic queue pool of connections."""

    def __init__(self, connector, pool_size, connection_cls):
        self.pool = asyncio.Queue(pool_size)

        for _ in range(pool_size):
            self.pool.put_nowait(connection_cls(connector))

    async def acquire(self, _urlparsed: ParseResult = None):
        """Acquire connection."""
        return await self.pool.get()

    async def release(self, conn):
        """Acquire connection."""
        return self.pool.put_nowait(conn)


class SmartPool:
    """Pool which utilizes alive connections."""

    def __init__(self, connector, pool_size, connection_cls):
        self.pool = set()
        self.sem = asyncio.Semaphore(pool_size)

        for _ in range(pool_size):
            self.pool.add(connection_cls(connector))

    async def acquire(self, urlparsed: ParseResult = None):
        """Acquire connection."""
        await self.sem.acquire()
        if urlparsed:
            key = '%s-%s' % (urlparsed.hostname, urlparsed.port)
            for item in self.pool:
                if item.key == key:
                    self.pool.remove(item)
                    return item
        return self.pool.pop()

    def release(self, conn):
        """Acquire connection."""
        self.pool.add(conn)
        self.sem.release()
