"""Pools module."""

from urllib.parse import ParseResult
from asyncio import Semaphore
from asyncio import Queue

class CyclicQueuePool:
    """Cyclic queue pool of connections."""
    def __init__(self, connector, pool_size, connection_cls):
        self.pool_size = pool_size
        self.pool = Queue(pool_size)

        for _ in range(pool_size):
            self.pool.put_nowait(connection_cls(connector))

    async def acquire(self, _urlparsed: ParseResult = None):
        """Acquire connection."""
        return await self.pool.get()

    async def release(self, conn):
        """Acquire connection."""
        return self.pool.put_nowait(conn)

    def is_all_free(self):
        """Indicates if all pool is free."""
        return self.pool_size == self.pool.qsize()


class SmartPool:
    """Pool which utilizes alive connections."""
    def __init__(self, connector, pool_size, connection_cls):
        self.pool_size = pool_size
        self.pool = set()
        self.sem = Semaphore(pool_size)

        for _ in range(pool_size):
            self.pool.add(connection_cls(connector))

    async def acquire(self, urlparsed: ParseResult = None):
        """Acquire connection."""
        await self.sem.acquire()
        if urlparsed:
            key = f'{urlparsed.hostname}-{urlparsed.port}'
            for item in self.pool:
                if item.key == key:
                    self.pool.remove(item)
                    return item
        return self.pool.pop()

    def release(self, conn):
        """Acquire connection."""
        self.pool.add(conn)
        self.sem.release()

    def is_all_free(self):
        """Indicates if all pool is free."""
        return self.pool_size == self.sem._value
