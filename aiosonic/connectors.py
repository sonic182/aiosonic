"""Connector stuffs."""
import random
from asyncio import sleep as asyncio_sleep
from asyncio import wait_for
from typing import TYPE_CHECKING, Optional
from urllib.parse import ParseResult

from onecache import ExpirableCache

from aiosonic.exceptions import (
    ConnectTimeout,
    HttpParsingError,
    TimeoutException,
)
from aiosonic.pools import PoolConfig, SmartPool
from aiosonic.resolver import DefaultResolver
from aiosonic.timeout import Timeouts

if TYPE_CHECKING:
    from aiosonic.connection import Connection


class TCPConnector:
    """TCPConnector.

    Holds the main logic for making connections to destination hosts.

    Params:
        * **pool_config**: configs for the connection pool.
        * **timeouts**: global timeouts to use for connections with this connector. default: :class:`aiosonic.timeout.Timeouts` instance with default args.
        * **connection_cls**: connection class to be used. default: :class:`aiosonic.connection.Connection`
        * **pool_cls**: pool class to be used. default: :class:`aiosonic.pools.SmartPool`
        * **resolver**: resolver to be used. default: :class:`aiosonic.resolver.DefaultResolver`
        * **ttl_dns_cache**: ttl in milliseconds for dns cache. default: `10000` 10 seconds
        * **use_dns_cache**: Flag to indicate usage of dns cache. default: `True`
    """

    def __init__(
        self,
        pool_config: PoolConfig = PoolConfig(),
        timeouts: Optional[Timeouts] = None,
        connection_cls=None,
        pool_cls=None,
        resolver=None,
        ttl_dns_cache=10000,
        use_dns_cache=True
    ):
        from aiosonic.connection import Connection  # avoid circular dependency

        connection_cls = connection_cls or Connection
        pool_cls = pool_cls or SmartPool
        self.pool = pool_cls(pool_config, connection_cls, timeouts)
        self.timeouts = timeouts or Timeouts()
        self.resolver = resolver or DefaultResolver()
        self.use_dns_cache = use_dns_cache
        if self.use_dns_cache:
            self.cache = ExpirableCache(512, ttl_dns_cache)

    async def acquire(self, urlparsed: ParseResult, verify, ssl, timeouts, http2) -> "Connection":
        """Acquire connection."""
        if not urlparsed.hostname:
            raise HttpParsingError("missing hostname")

        conn = await self.pool.acquire(urlparsed)
        return await self.after_acquire(urlparsed, conn, verify, ssl, timeouts, http2)

    async def after_acquire(self, urlparsed, conn, verify, ssl, timeouts, http2):

        try:
            dns_info = await self.__resolve_dns(urlparsed.hostname, urlparsed.port)
            await wait_for(
                conn.connect(urlparsed, dns_info, verify, ssl, http2),
                timeout=timeouts.sock_connect,
            )
        except TimeoutException:
            self.release(conn)
            raise ConnectTimeout()
        except BaseException as ex:
            self.release(conn)
            raise ex
        return conn

    def release(self, conn):
        """Release connection."""
        self.pool.release(conn)

    async def wait_free_pool(self):
        """Wait until free pool."""
        while True:
            if self.pool.is_all_free():
                return True
            await asyncio_sleep(0.02)  # pragma: no cover

    async def cleanup(self):
        """Cleanup connector connections."""
        await self.pool.cleanup()

    async def __resolve_dns(self, host: str, port: int):
        key = f"{host}-{port}"
        dns_data = self.cache.get(key)
        if not dns_data:
            dns_data = await self.resolver.resolve(host, port)
            self.cache.set(key, dns_data)
        return random.choice(dns_data)
