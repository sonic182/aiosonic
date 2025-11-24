# copied from aiohttp

import asyncio
import socket
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Type, Union, Optional

from aiosonic.dns_cache import DNSCache
from aiosonic.utils import encode_idna

__all__ = ("ThreadedResolver", "AsyncResolver", "DefaultResolver")

try:
    import aiodns

    # aiodns_default = hasattr(aiodns.DNSResolver, 'gethostbyname')
except ImportError:  # pragma: no cover
    aiodns = None

aiodns_default = False


def get_loop():
    return asyncio.get_running_loop()


class AbstractResolver(ABC):
    """Abstract DNS resolver."""

    @abstractmethod
    async def resolve(self, host: str, port: int, family: int) -> List[Dict[str, Any]]:
        """Return IP address for given hostname"""

    @abstractmethod
    async def close(self) -> None:
        """Release resolver"""


class ThreadedResolver(AbstractResolver):
    """Use Executor for synchronous getaddrinfo() calls, which defaults to
    concurrent.futures.ThreadPoolExecutor.

    Supports IDNA encoding for internationalized domain names and DNS caching.
    """

    def __init__(
        self, cache: Optional[DNSCache] = None, use_cache: bool = True
    ) -> None:
        self._loop = None
        self._cache = (
            cache if cache is not None else (DNSCache() if use_cache else None)
        )

    @property
    def loop(self):
        if not self._loop:
            self._loop = get_loop()
        return self._loop

    async def resolve(
        self, hostname: str, port: int = 0, family: int = socket.AF_INET
    ) -> List[Dict[str, Any]]:
        # Apply IDNA encoding for internationalized domain names
        try:
            encoded_hostname = encode_idna(hostname)
        except (ValueError, UnicodeError):
            # If encoding fails, use original hostname
            encoded_hostname = hostname

        # Create cache key
        cache_key = f"{encoded_hostname}:{port}:{family}"

        # Check cache first
        if self._cache is not None:
            cached_result = self._cache.get(cache_key)
            if cached_result is not None:
                # Reconstruct hosts from cached data
                hosts = []
                for host, cached_port in cached_result:
                    hosts.append(
                        {
                            "hostname": hostname,  # Use original hostname
                            "host": host,
                            "port": cached_port,
                            "family": family,
                            "proto": socket.IPPROTO_TCP,
                            "flags": socket.AI_NUMERICHOST | socket.AI_NUMERICSERV,
                        }
                    )
                return hosts

        # Perform DNS lookup with encoded hostname
        infos = await self.loop.getaddrinfo(
            encoded_hostname,
            port,
            type=socket.SOCK_STREAM,
            family=family,
            flags=socket.AI_ADDRCONFIG,
        )

        hosts = []
        addresses_for_cache = []

        for family, _, proto, _, address in infos:
            if family == socket.AF_INET6 and address[3]:  # type: ignore[misc]
                # This is essential for link-local IPv6 addresses.
                # LL IPv6 is a VERY rare case. Strictly speaking, we should use
                # getnameinfo() unconditionally, but performance makes sense.
                host, _port = socket.getnameinfo(
                    address, socket.NI_NUMERICHOST | socket.NI_NUMERICSERV
                )
                port = int(_port)
            else:
                host, port = address[:2]

            hosts.append(
                {
                    "hostname": hostname,  # Use original hostname, not encoded
                    "host": host,
                    "port": port,
                    "family": family,
                    "proto": proto,
                    "flags": socket.AI_NUMERICHOST | socket.AI_NUMERICSERV,
                }
            )
            addresses_for_cache.append((host, port))

        # Store in cache
        if self._cache is not None and addresses_for_cache:
            self._cache.set(cache_key, addresses_for_cache)

        return hosts

    async def close(self) -> None:
        pass


class AsyncResolver(AbstractResolver):
    """Use the `aiodns` package to make asynchronous DNS lookups

    Supports IDNA encoding for internationalized domain names and DNS caching.
    """

    def __init__(
        self,
        cache: Optional[DNSCache] = None,
        use_cache: bool = True,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        if aiodns is None:
            raise RuntimeError("Resolver requires aiodns library")

        self._loop = get_loop()
        self._resolver = aiodns.DNSResolver(*args, loop=self._loop, **kwargs)
        self._cache = (
            cache if cache is not None else (DNSCache() if use_cache else None)
        )

    async def resolve(
        self, host: str, port: int = 0, family: int = socket.AF_INET
    ) -> List[Dict[str, Any]]:
        # Apply IDNA encoding for internationalized domain names
        try:
            encoded_host = encode_idna(host)
        except (ValueError, UnicodeError):
            # If encoding fails, use original hostname
            encoded_host = host

        # Create cache key
        cache_key = f"{encoded_host}:{port}:{family}"

        # Check cache first
        if self._cache is not None:
            cached_result = self._cache.get(cache_key)
            if cached_result is not None:
                # Reconstruct hosts from cached data
                hosts = []
                for address, cached_port in cached_result:
                    hosts.append(
                        {
                            "hostname": host,  # Use original hostname
                            "host": address,
                            "port": cached_port,
                            "family": family,
                            "proto": 0,
                            "flags": socket.AI_NUMERICHOST | socket.AI_NUMERICSERV,
                        }
                    )
                return hosts

        # Perform DNS lookup with encoded hostname
        try:
            resp = await self._resolver.gethostbyname(encoded_host, family)
        except aiodns.error.DNSError as exc:
            msg = exc.args[1] if len(exc.args) >= 1 else "DNS lookup failed"
            raise OSError(msg) from exc

        hosts = []
        addresses_for_cache = []

        for address in resp.addresses:
            hosts.append(
                {
                    "hostname": host,  # Use original hostname, not encoded
                    "host": address,
                    "port": port,
                    "family": family,
                    "proto": 0,
                    "flags": socket.AI_NUMERICHOST | socket.AI_NUMERICSERV,
                }
            )
            addresses_for_cache.append((address, port))

        if not hosts:
            raise OSError("DNS lookup failed")

        # Store in cache
        if self._cache is not None and addresses_for_cache:
            self._cache.set(cache_key, addresses_for_cache)

        return hosts

    async def close(self) -> None:
        self._resolver.cancel()


_DefaultType = Type[Union[AsyncResolver, ThreadedResolver]]
DefaultResolver: _DefaultType = AsyncResolver if aiodns_default else ThreadedResolver
