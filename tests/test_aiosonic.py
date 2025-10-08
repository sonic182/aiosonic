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
    HttpParsingError,
    MaxRedirects,
    MissingEvent,
    MissingWriterException,
    ReadTimeout,
    RequestTimeout,
)
from aiosonic.http2 import Http2Handler
from aiosonic.pools import CyclicQueuePool, PoolConfig
from aiosonic.resolver import AsyncResolver
from aiosonic.timeout import Timeouts

# setup debug logger
logging.getLogger("aiosonic").setLevel(logging.DEBUG)


@pytest.mark.asyncio
async def test_simple_get(http_serv):
    """Test simple get."""
    url = http_serv

    connector = TCPConnector(timeouts=Timeouts(sock_connect=3, sock_read=4))
    async with aiosonic.HTTPClient(connector) as client:
        res = await client.get(url)
        assert res.status_code == 200
        assert await res.content() == b"Hello, world"
        assert await res.text() == "Hello, world"


@pytest.mark.asyncio
async def test_simple_get_aiodns(http_serv, mocker):
    """Test simple get with aiodns"""

    async def foo(*args):
        return mocker.MagicMock(addresses=["127.0.0.1"])

    mocker.patch("aiodns.DNSResolver.gethostbyname", new=foo)
    resolver = AsyncResolver(nameservers=["8.8.8.8", "8.8.4.4"])

    url = http_serv

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
async def test_keep_alive_smart_pool(http_serv):
    """Test keepalive smart pool."""
    url = http_serv
    urlparsed = urlparse(url)

    connector = TCPConnector(
        {":default": PoolConfig(size=2)}, connection_cls=MyConnection
    )
    async with aiosonic.HTTPClient(connector) as client:
        res = None
        for _ in range(5):
            res = await client.get(url)
        async with await connector.pools[":default"].acquire(urlparsed) as connection:
            assert res
            assert res.status_code == 200
            assert await res.text() == "Hello, world"
            assert connection.counter == 5


@pytest.mark.asyncio
async def test_keep_alive_cyclic_pool(http_serv):
    """Test keepalive cyclic pool."""
    url = http_serv

    connector = TCPConnector(
        {":default": PoolConfig(size=2)},
        connection_cls=MyConnection,
        pool_cls=CyclicQueuePool,
    )
    async with aiosonic.HTTPClient(connector) as client:
        for _ in range(5):
            res = await client.get(url)
        async with await connector.pools[":default"].acquire() as connection:
            assert res.status_code == 200
            assert await res.text() == "Hello, world"
            assert connection.counter == 2


@pytest.mark.asyncio
async def test_get_with_params(http_serv):
    """Test get with params."""
    url = http_serv
    params = {"foo": "bar"}

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, params=params)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
async def test_get_with_params_in_url(http_serv):
    """Test get with params."""
    url = http_serv + "?foo=bar"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
async def test_get_with_params_tuple(http_serv):
    """Test get with params as tuple."""
    url = http_serv
    params = (("foo", "bar"),)

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, params=params)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
async def test_post_form_urlencoded(http_serv):
    """Test post form urlencoded."""
    url = http_serv + "/post"
    data = {"foo": "bar"}

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=data)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
async def test_post_tuple_form_urlencoded(http_serv):
    """Test post form urlencoded tuple."""
    url = http_serv + "/post"
    data = (("foo", "bar"),)

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=data)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
async def test_post_json(http_serv):
    """Test post json."""
    url = http_serv + "/post_json"
    data = {"foo": "bar"}

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, json=data, headers=[["x-foo", "bar"]])
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
async def test_put_patch(http_serv):
    """Test put."""
    url = http_serv + "/put_patch"

    async with aiosonic.HTTPClient() as client:
        res = await client.put(url)
        assert res.status_code == 200
        assert await res.text() == "put_patch"

    async with aiosonic.HTTPClient() as client:
        res = await client.patch(url)
        assert res.status_code == 200
        assert await res.text() == "put_patch"


@pytest.mark.asyncio
async def test_delete(http_serv):
    """Test delete."""
    url = http_serv + "/delete"

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
async def test_read_timeout(http_serv, mocker):
    """Test read timeout."""
    url = http_serv + "/slow_request"
    connector = TCPConnector(timeouts=Timeouts(sock_read=0.2))
    async with aiosonic.HTTPClient(connector) as client:
        with pytest.raises(ReadTimeout):
            await client.get(url)


@pytest.mark.asyncio
async def test_timeouts_overriden(http_serv, mocker):
    """Test timeouts overriden."""
    url = http_serv + "/slow_request"

    # request takes 1s so this timeout should not be applied
    # instead the one provided by request call
    connector = TCPConnector(timeouts=Timeouts(sock_read=2))

    async with aiosonic.HTTPClient(connector) as client:
        response = await client.get(url)
        assert response.status_code == 200

        with pytest.raises(ReadTimeout):
            await client.get(url, timeouts=Timeouts(sock_read=0.3))


@pytest.mark.asyncio
async def test_request_timeout(http_serv, mocker):
    """Test request timeout."""
    url = http_serv + "/post_json"

    async def long_request(*_args, **_kwargs):
        await asyncio.sleep(3)

    _connect = mocker.patch("aiosonic.client._do_request", new=long_request)
    _connect.return_value = long_request()
    connector = TCPConnector(timeouts=Timeouts(request_timeout=0.2))
    async with aiosonic.HTTPClient(connector) as client:
        with pytest.raises(RequestTimeout):
            await client.get(url)


@pytest.mark.asyncio
async def test_pool_acquire_timeout(http_serv, mocker):
    """Test pool acquirere timeout."""
    url = http_serv + "/slow_request"

    connector = TCPConnector(
        {":default": PoolConfig(size=1)}, timeouts=Timeouts(pool_acquire=0.3)
    )
    async with aiosonic.HTTPClient(connector) as client:
        with pytest.raises(ConnectionPoolAcquireTimeout):
            await asyncio.gather(
                client.get(url),
                client.get(url),
            )


@pytest.mark.asyncio
async def test_simple_get_ssl(http2_serv):
    """Test simple get with https."""
    url = http2_serv

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, verify=False)
        assert res.status_code == 200
        assert await res.text() == "Hello World"


@pytest.mark.asyncio
async def test_simple_get_ssl_ctx(http2_serv):
    """Test simple get with https and ctx."""
    url = http2_serv

    ssl_context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
    )
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, ssl=ssl_context)
        assert res.status_code == 200
        assert await res.text() == "Hello World"


@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_simple_get_ssl_no_valid(http2_serv):
    """Test simple get with https no valid."""
    url = http2_serv
    async with aiosonic.HTTPClient() as client:
        with pytest.raises(ssl.SSLError):
            await client.get(url)


@pytest.mark.asyncio
async def test_get_chunked_response(http_serv):
    """Test get chunked response."""
    url = http_serv + "/chunked"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        assert res._connection
        assert res.status_code == 200

        chunks = [b"foo", b"bar"]

        async for chunk in res.read_chunks():
            assert chunk in chunks

        with pytest.raises(ConnectionError):
            assert await res.text() == ""  # chunks already readed manually


# TODO: investigate and fix a compatibility issue for PyPy
@pytest.mark.skipif(
    platform.python_implementation() == "PyPy",
    reason="this test freezes testing on PyPy",
)
@pytest.mark.asyncio
async def test_get_chunked_response_and_not_read_it(http_serv):
    """Test get chunked response and not read it.

    Also, trigger gc delete.
    """
    url = http_serv + "/chunked"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        assert client.connector.pools[":default"].free_conns(), 24
        del res
        assert client.connector.pools[":default"].free_conns(), 25

    connector = aiosonic.TCPConnector(pool_cls=CyclicQueuePool)
    async with aiosonic.HTTPClient(connector) as client:
        res = await client.get(url)
        assert client.connector.pools[":default"].free_conns(), 24
        del res
        assert client.connector.pools[":default"].free_conns(), 25


@pytest.mark.asyncio
async def test_read_chunks_by_text_method(http_serv):
    """Test read chunks by text method."""
    url = http_serv + "/chunked"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        assert res._connection
        assert res.status_code == 200
        assert await res.text() == "foobar"


@pytest.mark.asyncio
async def test_get_body_gzip(http_serv):
    """Test simple get."""
    url = http_serv + "/gzip"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, headers={"Accept-Encoding": "gzip, deflate, br"})
        content = await res.content()
        assert res.status_code == 200
        assert content == b"Hello, world"


@pytest.mark.asyncio
async def test_get_body_deflate(http_serv):
    """Test simple get."""
    url = http_serv + "/deflate"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, headers=[("Accept-Encoding", "gzip, deflate, br")])
        content = await res.content()
        assert res.status_code == 200
        assert content == b"Hello, world"


@pytest.mark.asyncio
async def test_post_chunked(http_serv):
    """Test post chunked."""
    url = http_serv + "/post"
    async with aiosonic.HTTPClient() as client:

        async def data():
            yield b"foo"
            yield b"bar"

        res = await client.post(url, data=data())
        assert res.status_code == 200
        assert await res.text() == "foobar"

        def data():
            yield b"foo"
            yield b"bar"
            yield b"a" * 14

        res = await client.post(url, data=data())
        assert res.status_code == 200
        assert await res.text() == "foobaraaaaaaaaaaaaaa"


@pytest.mark.asyncio
async def test_close_connection(http_serv):
    """Test close connection."""
    url = http_serv + "/post"

    connector = TCPConnector(
        {":default": PoolConfig(size=1)}, connection_cls=MyConnection
    )
    async with aiosonic.HTTPClient(connector) as client:
        res = await client.post(url, data=b"close")
        async with await connector.pools[":default"].acquire() as connection:
            assert res.status_code == 200
            assert not connection.keep
            assert await res.text() == "close"


@pytest.mark.asyncio
async def test_close_old_keeped_conn(http_serv):
    """Test close old conn."""
    url1 = http_serv
    url2 = http_serv
    connector = TCPConnector(
        {":default": PoolConfig(size=1)}, connection_cls=MyConnection
    )
    async with aiosonic.HTTPClient(connector) as client:
        await client.get(url1)
        # get used writer
        async with await connector.pools[":default"].acquire() as connection:
            writer = connection.writer

        await client.get(url2)
        # python 3.6 doesn't have writer.is_closing
        is_closing = getattr(writer, "is_closing", writer._transport.is_closing)

        # check that old writer is closed
        assert not is_closing()


@pytest.mark.asyncio
async def test_get_redirect(http_serv):
    """Test follow redirect."""
    url = http_serv + "/get_redirect"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        assert res.status_code == 302

        res = await client.get(url, follow=True)
        assert res.status_code == 200
        assert await res.content() == b"Hello, world"
        assert await res.text() == "Hello, world"

        url = http_serv + "/get_redirect_full"
        res = await client.get(url, follow=True)
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_max_redirects(http_serv):
    """Test simple get."""
    url = http_serv + "/max_redirects"
    async with aiosonic.HTTPClient() as client:
        with pytest.raises(MaxRedirects):
            await client.get(url, follow=True)


@pytest.mark.asyncio
async def test_sending_chunks_with_error(mocker):
    """Sending bad chunck data type."""
    conn = mocker.MagicMock()
    conn.writer = None
    mocker.patch("aiosonic.client._handle_chunk")

    def chunks_data():
        yield b"foo"

    with pytest.raises(MissingWriterException):
        await aiosonic.client._send_chunks(conn, chunks_data())

    with pytest.raises(ValueError):
        await aiosonic.client._send_chunks(conn, {})


@pytest.mark.asyncio
async def test_connection_error(mocker):
    """Connection error check."""

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
async def test_json_response_parsing():
    """Test json response parsing."""
    response = HttpResponse()
    response._set_response_initial(b"HTTP/1.1 200 OK\r\n")
    response._set_header("content-type", "application/json; charset=utf-8")
    response.body = b'{"foo": "bar"}'
    assert (await response.json()) == {"foo": "bar"}


@pytest.mark.asyncio
async def test_json_response_parsing_wrong_content_type():
    """Test json response parsing with wrong content type."""
    response = HttpResponse()
    response._set_response_initial(b"HTTP/1.1 200 OK\r\n")
    response._set_header("content-type", "text/plain")
    response.body = b'{"foo": "bar"}'
    assert (await response.json()) == {"foo": "bar"}


class WrongEvent:
    stream_id = 1


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_http2_wrong_event(mocker):
    """Test json response parsing."""
    mocker.patch("aiosonic.http2.Http2Handler.__init__", lambda x: None)
    mocker.patch("aiosonic.http2.Http2Handler.h2conn")

    handler = Http2Handler()

    async def coro():
        pass

    with pytest.raises(MissingEvent):
        await handler.handle_events([WrongEvent])


@pytest.mark.asyncio
async def test_get_no_hostname(http_serv):
    """Test simple get."""
    url = "http://:" + http_serv.split(":")[2]
    async with aiosonic.HTTPClient() as client:
        with pytest.raises(HttpParsingError):
            await client.get(url)


@pytest.mark.asyncio
async def test_wait_connections_empty(mocker):
    """Test simple get."""
    async with aiosonic.HTTPClient() as client:
        assert await client.wait_requests()

    connector = TCPConnector(pool_cls=CyclicQueuePool)
    async with aiosonic.HTTPClient(connector) as client:
        assert await client.wait_requests()


@pytest.mark.asyncio
async def test_wait_connections_busy_timeout(mocker):
    """Test simple get."""

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
async def test_get_with_cookies(http_serv):
    """Test simple get."""
    url = http_serv + "/cookies"

    connector = TCPConnector(timeouts=Timeouts(sock_connect=3, sock_read=4))
    async with aiosonic.HTTPClient(connector, handle_cookies=True) as client:
        res = await client.get(url)
        assert res.status_code == 200
        assert res.cookies

        # check if server got cookies
        res = await client.get(url)
        assert await res.text() == "Got cookies"
