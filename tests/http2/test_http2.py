
import aiosonic
import pytest


@pytest.mark.asyncio
async def test_get(http2_server):
    """Get http2."""
    assert http2_server
    server = await http2_server()
    sockname = server.sockets[0].getsockname()
    url = 'https://%s:%s' % sockname

    res = await aiosonic.get(url, verify=False)
    assert res.status_code == 200
    assert await res.content() == b'Hello, world'
    assert await res.text() == 'Hello, world'
