from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiosonic.resolver import AsyncResolver, ThreadedResolver


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
