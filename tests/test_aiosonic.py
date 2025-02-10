import asyncio
import logging
import platform
import ssl
from urllib.parse import urlparse

import pytest

import aiosonic
from aiosonic import HttpResponse
from aiosonic.connection import Connection
from aiosonic.connectors import TCPConnector
from aiosonic.exceptions import (
    ConnectionPoolAcquireTimeout,
    ConnectTimeout,
    MaxRedirects,
    MissingEvent,
    MissingWriterException,
    ReadTimeout,
    RequestTimeout,
)
from aiosonic.http2 import Http2Handler
from aiosonic.multipart import MultipartForm
from aiosonic.pools import CyclicQueuePool
from aiosonic.resolver import AsyncResolver
from aiosonic.timeout import Timeouts

# setup debug logger
logging.getLogger("aiosonic").setLevel(logging.DEBUG)


@pytest.mark.asyncio
async def test_simple_get(http_serv_new):
    """Test simple get."""
    url = http_serv_new

    connector = TCPConnector(timeouts=Timeouts(sock_connect=3, sock_read=4))
    async with aiosonic.HTTPClient(connector) as client:
        res = await client.get(url)
        assert res.status_code == 200
        assert await res.content() == b"Hello, world"
        assert await res.text() == "Hello, world"


@pytest.mark.asyncio
async def test_simple_get_aiodns(http_serv_new, mocker):
    """Test simple get with aiodns"""

    async def foo(*args):
        return mocker.MagicMock(addresses=["127.0.0.1"])

    mock = mocker.patch("aiodns.DNSResolver.gethostbyname", new=foo)
    resolver = AsyncResolver(nameservers=["8.8.8.8", "8.8.4.4"])

    url = http_serv_new

    connector = aiosonic.TCPConnector(resolver=resolver)
    async with aiosonic.HTTPClient(connector) as client:
        res = await client.get(url)
        assert res.status_code == 200
        assert await res.content() == b"Hello, world"
        assert await res.text() == "Hello, world"


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_get_python(http2_serv):
    """Test simple get."""
    url = http2_serv

    connector = TCPConnector(timeouts=Timeouts(sock_connect=3, sock_read=4))
    async with aiosonic.HTTPClient(connector) as client:
        res = await client.get(
            url,
            verify=False,
            headers={
                "user-agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:70.0)"
                    " Gecko/20100101 Firefox/70.0"
                )
            },
            http2=True,
        )
        assert "Hello World" in await res.text()


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_post_http2(http2_serv):
    """Test simple post."""
    url = f"{http2_serv}/post"

    # connector = TCPConnector(timeouts=Timeouts(sock_connect=3, sock_read=4))
    connector = TCPConnector()
    async with aiosonic.HTTPClient(connector) as client:
        res = await client.post(
            url,
            json={"foo": "bar"},
            verify=False,
            http2=True,
        )
        assert "Hello World" in await res.text()


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_get_http2(http2_serv):
    """Test simple get to node http2 server."""
    url = http2_serv
    connector = TCPConnector(timeouts=Timeouts(sock_connect=3, sock_read=4))

    async with aiosonic.HTTPClient(connector) as client:
        res = await client.get(url, verify=False)
        assert res.status_code == 200
        assert "Hello World" == await res.text()


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_method_lower(http2_serv):
    """Test simple get to node http2 server."""
    url = http2_serv
    async with aiosonic.HTTPClient() as client:
        res = await client.request(url, method="get", verify=False)
        assert res.status_code == 200
        assert "Hello World" == await res.text()


class MyConnection(Connection):
    """Connection to count keeped alives connections."""

    def __init__(self, *args, **kwargs):
        self.counter = 0
        super(MyConnection, self).__init__(*args, **kwargs)

    def keep_alive(self):
        self.keep = True
        self.counter += 1


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_keep_alive_smart_pool(http_serv_new):
    """Test keepalive smart pool."""
    url = http_serv_new
    urlparsed = urlparse(url)

    connector = TCPConnector(pool_size=2, connection_cls=MyConnection)
    async with aiosonic.HTTPClient(connector) as client:
        res = None
        for _ in range(5):
            res = await client.get(url)
            await res.text()

        async with await connector.pool.acquire(urlparsed) as connection:
            assert res
            assert res.status_code == 200
            assert await res.text() == "Hello, world"
            assert connection.counter == 5


@pytest.mark.asyncio
async def test_keep_alive_cyclic_pool(http_serv_new):
    """Test keepalive cyclic pool."""
    url = http_serv_new

    connector = TCPConnector(
        pool_size=2, connection_cls=MyConnection, pool_cls=CyclicQueuePool
    )
    async with aiosonic.HTTPClient(connector) as client:
        for _ in range(5):
            res = await client.get(url)
        async with await connector.pool.acquire() as connection:
            assert res.status_code == 200
            assert await res.text() == "Hello, world"
            assert connection.counter == 2


@pytest.mark.asyncio
async def test_get_with_params(http_serv_new):
    """Test get with params."""
    url = http_serv_new
    params = {"foo": "bar"}

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, params=params)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
async def test_get_with_params_in_url(http_serv_new):
    """Test get with params."""
    url = f"{http_serv_new}?foo=bar"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
async def test_get_with_params_tuple(http_serv_new):
    """Test get with params as tuple."""
    url = http_serv_new
    params = (("foo", "bar"),)

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, params=params)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
async def test_post_form_urlencoded(http_serv_new):
    """Test post form urlencoded."""
    url = f"{http_serv_new}/post"
    data = {"foo": "bar"}

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=data)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
async def test_post_tuple_form_urlencoded(http_serv_new):
    """Test post form urlencoded tuple."""
    url = f"{http_serv_new}/post"
    data = (("foo", "bar"),)

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=data)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
async def test_post_json(http_serv_new):
    """Test post json."""
    url = f"{http_serv_new}/post_json"
    data = {"foo": "bar"}

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, json=data, headers=[["x-foo", "bar"]])
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
async def test_put_patch(http_serv_new):
    """Test put."""
    url = f"{http_serv_new}/put_patch"

    async with aiosonic.HTTPClient() as client:
        res = await client.put(url)
        assert res.status_code == 200
        assert await res.text() == "put_patch"

    async with aiosonic.HTTPClient() as client:
        res = await client.patch(url)
        assert res.status_code == 200
        assert await res.text() == "put_patch"


@pytest.mark.asyncio
async def test_delete(http_serv_new):
    """Test delete."""
    url = f"{http_serv_new}/delete"

    async with aiosonic.HTTPClient() as client:
        res = await client.delete(url)
        assert res.status_code == 200
        assert await res.text() == "deleted"


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_delete_2(http_serv):
    """Test delete."""
    url = f"{http_serv}/delete"

    async with aiosonic.HTTPClient() as client:
        res = await client.delete(url)
        assert res.status_code == 200
        assert await res.text() == "deleted"


@pytest.mark.asyncio
@pytest.mark.timeout(4)
async def test_get_keepalive(http_serv):
    """Test keepalive."""
    url = f"{http_serv}/keepalive"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        assert res.status_code == 200
        assert await res.text() == "1"

        await asyncio.sleep(2.1)

        res = await client.get(url)

        # check that sending data to closed socket doesn't send anything
        # counter doesn't get increased
        assert res.status_code == 200
        assert await res.text() == "2"


@pytest.mark.asyncio
async def test_post_multipart(http_serv):
    """Test post multipart."""
    url = f"{http_serv}/upload_file"
    data = {"foo": open("tests/files/bar.txt", "rb"), "field1": "foo"}

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=data, multipart=True)
        assert res.status_code == 200
        # assert await res.content() == b"bar\n-foo"
        assert await res.text() == "bar-foo"


@pytest.mark.asyncio
async def test_post_multipart_with_class(http_serv):
    """Test post multipart."""
    url = f"{http_serv}/upload_file"

    form = MultipartForm()
    form.add_field("foo", open("tests/files/bar.txt", "rb"), "myfile.txt")
    form.add_field("field1", "foo")

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=form)
        assert res.status_code == 200
        assert await res.text() == "bar-foo"


@pytest.mark.asyncio
async def test_connect_timeout(mocker):
    """Test connect timeout."""
    url = "http://localhost:1234"

    async def long_connect(*_args, **_kwargs):
        await asyncio.sleep(3)

    async def acquire(*_args, **_kwargs):
        return mocker.MagicMock(connect=long_connect)

    _connect = mocker.patch("aiosonic.pools.SmartPool.acquire", new=acquire)
    # _connect.return_value = long_connect()
    connector = TCPConnector(timeouts=Timeouts(sock_connect=0.2))

    with pytest.raises(ConnectTimeout):
        async with aiosonic.HTTPClient(connector) as client:
            await client.get(url)


@pytest.mark.asyncio
async def test_read_timeout(http_serv_new):
    """Test read timeout."""
    url = f"{http_serv_new}/slow_request"
    connector = TCPConnector(timeouts=Timeouts(sock_read=0.2))
    async with aiosonic.HTTPClient(connector) as client:
        with pytest.raises(ReadTimeout):
            await client.get(url)


@pytest.mark.asyncio
async def test_timeouts_overriden(http_serv_new):
    """Test timeouts overriden."""
    url = f"{http_serv_new}/slow_request"

    # request takes 1s so this timeout should not be applied
    # instead the one provided by request call
    connector = TCPConnector(timeouts=Timeouts(sock_read=2))

    async with aiosonic.HTTPClient(connector) as client:
        response = await client.get(url)
        assert response.status_code == 200

        with pytest.raises(ReadTimeout):
            await client.get(url, timeouts=Timeouts(sock_read=0.3))


@pytest.mark.asyncio
async def test_request_timeout(http_serv_new, mocker):
    """Test request timeout."""
    url = f"{http_serv_new}/post_json"

    async def long_request(*_args, **_kwargs):
        await asyncio.sleep(3)

    _connect = mocker.patch("aiosonic._do_request", new=long_request)
    _connect.return_value = long_request()
    connector = TCPConnector(timeouts=Timeouts(request_timeout=0.2))
    async with aiosonic.HTTPClient(connector) as client:
        with pytest.raises(RequestTimeout):
            await client.get(url)


@pytest.mark.asyncio
async def test_pool_acquire_timeout(http_serv_new, mocker):
    """Test pool acquire timeout."""
    url = f"{http_serv_new}/slow_request"

    connector = TCPConnector(pool_size=1, timeouts=Timeouts(pool_acquire=0.3))
    async with aiosonic.HTTPClient(connector) as client:
        with pytest.raises(ConnectionPoolAcquireTimeout):
            await asyncio.gather(
                client.get(url),
                client.get(url),
            )


@pytest.mark.asyncio
async def test_simple_get_ssl(http_serv_new, ssl_context):
    """Test simple get with https."""
    # http_serv_new is assumed to yield a URL like "https://localhost:<port>"
    url = http_serv_new

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, verify=False)
        assert res.status_code == 200
        assert await res.text() == "Hello, world"


@pytest.mark.asyncio
async def test_simple_get_ssl_ctx(app, aiohttp_server, ssl_context):
    """Test simple get with https and ctx."""
    server = await aiohttp_server(app, ssl=ssl_context)
    url = "https://localhost:%d" % server.port

    ssl_context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
    )
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, ssl=ssl_context)
        assert res.status_code == 200
        assert await res.text() == "Hello, world"
        await server.close()


@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_simple_get_ssl_no_valid(app, aiohttp_server, ssl_context):
    """Test simple get with https no valid."""
    server = await aiohttp_server(app, ssl=ssl_context)
    url = "https://localhost:%d" % server.port
    async with aiosonic.HTTPClient() as client:
        with pytest.raises(ssl.SSLError):
            await client.get(url)
        await server.close()


@pytest.mark.asyncio
async def test_get_chunked_response(http_serv_new):
    """Test get chunked response."""
    url = f"{http_serv_new}/chunked"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        assert res._connection
        assert res.status_code == 200

        chunks = [b"foo", b"bar"]
        async for chunk in res.read_chunks():
            assert chunk in chunks

        with pytest.raises(ConnectionError):
            # reading the text again should fail because the chunks were already consumed
            assert await res.text() == ""


# TODO: investigate and fix a compatibility issue for PyPy
@pytest.mark.skipif(
    platform.python_implementation() == "PyPy",
    reason="this test freezes testing on PyPy",
)
@pytest.mark.asyncio
async def test_get_chunked_response_and_not_read_it(http_serv_new):
    """Test get chunked response and not read it (and trigger gc delete)."""
    url = f"{http_serv_new}/chunked"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        # Some arbitrary assertions about free connections
        assert client.connector.pool.free_conns(), 24
        del res
        assert client.connector.pool.free_conns(), 25

    connector = aiosonic.TCPConnector(pool_cls=CyclicQueuePool)
    async with aiosonic.HTTPClient(connector) as client:
        res = await client.get(url)
        assert client.connector.pool.free_conns(), 24
        del res
        assert client.connector.pool.free_conns(), 25


@pytest.mark.asyncio
async def test_read_chunks_by_text_method(http_serv_new):
    """Test read chunks by text method."""
    url = f"{http_serv_new}/chunked"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        assert res._connection
        assert res.status_code == 200
        assert await res.text() == "foobar"


@pytest.mark.asyncio
async def test_get_body_gzip(http_serv_new):
    """Test get body gzip."""
    url = f"{http_serv_new}/gzip"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, headers={"Accept-Encoding": "gzip, deflate, br"})
        content = await res.content()
        assert res.status_code == 200
        assert content == b"Hello, world"


@pytest.mark.asyncio
async def test_get_body_deflate(http_serv_new):
    """Test get body deflate."""
    url = f"{http_serv_new}/deflate"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, headers=[("Accept-Encoding", "gzip, deflate, br")])
        content = await res.content()
        assert res.status_code == 200
        assert content == b"Hello, world"


@pytest.mark.asyncio
async def test_post_chunked(http_serv_new):
    """Test post chunked."""
    url = f"{http_serv_new}/post"
    async with aiosonic.HTTPClient() as client:

        async def data_sending():
            yield b"foo"
            yield b"bar"

        res = await client.post(url, data=data_sending())
        assert res.status_code == 200
        assert await res.text() == "foobar"

        def data_2():
            yield b"foo"
            yield b"bar"
            yield b"a" * 14

        res = await client.post(url, data=data_2())
        assert res.status_code == 200
        assert await res.text() == "foobaraaaaaaaaaaaaaa"


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_close_connection(http_serv_new):
    """Test close connection."""
    url = f"{http_serv_new}/post"

    connector = TCPConnector(pool_size=1, connection_cls=MyConnection)
    async with aiosonic.HTTPClient(connector) as client:
        res = await client.post(url, data=b"close")
        async with await connector.pool.acquire() as connection:
            assert res.status_code == 200
            assert not connection.keep
            assert await res.text() == "close"


@pytest.mark.asyncio
async def test_close_old_keeped_conn(app, aiohttp_server):
    """Test close old conn."""
    server1 = await aiohttp_server(app)
    server2 = await aiohttp_server(app)
    url1 = "http://localhost:%d" % server1.port
    url2 = "http://localhost:%d" % server2.port
    connector = TCPConnector(pool_size=1, connection_cls=MyConnection)
    async with aiosonic.HTTPClient(connector) as client:
        await client.get(url1)
        # get used writer
        async with await connector.pool.acquire() as connection:
            writer = connection.writer

        await client.get(url2)
        # python 3.6 doesn't have writer.is_closing
        is_closing = getattr(writer, "is_closing", writer._transport.is_closing)

        # check that old writer is closed
        assert is_closing()
        await server1.close()
        await server2.close()


@pytest.mark.asyncio
async def test_get_redirect(http_serv_new):
    """Test follow redirect."""
    url = f"{http_serv_new}/get_redirect"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        assert res.status_code == 302

        res = await client.get(url, follow=True)
        assert res.status_code == 200
        assert await res.content() == b"Hello, world"
        assert await res.text() == "Hello, world"

        url = f"{http_serv_new}/get_redirect_full"
        res = await client.get(url, follow=True)
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_max_redirects(http_serv_new):
    """Test max redirects."""
    url = f"{http_serv_new}/max_redirects"
    async with aiosonic.HTTPClient() as client:
        with pytest.raises(MaxRedirects):
            await client.get(url, follow=True)


@pytest.mark.asyncio
async def test_sending_chunks_with_error(mocker):
    """Sending bad chunk data type."""
    conn = mocker.MagicMock()
    conn.writer = None
    mocker.patch("aiosonic._handle_chunk")

    async def chunks_data():
        yield b"foo"

    with pytest.raises(MissingWriterException):
        await aiosonic._send_chunks(conn, chunks_data())

    with pytest.raises(ValueError):
        await aiosonic._send_chunks(conn, {})


@pytest.mark.asyncio
async def test_connection_error(mocker):
    """Test connection error check."""

    async def get_conn(*args, **kwargs):
        conn = Connection(connector)
        conn.connect = connect
        conn.writer = None
        return conn

    acquire = mocker.patch("aiosonic.TCPConnector.acquire", new=get_conn)
    connector = mocker.MagicMock(conn_max_requests=100)

    async def connect(*args, **kwargs):
        return None, None

    acquire.return_value = get_conn()
    connector.release.return_value = asyncio.Future()
    connector.release.return_value.set_result(True)

    async with aiosonic.HTTPClient() as client:
        with pytest.raises(ConnectionError):
            await client.get("http://foo")


@pytest.mark.asyncio
async def test_request_multipart_value_error():
    """Test multipart value error."""
    async with aiosonic.HTTPClient() as client:
        with pytest.raises(ValueError):
            await client.post("foo", data=b"foo", multipart=True)


@pytest.mark.asyncio
async def test_json_response_parsing():
    """Test JSON response parsing."""
    response = HttpResponse()
    response._set_response_initial(b"HTTP/1.1 200 OK\r\n")
    response._set_header("content-type", "application/json; charset=utf-8")
    response.body = b'{"foo": "bar"}'
    assert (await response.json()) == {"foo": "bar"}


class WrongEvent:
    pass


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_http2_wrong_event(mocker):
    """Test HTTP/2 wrong event handling."""
    mocker.patch("aiosonic.http2.Http2Handler.__init__", lambda x: None)
    mocker.patch("aiosonic.http2.Http2Handler.h2conn")

    handler = Http2Handler()

    async def coro():
        pass

    with pytest.raises(MissingEvent):
        await handler.handle_events([WrongEvent])


@pytest.mark.asyncio
async def test_get_no_hostname(http_serv_new):
    """Test get with a missing hostname."""
    # Use the port from the provided URL but omit the hostname.
    port = http_serv_new.split(":")[-1]
    url = f"http://:{port}"
    async with aiosonic.HTTPClient() as client:
        with pytest.raises(aiosonic.HttpParsingError):  # expected parsing error
            await client.get(url)


@pytest.mark.asyncio
async def test_wait_connections_empty(mocker):
    """Test wait_requests with an empty pool."""
    async with aiosonic.HTTPClient() as client:
        assert await client.wait_requests()

    connector = TCPConnector(pool_cls=CyclicQueuePool)
    async with aiosonic.HTTPClient(connector) as client:
        assert await client.wait_requests()


@pytest.mark.asyncio
async def test_wait_connections_busy_timeout(mocker):
    """Test wait_requests with busy connections (timeout)."""

    async def long_connect(*_args, **_kwargs):
        await asyncio.sleep(1)
        return True

    _connect = mocker.patch(
        "aiosonic.connectors.TCPConnector.wait_free_pool", new=long_connect
    )
    _connect.return_value = long_connect()
    async with aiosonic.HTTPClient() as client:
        assert not await client.wait_requests(0)

    connector = TCPConnector(pool_cls=CyclicQueuePool)
    async with aiosonic.HTTPClient(connector) as client:
        assert not await client.wait_requests(0)


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_get_image(http2_serv):
    """Test get image."""
    url = f"{http2_serv}/sample.png"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, verify=False)
        assert res.status_code == 200
        assert res.chunked
        with open("tests/sample.png", "rb") as _file:
            assert (await res.content()) == _file.read()


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_get_image_chunked(http2_serv):
    """Test get image chunked."""
    url = f"{http2_serv}/sample.png"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, verify=False)
        assert res.status_code == 200
        assert res.chunked
        filebytes = b""
        async for chunk in res.read_chunks():
            filebytes += chunk
        with open("tests/sample.png", "rb") as _file:
            assert filebytes == _file.read()


@pytest.mark.asyncio
async def test_get_with_cookies(http_serv_new):
    """Test get with cookies."""
    url = f"{http_serv_new}/cookies"

    connector = TCPConnector(timeouts=Timeouts(sock_connect=3, sock_read=4))
    async with aiosonic.HTTPClient(connector, handle_cookies=True) as client:
        res = await client.get(url)
        assert res.status_code == 200
        assert res.cookies

        # Check if server got cookies
        res = await client.get(url)
        assert await res.text() == "Got cookies"
