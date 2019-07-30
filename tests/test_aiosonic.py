
import pytest
import aiosonic
from aiohttp import ClientSession


@pytest.mark.asyncio
async def test_do_load_test_sample_server(app, aiohttp_server):
    """Test simple get."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d' % server.port

    res = await aiosonic.get(url)
    assert res.status_code == 200
    assert res.body == b'Hello, world'
    await server.close()


@pytest.mark.asyncio
async def test_get_with_params(app, aiohttp_server):
    """Test get with params."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d' % server.port
    params = {'foo': 'bar'}

    res = await aiosonic.get(url, params=params)
    assert res.status_code == 200
    assert res.body == b'bar'
    await server.close()


@pytest.mark.asyncio
async def test_get_with_params_tuple(app, aiohttp_server):
    """Test get with params as tuple."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d' % server.port
    params = (('foo', 'bar'), )

    res = await aiosonic.get(url, params=params)
    assert res.status_code == 200
    assert res.body == b'bar'
    await server.close()


@pytest.mark.asyncio
async def test_post_form_urlencoded(app, aiohttp_server):
    """Test post form urlencoded."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/post' % server.port
    data = {
        'foo': 'bar'
    }

    res = await aiosonic.post(url, data=data)
    assert res.status_code == 200
    assert res.body == b'bar'
    await server.close()


@pytest.mark.asyncio
async def test_post_json(app, aiohttp_server):
    """Test post json."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/post_json' % server.port
    data = {
        'foo': 'bar'
    }

    res = await aiosonic.post(url, json=data)
    assert res.status_code == 200
    assert res.body == b'bar'
    await server.close()


@pytest.mark.asyncio
async def test_post_multipart_aiohttp(app, aiohttp_server):
    """Test post multipart."""
    server = await aiohttp_server(app, port=9000)
    # url = 'http://localhost:%d/post_file' % server.port
    url = 'http://127.0.0.1:%d/post_file' % 9001
    data = {
        'foo': open('tests/files/bar.txt', 'rb')
    }

    # url = 'http://httpbin.org/post'
    # files = {'file': open('report.xls', 'rb')}

    async with ClientSession() as session:
        res = await session.post(url, data=data)

    # res = await aiosonic.post(url, data=data, multipart=True)
    ## print('res.body')
    ## print(res.body)
    ## assert res.status_code == 200
    ## assert res.body == b'bar'
    assert False
    await server.close()


@pytest.mark.asyncio
async def test_post_multipart(app, aiohttp_server):
    """Test post multipart."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/post_file' % server.port
    data = {
        'foo': open('tests/files/bar.txt', 'rb')
    }

    res = await aiosonic.post(url, data=data, multipart=True)
    print('res.body')
    print(res.body)
    assert res.status_code == 200
    assert res.body == b'bar'
    await server.close()
