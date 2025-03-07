"""Pools module."""

from abc import ABC, abstractmethod
from asyncio import Queue, Semaphore, wait_for
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import ParseResult

from aiosonic.exceptions import ConnectionPoolAcquireTimeout, TimeoutException
from aiosonic.timeout import Timeouts


@dataclass
class PoolConfig:
    """Configuration options for connection pools."""

    size: int = field(default=10)


class BasePool(ABC):
    """Abstract base class for connection pools."""

    def __init__(
        self,
        connector,
        pool_conf: PoolConfig,
        connection_cls,
        timeouts: Optional[Timeouts] = None,
    ):
        """Initialize pool with common attributes."""
        self.pool_conf = pool_conf
        self.timeouts = timeouts or Timeouts()
        self._init_pool(connector, connection_cls)

    @abstractmethod
    def _init_pool(self, connector, connection_cls):
        """Initialize the pool structure."""
        pass

    @abstractmethod
    async def acquire(self, urlparsed: ParseResult = None):
        """Acquire a connection from the pool."""
        pass

    @abstractmethod
    def release(self, conn) -> None:
        """Release a connection back to the pool."""
        pass

    @abstractmethod
    def free_conns(self) -> int:
        """Return number of free connections."""
        pass

    @abstractmethod
    def is_all_free(self) -> bool:
        """Indicate if all connections in the pool are free."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up all connections. Makes the pool unusable."""
        pass


class CyclicQueuePool(BasePool):
    """Cyclic queue pool of connections."""

    def _init_pool(self, connector, connection_cls):
        self.pool = Queue(self.pool_conf.size)
        for _ in range(self.pool_conf.size):
            self.pool.put_nowait(connection_cls(connector))

    async def acquire(self, _urlparsed: ParseResult = None):
        """Acquire connection."""
        if not self.timeouts.pool_acquire:
            return await self.pool.get()
        else:
            try:
                return await wait_for(self.pool.get(), self.timeouts.pool_acquire)
            except TimeoutException:
                raise ConnectionPoolAcquireTimeout()

    def release(self, conn):
        """Release connection."""
        return self.pool.put_nowait(conn)

    def is_all_free(self):
        """Indicates if all pool is free."""
        return self.pool_conf.size == self.pool.qsize()

    def free_conns(self) -> int:
        return self.pool.qsize()

    async def cleanup(self):
        """Get all conn and close them, this method let this pool unusable."""
        for _ in range(self.pool_conf.size):
            conn = self.pool.get_nowait()
            conn.close()


class SmartPool(BasePool):
    """Pool which priorizes the reusage of connections."""

    def _init_pool(self, connector, connection_cls):
        self.pool = set()
        self.sem = Semaphore(self.pool_conf.size)
        for _ in range(self.pool_conf.size):
            self.pool.add(connection_cls(connector))

    async def acquire(self, urlparsed: ParseResult = None):
        """Acquire connection."""
        if not self.timeouts.pool_acquire:
            await self.sem.acquire()
        else:
            try:
                await wait_for(self.sem.acquire(), self.timeouts.pool_acquire)
            except TimeoutException:
                raise ConnectionPoolAcquireTimeout()

        if urlparsed:
            key = f"{urlparsed.hostname}-{urlparsed.port}"
            for item in self.pool:
                if item.key == key:
                    self.pool.remove(item)
                    return item
        return self.pool.pop()

    def release(self, conn) -> None:
        """Release connection."""
        self.pool.add(conn)
        self.sem.release()

    def free_conns(self) -> int:
        return len(self.pool)

    def is_all_free(self):
        """Indicates if all pool is free."""
        return self.pool_conf.size == self.sem._value

    async def cleanup(self) -> None:
        """Get all conn and close them, this method let this pool unusable."""
        for _ in range(self.pool_conf.size):
            conn = await self.acquire()
            conn.close()


class WsPool(BasePool):
    """WebSocket connection factory masquerading as a pool.

    This is not a real connection pool - it simply creates new WebSocket connections
    on demand without any pooling functionality. This design choice exists because
    WebSocket connections are long-lived and typically managed by the application
    logic rather than a connection pool.

    The pool interface methods are implemented as no-ops or with dummy values:
    - acquire(): Creates and returns a new WebSocket connection
    - release(): Does nothing since connections aren't pooled
    - free_conns(): Always returns 100 (dummy value)
    - is_all_free(): Always returns True
    - cleanup(): Does nothing

    Note:
        Users are responsible for managing the lifecycle (including cleanup) of 
        WebSocket connections obtained from this factory.
    """

    def _init_pool(self, connector, connection_cls):
        self.connector = connector
        self.conn_cls = connection_cls

    async def acquire(self, _urlparsed: ParseResult = None):
        """Acquire connection."""
        return self.conn_cls(self.connector)

    def release(self, conn) -> None:
        """Release connection."""
        pass

    def free_conns(self) -> int:
        return 100

    def is_all_free(self):
        """Indicates if all pool is free."""
        return True

    async def cleanup(self) -> None:
        """Get all conn and close them, this method let this pool unusable."""
        pass
