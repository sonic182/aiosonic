"""Pools module."""

import time
from abc import ABC, abstractmethod
from asyncio import Queue, Semaphore, wait_for
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import ParseResult

from aiosonic.exceptions import ConnectionPoolAcquireTimeout, TimeoutException
from aiosonic.timeout import Timeouts


@dataclass(frozen=True, eq=True)
class PoolConfig:
    """Configuration options for database connection pools.

    Controls how connections are created, maintained, and recycled.

    This class is immutable and hashable, allowing it to be used as a dictionary key.
    """

    size: int = field(
        default=30,
        metadata={"description": "Maximum number of connections to keep in the pool"},
    )
    max_conn_requests: Optional[int] = field(
        default=1000,
        metadata={
            "description": "Maximum number of requests per connection before recycling (None means no limit)"
        },
    )
    max_conn_idle_ms: int = field(
        default=60000,  # 1min
        metadata={
            "description": "Maximum time in milliseconds a connection can remain idle before being closed (None means no limit)"
        },
    )

    def __hash__(self):
        """Make PoolConfig hashable for use as dictionary keys.

        Returns:
            int: Hash value based on the configuration values
        """
        return hash((self.size, self.max_conn_requests, self.max_conn_idle_ms))


class BasePool(ABC):
    """Abstract base class for connection pools."""

    def __init__(
        self,
        conf: PoolConfig,
        connection_cls,
        timeouts: Optional[Timeouts] = None,
    ):
        """Initialize pool with common attributes."""
        self.conf = conf
        self.timeouts = timeouts or Timeouts()
        self._init_pool(connection_cls)

    @abstractmethod
    def _init_pool(self, connection_cls):
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

    @property
    def pool_size(self):
        return self.conf.size

    def _is_connection_idle(self, conn) -> bool:
        """Check if a connection has been idle too long.

        Returns:
            bool: True if the connection is idle and should be closed
        """
        if (
            self.conf.max_conn_idle_ms is not None
            and conn.last_released_time is not None
        ):
            idle_time_ms = (time.monotonic() - conn.last_released_time) * 1000
            if idle_time_ms > self.conf.max_conn_idle_ms:
                return True
        return False


class CyclicQueuePool(BasePool):
    """Cyclic queue pool of connections."""

    def _init_pool(self, connection_cls):
        self.pool = Queue(self.pool_size)
        for _ in range(self.pool_size):
            self.pool.put_nowait(connection_cls(self))

    async def acquire(self, _urlparsed: ParseResult = None):
        """Acquire connection."""
        # Get connection from the pool
        if not self.timeouts.pool_acquire:
            conn = await self.pool.get()
        else:
            try:
                conn = await wait_for(self.pool.get(), self.timeouts.pool_acquire)
            except TimeoutException:
                raise ConnectionPoolAcquireTimeout()

        if self._is_connection_idle(conn):
            # Close idle connection, this will allow re-opening when using it.
            conn.close()

        return conn

    def release(self, conn):
        """Release connection."""
        return self.pool.put_nowait(conn)

    def is_all_free(self):
        """Indicates if all pool is free."""
        return self.pool_size == self.pool.qsize()

    def free_conns(self) -> int:
        return self.pool.qsize()

    async def cleanup(self):
        """Get all conn and close them, this method let this pool unusable."""
        for _ in range(self.pool_size):
            conn = self.pool.get_nowait()
            conn.close()


class SmartPool(BasePool):
    """Pool which priorizes the reusage of connections."""

    def _init_pool(self, connection_cls):
        self.pool = set()
        self.sem = Semaphore(self.pool_size)
        for _ in range(self.pool_size):
            self.pool.add(connection_cls(self))

    async def acquire(self, urlparsed: ParseResult = None):
        """Acquire connection."""
        if not self.timeouts.pool_acquire:
            await self.sem.acquire()
        else:
            try:
                await wait_for(self.sem.acquire(), self.timeouts.pool_acquire)
            except TimeoutException:
                raise ConnectionPoolAcquireTimeout()

        conn = None

        # Find connection based on URL
        if urlparsed:
            key = f"{urlparsed.hostname}-{urlparsed.port}"
            for item in self.pool:
                if item.key == key:
                    self.pool.remove(item)
                    conn = item
                    break

        # If no matching connection, get any connection
        if conn is None and self.pool:
            conn = self.pool.pop()

        # Check if connection is idle
        if conn is not None and self._is_connection_idle(conn):
            conn.close()
            conn = conn.__class__(self)

        return conn

    def release(self, conn) -> None:
        """Release connection."""
        self.pool.add(conn)
        self.sem.release()

    def free_conns(self) -> int:
        return len(self.pool)

    def is_all_free(self):
        """Indicates if all pool is free."""
        return self.pool_size == self.sem._value

    async def cleanup(self) -> None:
        """Get all conn and close them, this method let this pool unusable."""
        for _ in range(self.pool_size):
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

    def _init_pool(self, connection_cls):
        self.conn_cls = connection_cls

    async def acquire(self, _urlparsed: ParseResult = None):
        """Acquire connection."""
        return self.conn_cls(self)

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
