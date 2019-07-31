
import asyncio

import pytest
import aiosonic
from aiosonic.exceptions import ConnectTimeout
from aiosonic.exceptions import RequestTimeout
from aiosonic.connectors import TCPConnector
from aiosonic.connectors import Connection


@pytest.mark.asyncio
async def test_simple_get(app, aiohttp_server):
    """Test simple get."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d' % server.port

    res = await aiosonic.get(url)
    assert res.status_code == 200
    assert res.body == b'Hello, world'
    await server.close()


class MyConnection(Connection):
    """Connection to count keeped alives connections."""

    def __init__(self, *args, **kwargs):
        self.counter = 0
        super(MyConnection, self).__init__(*args, **kwargs)

    def keep_alive(self):
        self.keep = True
        self.counter += 1


@pytest.mark.asyncio
async def test_simple_get_keep_alive(app, aiohttp_server):
    """Test simple get keepalive."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d' % server.port

    connector = TCPConnector(
        pool_size=1, connection_cls=MyConnection)

    for _ in range(5):
        res = await aiosonic.get(url, connector=connector)
    connection = await connector.pool.get()
    assert res.status_code == 200
    assert res.body == b'Hello, world'
    assert connection.counter == 5
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
async def test_post_multipart_to_django(live_server):
    """Test post multipart."""
    url = live_server.url + '/post_file'
    data = {
        'foo': open('tests/files/bar.txt', 'rb')
    }

    res = await aiosonic.post(url, data=data, multipart=True)
    assert res.status_code == 200
    assert res.body == b'bar'


@pytest.mark.asyncio
async def test_connect_timeout(mocker):
    """Test connect timeout."""
    url = 'http://localhost:1234'

    async def long_connect(*_args, **_kwargs):
        await asyncio.sleep(3)

    _connect = mocker.patch('aiosonic.connectors.Connection._connect')
    _connect.return_value = long_connect()

    with pytest.raises(ConnectTimeout):
        await aiosonic.get(
            url, connector=TCPConnector(connect_timeout=0.2))


@pytest.mark.asyncio
async def test_request_timeout(app, aiohttp_server, mocker):
    """Test request timeout."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/post_json' % server.port

    async def long_request(*_args, **_kwargs):
        await asyncio.sleep(3)

    _connect = mocker.patch('aiosonic._do_request')
    _connect.return_value = long_request()

    with pytest.raises(RequestTimeout):
        await aiosonic.get(
            url, connector=TCPConnector(request_timeout=0.2))
