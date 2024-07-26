"""Test proxy requests."""

import pytest

from aiosonic import HTTPClient
from aiosonic.proxy import Proxy


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_proxy_request(app, aiohttp_server, proxy_serv):
    """Test proxy request."""
    server = await aiohttp_server(app)

    url = f"http://localhost:{server.port}"

    async with HTTPClient(proxy=Proxy(*proxy_serv)) as client:
        res = await client.get(url)
        assert await res.text() == "Hello, world"
        assert res.status_code == 200
        await server.close()
