import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiosonic.resolver import AsyncResolver, ThreadedResolver


@pytest.mark.asyncio
@pytest.mark.skipif(not socket.has_ipv6, reason="IPv6 is unavailable")
async def test_threaded_resolver_ipv6_with_only_loopback_interfaces(mocker):
    resolver = ThreadedResolver()
    getaddrinfo = resolver.loop.getaddrinfo

    async def loopback_getaddrinfo(*args, **kwargs):
        if kwargs.get("flags", 0) & socket.AI_ADDRCONFIG:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        return await getaddrinfo(*args, **kwargs)

    mocker.patch.object(resolver.loop, "getaddrinfo", side_effect=loopback_getaddrinfo)
    hosts = await resolver.resolve("::1", 443, family=socket.AF_INET6)

    assert hosts == [
        {
            "hostname": "::1",
            "host": "::1",
            "port": 443,
            "family": socket.AF_INET6,
            "proto": socket.IPPROTO_TCP,
            "flags": socket.AI_NUMERICHOST | socket.AI_NUMERICSERV,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("error_code", [socket.EAI_AGAIN, socket.EAI_FAIL])
async def test_threaded_resolver_propagates_dns_errors_without_retry(mocker, error_code):
    resolver = ThreadedResolver()
    error = socket.gaierror(error_code, "lookup failed")
    lookup = mocker.patch.object(resolver.loop, "getaddrinfo", side_effect=error)

    with pytest.raises(socket.gaierror) as exc_info:
        await resolver.resolve("example.invalid", 80)

    assert exc_info.value is error
    lookup.assert_awaited_once()


@pytest.mark.asyncio
async def test_threaded_resolver_propagates_fallback_failure(mocker):
    resolver = ThreadedResolver()
    first_error = socket.gaierror(socket.EAI_NONAME, "no configured addresses")
    fallback_error = socket.gaierror(socket.EAI_NONAME, "unknown hostname")
    lookup = mocker.patch.object(resolver.loop, "getaddrinfo", side_effect=[first_error, fallback_error])

    with pytest.raises(socket.gaierror) as exc_info:
        await resolver.resolve("missing.invalid", 80)

    assert exc_info.value is fallback_error
    assert lookup.await_count == 2


@pytest.mark.asyncio
async def test_threaded_resolver_close():
    resolver = ThreadedResolver()
    await resolver.close()


@pytest.mark.asyncio
async def test_async_resolver_no_aiodns():
    with patch("aiosonic.resolver.aiodns", None):
        with pytest.raises(RuntimeError, match="aiodns"):
            AsyncResolver()


@pytest.mark.asyncio
async def test_async_resolver_dns_error():
    import aiodns

    mock_resolver = MagicMock()
    mock_resolver.gethostbyname = AsyncMock(side_effect=aiodns.error.DNSError(1, "NXDOMAIN"))
    with patch("aiosonic.resolver.aiodns") as mock_aiodns:
        mock_aiodns.DNSResolver.return_value = mock_resolver
        mock_aiodns.error.DNSError = aiodns.error.DNSError
        resolver = AsyncResolver()
        with pytest.raises(OSError, match="NXDOMAIN"):
            await resolver.resolve("nonexistent.invalid", 80)


@pytest.mark.asyncio
async def test_async_resolver_empty_hosts():
    mock_resp = MagicMock()
    mock_resp.addresses = []
    mock_resolver = MagicMock()
    mock_resolver.gethostbyname = AsyncMock(return_value=mock_resp)
    with patch("aiosonic.resolver.aiodns") as mock_aiodns:
        import aiodns

        mock_aiodns.DNSResolver.return_value = mock_resolver
        mock_aiodns.error.DNSError = aiodns.error.DNSError
        resolver = AsyncResolver()
        with pytest.raises(OSError, match="DNS lookup failed"):
            await resolver.resolve("example.com", 80)


@pytest.mark.asyncio
async def test_async_resolver_close():
    mock_resolver = MagicMock()
    with patch("aiosonic.resolver.aiodns") as mock_aiodns:
        mock_aiodns.DNSResolver.return_value = mock_resolver
        resolver = AsyncResolver()
        await resolver.close()
        mock_resolver.close.assert_called_once()


@pytest.mark.asyncio
async def test_async_resolver_cancel_fallback():
    mock_resolver = MagicMock(spec=["cancel"])  # no close attribute
    with patch("aiosonic.resolver.aiodns") as mock_aiodns:
        mock_aiodns.DNSResolver.return_value = mock_resolver
        resolver = AsyncResolver()
        await resolver.close()
        mock_resolver.cancel.assert_called_once()
