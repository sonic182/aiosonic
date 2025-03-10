"""Connector stuffs."""

import random
from asyncio import sleep as asyncio_sleep
from asyncio import wait_for
from typing import TYPE_CHECKING, Any, Dict, Optional, Union
from urllib.parse import ParseResult

from onecache import ExpirableCache

from aiosonic.exceptions import (ConnectTimeout, HttpParsingError,
                                 TimeoutException)
from aiosonic.pools import PoolConfig, SmartPool
from aiosonic.resolver import DefaultResolver
from aiosonic.timeout import Timeouts

if TYPE_CHECKING:
    from aiosonic.connection import Connection


class TCPConnector:
    """TCPConnector.

    Holds the main logic for making connections to destination hosts.

    Parameters:
        pool_configs (Optional[Dict[str, PoolConfig]]):
            Map of host domains to pool configurations. Keys are host domains
            (e.g., "https://example.com" or "example.com") and values are PoolConfig
            instances. A special key ":default" is used for hosts without a specific configuration.
        timeouts (Optional[Timeouts]):
            Global timeouts for connections. Defaults to a Timeouts instance with default args.
        connection_cls:
            Connection class to be used. Defaults to Connection.
        pool_cls:
            Pool class to be used. Defaults to SmartPool.
        resolver:
            DNS resolver to be used. Defaults to DefaultResolver.
        ttl_dns_cache (int):
            TTL in milliseconds for DNS cache. Defaults to 10000 (10 seconds).
        use_dns_cache (bool):
            Flag to indicate usage of DNS cache. Defaults to True.
    """

    def __init__(
        self,
        pool_configs: Optional[Dict[str, Union[PoolConfig, Dict[str, Any]]]] = None,
        timeouts: Optional[Timeouts] = None,
        connection_cls=None,
        pool_cls=None,
        resolver=None,
        ttl_dns_cache=10000,
        use_dns_cache=True,
        ):
        from aiosonic.connection import Connection  # avoid circular dependency

        self.connection_cls = connection_cls or Connection
        self.pool_cls = pool_cls or SmartPool
        self.timeouts = timeouts or Timeouts()

        if pool_configs is None:
            pool_configs = {}

        if ":default" not in pool_configs:
            pool_configs[":default"] = PoolConfig()

        self.pool_configs = _check_pool_configs(pool_configs)

        # Pre-create pools based on provided pool_configs keys.
        # Keys are expected to be in the form "<scheme>://<host>" or ":default".
        self.pools: Dict[str, SmartPool] = {}
        for key, config in self.pool_configs.items():
            self.pools[key] = self.pool_cls(config, self.connection_cls, self.timeouts)

        self.resolver = resolver or DefaultResolver()
        self.use_dns_cache = use_dns_cache
        if self.use_dns_cache:
            self.cache = ExpirableCache(512, ttl_dns_cache)

    async def acquire(
        self, urlparsed: ParseResult, verify, ssl, timeouts, http2
    ) -> "Connection":
        """Acquire a connection from the appropriate pool."""
        if not urlparsed.hostname:
            raise HttpParsingError("missing hostname")

        host_key = f"{urlparsed.scheme}://{urlparsed.hostname}"

        # Use host-specific pool if available; otherwise, fall back to the default pool.
        if host_key in self.pools:
            pool = self.pools[host_key]
        else:
            pool = self.pools[":default"]

        conn = await pool.acquire(urlparsed)
        return await self.after_acquire(urlparsed, conn, verify, ssl, timeouts, http2)

    async def after_acquire(self, urlparsed, conn, verify, ssl, timeouts, http2):
        """Process connection after acquisition."""
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
        """Release connection back to its pool."""
        conn.release()

    async def wait_free_pool(self):
        """Wait until all pools are free."""
        while True:
            if all(pool.is_all_free() for pool in self.pools.values()):
                return True
            await asyncio_sleep(0.02)  # pragma: no cover

    async def cleanup(self):
        """Cleanup connector connections."""
        for pool in self.pools.values():
            await pool.cleanup()

    async def __resolve_dns(self, host: str, port: int):
        key = f"{host}-{port}"
        dns_data = self.cache.get(key)
        if not dns_data:
            dns_data = await self.resolver.resolve(host, port)
            self.cache.set(key, dns_data)
        assert isinstance(dns_data, list)
        return random.choice(dns_data)


def _check_pool_configs(configs) -> Dict[str, PoolConfig]:
    result = {}  # temporary variable to store results
    for key, val in configs.items():
        if isinstance(val, PoolConfig):
            result[key] = val
        else:
            result[key] = PoolConfig(**val)
    return result
