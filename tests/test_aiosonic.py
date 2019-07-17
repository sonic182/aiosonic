
import pytest
import aiosonic


@pytest.mark.asyncio
async def test_do_load_test_sample_server(app, aiohttp_server):
    """Do load test to sample server."""
    server = await aiohttp_server(app)
    url = 'http://localhost:{}'.format(server.port)

    res = await aiosonic.get(url)
    assert res.status_code == 200
    assert res.body == b'Hello, world'
    await server.close()
