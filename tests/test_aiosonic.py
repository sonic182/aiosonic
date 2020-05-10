import asyncio
import ssl
from urllib.parse import urlparse

import pytest
import aiosonic
from aiosonic import _get_url_parsed
from aiosonic import HttpResponse
from aiosonic.connectors import TCPConnector
from aiosonic.connection import Connection
from aiosonic.exceptions import ConnectTimeout
from aiosonic.exceptions import ReadTimeout
from aiosonic.exceptions import RequestTimeout
from aiosonic.exceptions import MaxRedirects
from aiosonic.exceptions import HttpParsingError
from aiosonic.exceptions import MissingWriterException
from aiosonic.exceptions import MissingEvent
from aiosonic.exceptions import ConnectionPoolAcquireTimeout
from aiosonic.http2 import Http2Handler
from aiosonic.pools import CyclicQueuePool
from aiosonic.timeout import Timeouts


@pytest.mark.asyncio
async def test_simple_get(app, aiohttp_server):
    """Test simple get."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d' % server.port

    client = aiosonic.HTTPClient()
    res = await client.get(url)
    assert res.status_code == 200
    assert await res.content() == b'Hello, world'
    assert await res.text() == 'Hello, world'
    await server.close()


@pytest.mark.asyncio
async def test_get_python():
    """Test simple get."""
    url = 'https://www.python.org/'

    client = aiosonic.HTTPClient()
    res = await client.get(
        url,
        headers={
            'user-agent':
            ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:70.0)'
             ' Gecko/20100101 Firefox/70.0')
        },
        http2=True)
    assert res.status_code == 200
    assert '<title>Welcome to Python.org</title>' in await res.text()


@pytest.mark.asyncio
async def test_get_http2(http2_serv):
    """Test simple get to node http2 server."""
    url = http2_serv
    connector = TCPConnector(timeouts=Timeouts(sock_connect=3, sock_read=4))

    client = aiosonic.HTTPClient(connector)
    res = await client.get(url, verify=False)
    assert res.status_code == 200
    assert 'Hello World' == await res.text()


@pytest.mark.asyncio
async def test_method_lower(http2_serv):
    """Test simple get to node http2 server."""
    url = http2_serv
    client = aiosonic.HTTPClient()
    res = await client.request(url, method="get", verify=False)
    assert res.status_code == 200
    assert 'Hello World' == await res.text()


class MyConnection(Connection):
    """Connection to count keeped alives connections."""
    def __init__(self, *args, **kwargs):
        self.counter = 0
        super(MyConnection, self).__init__(*args, **kwargs)

    def keep_alive(self):
        self.keep = True
        self.counter += 1


@pytest.mark.asyncio
async def test_keep_alive_smart_pool(app, aiohttp_server):
    """Test keepalive smart pool."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d' % server.port
    urlparsed = urlparse(url)

    connector = TCPConnector(pool_size=2, connection_cls=MyConnection)
    client = aiosonic.HTTPClient(connector)

    for _ in range(5):
        res = await client.get(url)
    connection = await connector.pool.acquire(urlparsed)
    assert res.status_code == 200
    assert await res.text() == 'Hello, world'
    assert connection.counter == 5
    await server.close()


@pytest.mark.asyncio
async def test_keep_alive_cyclic_pool(app, aiohttp_server):
    """Test keepalive cyclic pool."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d' % server.port

    connector = TCPConnector(pool_size=2,
                             connection_cls=MyConnection,
                             pool_cls=CyclicQueuePool)
    client = aiosonic.HTTPClient(connector)

    for _ in range(5):
        res = await client.get(url)
    connection = await connector.pool.acquire()
    assert res.status_code == 200
    assert await res.text() == 'Hello, world'
    assert connection.counter == 2
    await server.close()


@pytest.mark.asyncio
async def test_get_with_params(app, aiohttp_server):
    """Test get with params."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d' % server.port
    params = {'foo': 'bar'}

    client = aiosonic.HTTPClient()
    res = await client.get(url, params=params)
    assert res.status_code == 200
    assert await res.text() == 'bar'
    await server.close()


@pytest.mark.asyncio
async def test_get_with_params_tuple(app, aiohttp_server):
    """Test get with params as tuple."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d' % server.port
    params = (('foo', 'bar'), )

    client = aiosonic.HTTPClient()
    res = await client.get(url, params=params)
    assert res.status_code == 200
    assert await res.text() == 'bar'
    await server.close()


@pytest.mark.asyncio
async def test_post_form_urlencoded(app, aiohttp_server):
    """Test post form urlencoded."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/post' % server.port
    data = {'foo': 'bar'}

    client = aiosonic.HTTPClient()
    res = await client.post(url, data=data)
    assert res.status_code == 200
    assert await res.text() == 'bar'
    await server.close()


@pytest.mark.asyncio
async def test_post_tuple_form_urlencoded(app, aiohttp_server):
    """Test post form urlencoded tuple."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/post' % server.port
    data = (('foo', 'bar'), )

    client = aiosonic.HTTPClient()
    res = await client.post(url, data=data)
    assert res.status_code == 200
    assert await res.text() == 'bar'
    await server.close()


@pytest.mark.asyncio
async def test_post_json(app, aiohttp_server):
    """Test post json."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/post_json' % server.port
    data = {'foo': 'bar'}

    client = aiosonic.HTTPClient()
    res = await client.post(url, json=data, headers=[['x-foo', 'bar']])
    assert res.status_code == 200
    assert await res.text() == 'bar'
    await server.close()


@pytest.mark.asyncio
async def test_put_patch(app, aiohttp_server):
    """Test put."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/put_patch' % server.port

    client = aiosonic.HTTPClient()
    res = await client.put(url)
    assert res.status_code == 200
    assert await res.text() == 'put_patch'

    client = aiosonic.HTTPClient()
    res = await client.patch(url)
    assert res.status_code == 200
    assert await res.text() == 'put_patch'
    await server.close()


@pytest.mark.asyncio
async def test_delete(app, aiohttp_server):
    """Test delete."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/delete' % server.port

    client = aiosonic.HTTPClient()
    res = await client.delete(url)
    assert res.status_code == 200
    assert await res.text() == 'deleted'
    await server.close()


@pytest.mark.asyncio
async def test_post_multipart_to_django(live_server):
    """Test post multipart."""
    url = live_server.url + '/post_file'
    data = {'foo': open('tests/files/bar.txt', 'rb'), 'field1': 'foo'}

    client = aiosonic.HTTPClient()
    res = await client.post(url, data=data, multipart=True)
    assert res.status_code == 200
    assert await res.text() == 'bar-foo'


@pytest.mark.asyncio
async def test_connect_timeout(mocker):
    """Test connect timeout."""
    url = 'http://localhost:1234'

    async def long_connect(*_args, **_kwargs):
        await asyncio.sleep(3)

    _connect = mocker.patch('aiosonic.connection.Connection._connect',
                            new=long_connect)
    _connect.return_value = long_connect()
    connector = TCPConnector(timeouts=Timeouts(sock_connect=0.2))

    with pytest.raises(ConnectTimeout):
        client = aiosonic.HTTPClient(connector)
        await client.get(url)


@pytest.mark.asyncio
async def test_read_timeout(app, aiohttp_server, mocker):
    """Test read timeout."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/slow_request' % server.port
    connector = TCPConnector(timeouts=Timeouts(sock_read=0.2))
    client = aiosonic.HTTPClient(connector)

    with pytest.raises(ReadTimeout):
        await client.get(url)
    await server.close()


@pytest.mark.asyncio
async def test_timeouts_overriden(app, aiohttp_server, mocker):
    """Test timeouts overriden."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/slow_request' % server.port

    # request takes 1s so this timeout should not be applied
    # instead the one provided by request call
    connector = TCPConnector(timeouts=Timeouts(sock_read=2))

    client = aiosonic.HTTPClient(connector)
    response = await client.get(url)
    assert response.status_code == 200

    with pytest.raises(ReadTimeout):
        await client.get(url, timeouts=Timeouts(sock_read=0.3))
    await server.close()


@pytest.mark.asyncio
async def test_request_timeout(app, aiohttp_server, mocker):
    """Test request timeout."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/post_json' % server.port

    async def long_request(*_args, **_kwargs):
        await asyncio.sleep(3)

    _connect = mocker.patch('aiosonic._do_request', new=long_request)
    _connect.return_value = long_request()
    connector = TCPConnector(timeouts=Timeouts(request_timeout=0.2))
    client = aiosonic.HTTPClient(connector)

    with pytest.raises(RequestTimeout):
        await client.get(url)
    await server.close()


@pytest.mark.asyncio
async def test_pool_acquire_timeout(app, aiohttp_server, mocker):
    """Test pool acquirere timeout."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/slow_request' % server.port

    connector = TCPConnector(pool_size=1, timeouts=Timeouts(pool_acquire=0.3))
    client = aiosonic.HTTPClient(connector)

    with pytest.raises(ConnectionPoolAcquireTimeout):
        await asyncio.gather(
            client.get(url),
            client.get(url),
        )
    await server.close()


@pytest.mark.asyncio
async def test_simple_get_ssl(app, aiohttp_server, ssl_context):
    """Test simple get with https."""
    server = await aiohttp_server(app, ssl=ssl_context)
    url = 'https://localhost:%d' % server.port

    client = aiosonic.HTTPClient()
    res = await client.get(url, verify=False)
    assert res.status_code == 200
    assert await res.text() == 'Hello, world'
    await server.close()


@pytest.mark.asyncio
async def test_simple_get_ssl_ctx(app, aiohttp_server, ssl_context):
    """Test simple get with https and ctx."""
    server = await aiohttp_server(app, ssl=ssl_context)
    url = 'https://localhost:%d' % server.port

    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, )
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    client = aiosonic.HTTPClient()
    res = await client.get(url, ssl=ssl_context)
    assert res.status_code == 200
    assert await res.text() == 'Hello, world'
    await server.close()


@pytest.mark.asyncio
async def test_simple_get_ssl_no_valid(app, aiohttp_server, ssl_context):
    """Test simple get with https no valid."""
    server = await aiohttp_server(app, ssl=ssl_context)
    url = 'https://localhost:%d' % server.port
    client = aiosonic.HTTPClient()

    # python 3.5 compatibility
    with pytest.raises(getattr(ssl, 'SSLCertVerificationError', ssl.SSLError)):
        await client.get(url)
    await server.close()


@pytest.mark.asyncio
async def test_get_chunked_response(app, aiohttp_server):
    """Test get chunked response."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/chunked' % server.port

    client = aiosonic.HTTPClient()
    res = await client.get(url)
    assert res.connection
    assert res.status_code == 200

    chunks = [b'foo', b'bar']

    async for chunk in res.read_chunks():
        assert chunk in chunks
    assert await res.text() == ''  # chunks already readed manually
    await server.close()


@pytest.mark.asyncio
async def test_read_chunks_by_text_method(app, aiohttp_server):
    """Test read chunks by text method."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/chunked' % server.port

    client = aiosonic.HTTPClient()
    res = await client.get(url)
    assert res.connection
    assert res.status_code == 200
    assert await res.text() == 'foobar'
    assert await res.text() == 'foobar'  # cached body in response object
    await server.close()


@pytest.mark.asyncio
async def test_get_body_gzip(app, aiohttp_server):
    """Test simple get."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/gzip' % server.port

    client = aiosonic.HTTPClient()
    res = await client.get(url,
                           headers={'Accept-Encoding': 'gzip, deflate, br'})
    content = await res.content()
    assert res.status_code == 200
    assert content == b'Hello, world'
    await server.close()


@pytest.mark.asyncio
async def test_get_body_deflate(app, aiohttp_server):
    """Test simple get."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/deflate' % server.port

    client = aiosonic.HTTPClient()
    res = await client.get(url,
                           headers=[('Accept-Encoding', 'gzip, deflate, br')])
    content = await res.content()
    assert res.status_code == 200
    assert content == b'Hello, world'
    await server.close()


@pytest.mark.asyncio
async def test_post_chunked(app, aiohttp_server):
    """Test post chunked."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/post' % server.port
    client = aiosonic.HTTPClient()

    async def data():
        yield b'foo'
        yield b'bar'

    res = await client.post(url, data=data())
    assert res.status_code == 200
    assert await res.text() == 'foobar'

    def data():
        yield b'foo'
        yield b'bar'
        yield b'a' * 14

    res = await client.post(url, data=data())
    assert res.status_code == 200
    assert await res.text() == 'foobaraaaaaaaaaaaaaa'
    await server.close()


@pytest.mark.asyncio
async def test_close_connection(app, aiohttp_server):
    """Test close connection."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/post' % server.port

    connector = TCPConnector(pool_size=1, connection_cls=MyConnection)
    client = aiosonic.HTTPClient(connector)

    res = await client.post(url, data=b'close')
    connection = await connector.pool.acquire()

    assert res.status_code == 200
    assert not connection.keep
    assert await res.text() == 'close'


@pytest.mark.asyncio
async def test_cache(app, aiohttp_server):
    """Test simple get."""
    server = await aiohttp_server(app)
    client = aiosonic.HTTPClient()

    for time in range(520):
        url = 'http://localhost:%d/%d' % (server.port, time)

        await client.get(url, headers={'Accept-Encoding': 'gzip, deflate, br'})
    assert len(_get_url_parsed.cache) == 512
    assert next(iter(_get_url_parsed.cache)) == url.replace('/519', '/8')
    await server.close()


@pytest.mark.asyncio
async def test_close_old_keeped_conn(app, aiohttp_server):
    """Test close old conn."""
    server1 = await aiohttp_server(app)
    server2 = await aiohttp_server(app)
    url1 = 'http://localhost:%d' % server1.port
    url2 = 'http://localhost:%d' % server2.port
    connector = TCPConnector(pool_size=1, connection_cls=MyConnection)
    client = aiosonic.HTTPClient(connector)

    await client.get(url1)
    # get used writer
    connection = await connector.pool.acquire()
    writer = connection.writer
    connection = connector.pool.release(connection)

    await client.get(url2)
    # python 3.6 doesn't have writer.is_closing
    is_closing = getattr(writer, 'is_closing', writer._transport.is_closing)

    # check that old writer is closed
    assert is_closing()
    await server1.close()
    await server2.close()


@pytest.mark.asyncio
async def test_get_redirect(app, aiohttp_server):
    """Test follow redirect."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/get_redirect' % server.port

    client = aiosonic.HTTPClient()
    res = await client.get(url)
    assert res.status_code == 302

    res = await client.get(url, follow=True)
    assert res.status_code == 200
    assert await res.content() == b'Hello, world'
    assert await res.text() == 'Hello, world'

    url = 'http://localhost:%d/get_redirect_full' % server.port
    res = await client.get(url, follow=True)
    assert res.status_code == 200

    await server.close()


@pytest.mark.asyncio
async def test_max_redirects(app, aiohttp_server):
    """Test simple get."""
    server = await aiohttp_server(app)
    url = 'http://localhost:%d/max_redirects' % server.port
    client = aiosonic.HTTPClient()

    with pytest.raises(MaxRedirects):
        await client.get(url, follow=True)
    await server.close()


def test_parse_response_line():
    """Test parsing response line"""
    response = HttpResponse()
    response._set_response_initial(b'HTTP/1.1 200 OK\r\n')
    assert response.status_code == 200


def test_parse_response_line_with_empty_reason():
    """Test parsing response line with empty reason-phrase"""
    response = HttpResponse()
    response._set_response_initial(b'HTTP/1.1 200 \r\n')
    assert response.status_code == 200


def test_parse_bad_response_line():
    """Test parsing bad response line"""
    with pytest.raises(HttpParsingError):
        HttpResponse()._set_response_initial(b'foo bar baz')


def test_handle_bad_chunk(mocker):
    """Test handling chunks in chunked request"""
    with pytest.raises(MissingWriterException):
        conn = mocker.MagicMock()
        conn.writer = None
        aiosonic._handle_chunk(b'foo', conn)


@pytest.mark.asyncio
async def test_sending_chunks_with_error(mocker):
    """Sending bad chunck data type."""
    conn = mocker.MagicMock()
    conn.writer = None
    mocker.patch('aiosonic._handle_chunk')

    def chunks_data():
        yield b'foo'

    with pytest.raises(MissingWriterException):
        await aiosonic._send_chunks(conn, chunks_data())

    with pytest.raises(ValueError):
        await aiosonic._send_chunks(conn, {})


@pytest.mark.asyncio
async def test_connection_error(mocker):
    """Connection error check."""
    async def get_conn(*args, **kwargs):
        conn = Connection(connector)
        conn.connect = connect
        conn.writer = None
        return conn

    acquire = mocker.patch('aiosonic.TCPConnector.acquire', new=get_conn)
    connector = mocker.MagicMock()

    async def connect(*args, **kwargs):
        return None, None

    acquire.return_value = get_conn()
    connector.release.return_value = asyncio.Future()
    connector.release.return_value.set_result(True)

    client = aiosonic.HTTPClient()

    with pytest.raises(ConnectionError):
        await client.get('foo')


@pytest.mark.asyncio
async def test_request_multipart_value_error():
    """Connection error check."""
    client = aiosonic.HTTPClient()
    with pytest.raises(ValueError):
        await client.post('foo', data=b'foo', multipart=True)


def test_encoding_from_header():
    """Test use encoder from header."""
    response = HttpResponse()
    response._set_response_initial(b'HTTP/1.1 200 OK\r\n')
    response._set_header('content-type', 'text/html; charset=utf-8')
    response.body = b'foo'
    assert response._get_encoding() == 'utf-8'

    response._set_header('content-type', 'application/json')
    assert response._get_encoding() == 'utf-8'

    response._set_header('content-type', 'text/html; charset=weirdencoding')
    assert response._get_encoding() == 'ascii'


@pytest.mark.asyncio
async def test_json_response_parsing():
    """Test json response parsing."""
    response = HttpResponse()
    response._set_response_initial(b'HTTP/1.1 200 OK\r\n')
    response._set_header('content-type', 'application/json; charset=utf-8')
    response.body = b'{"foo": "bar"}'
    assert (await response.json()) == {'foo': 'bar'}


class WrongEvent:
    pass


@pytest.mark.asyncio
async def test_http2_wrong_event(mocker):
    """Test json response parsing."""
    mocker.patch('aiosonic.http2.Http2Handler.__init__', lambda x: None)
    mocker.patch('aiosonic.http2.Http2Handler.h2conn')

    handler = Http2Handler()

    async def coro():
        pass

    with pytest.raises(MissingEvent):
        await handler.handle_events([WrongEvent])


@pytest.mark.asyncio
async def test_get_no_hostname(app, aiohttp_server):
    """Test simple get."""
    server = await aiohttp_server(app)
    url = 'http://:%d' % server.port
    client = aiosonic.HTTPClient()

    with pytest.raises(HttpParsingError):
        await client.get(url)
