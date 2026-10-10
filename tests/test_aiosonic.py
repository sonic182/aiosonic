import asyncio
import base64
import json
import os
import platform
import sys
import tempfile
from datetime import timedelta
from http.cookies import SimpleCookie
from urllib.parse import urlparse

import pytest

import aiosonic
from aiosonic import BasicAuth, BearerAuth, HttpResponse
from aiosonic.auth import normalize_auths, resolve_auth
from aiosonic.client import HttpHeaders
from aiosonic.connection import Connection
from aiosonic.connectors import TCPConnector
from aiosonic.exceptions import (
    AiosonicError,
    ConnectionPoolAcquireTimeout,
    ConnectTimeout,
    HTTPStatusError,
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


@pytest.mark.asyncio
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
async def test_simple_get_aiodns(http_serv, mocker):
    """Test simple get with aiodns"""

    async def foo(*args):
        return mocker.MagicMock(addresses=["127.0.0.1"])

    mocker.patch("aiodns.DNSResolver.gethostbyname", new=foo)
    resolver = AsyncResolver(nameservers=["8.8.8.8", "8.8.4.4"])

    url = http_serv

    try:
        connector = aiosonic.TCPConnector(resolver=resolver)
        async with aiosonic.HTTPClient(connector) as client:
            res = await client.get(url)
            assert res.status_code == 200
            assert await res.content() == b"Hello, world"
            assert await res.text() == "Hello, world"
    finally:
        await resolver.close()


class MyConnection(Connection):
    """Connection to count keeped alives connections."""

    def __init__(self, *args, **kwargs):
        self.counter = 0
        super(MyConnection, self).__init__(*args, **kwargs)

    def keep_alive(self):
        self.keep = True
        self.counter += 1


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_keep_alive_smart_pool(http_serv):
    """Test keepalive smart pool."""
    url = http_serv
    urlparsed = urlparse(url)

    connector = TCPConnector({":default": PoolConfig(size=2)}, connection_cls=MyConnection)
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
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
async def test_get_with_params(http_serv):
    """Test get with params."""
    url = http_serv
    params = {"foo": "bar"}

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, params=params)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_get_with_params_in_url(http_serv):
    """Test get with params."""
    url = http_serv + "?foo=bar"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_get_with_params_tuple(http_serv):
    """Test get with params as tuple."""
    url = http_serv
    params = (("foo", "bar"),)

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, params=params)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_post_form_urlencoded(http_serv):
    """Test post form urlencoded."""
    url = http_serv + "/post"
    data = {"foo": "bar"}

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=data)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_post_tuple_form_urlencoded(http_serv):
    """Test post form urlencoded tuple."""
    url = http_serv + "/post"
    data = (("foo", "bar"),)

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=data)
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_post_json(http_serv):
    """Test post json."""
    url = http_serv + "/post_json"
    data = {"foo": "bar"}

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, json=data, headers=[["x-foo", "bar"]])
        assert res.status_code == 200
        assert await res.text() == "bar"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
async def test_delete(http_serv):
    """Test delete."""
    url = http_serv + "/delete"

    async with aiosonic.HTTPClient() as client:
        res = await client.delete(url)
        assert res.status_code == 200
        assert await res.text() == "deleted"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
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
        connection = mocker.MagicMock(spec=Connection(mocker.MagicMock()), connect=long_connect)
        connection.reuse.return_value = False
        return connection

    _connect = mocker.patch("aiosonic.pools.SmartPool.acquire", new=acquire)
    # _connect.return_value = long_connect()
    connector = TCPConnector(timeouts=Timeouts(sock_connect=0.2))

    with pytest.raises(ConnectTimeout):
        async with aiosonic.HTTPClient(connector) as client:
            await client.get(url)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_read_timeout(http_serv, mocker):
    """Test read timeout."""
    url = http_serv + "/slow_request"
    connector = TCPConnector(timeouts=Timeouts(sock_read=0.2))
    async with aiosonic.HTTPClient(connector) as client:
        with pytest.raises(ReadTimeout):
            await client.get(url)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
async def test_pool_acquire_timeout(http_serv, mocker):
    """Test pool acquirere timeout."""
    url = http_serv + "/slow_request"

    connector = TCPConnector({":default": PoolConfig(size=1)}, timeouts=Timeouts(pool_acquire=0.3))
    async with aiosonic.HTTPClient(connector) as client:
        with pytest.raises(ConnectionPoolAcquireTimeout):
            await asyncio.gather(
                client.get(url),
                client.get(url),
            )


@pytest.mark.asyncio
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
async def test_read_chunks_by_text_method(http_serv):
    """Test read chunks by text method."""
    url = http_serv + "/chunked"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url)
        assert res._connection
        assert res.status_code == 200
        assert await res.text() == "foobar"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_get_body_gzip(http_serv):
    """Test simple get."""
    url = http_serv + "/gzip"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, headers={"Accept-Encoding": "gzip, deflate, br"})
        content = await res.content()
        assert res.status_code == 200
        assert content == b"Hello, world"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_get_body_deflate(http_serv):
    """Test simple get."""
    url = http_serv + "/deflate"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, headers=[("Accept-Encoding", "gzip, deflate, br")])
        content = await res.content()
        assert res.status_code == 200
        assert content == b"Hello, world"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
async def test_close_connection(http_serv):
    """Test close connection."""
    url = http_serv + "/post"

    connector = TCPConnector({":default": PoolConfig(size=1)}, connection_cls=MyConnection)
    async with aiosonic.HTTPClient(connector) as client:
        res = await client.post(url, data=b"close")
        async with await connector.pools[":default"].acquire() as connection:
            assert res.status_code == 200
            assert not connection.keep
            assert await res.text() == "close"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_close_old_keeped_conn(http_serv):
    """Test close old conn."""
    url1 = http_serv
    url2 = http_serv
    connector = TCPConnector({":default": PoolConfig(size=1)}, connection_cls=MyConnection)
    async with aiosonic.HTTPClient(connector) as client:
        await client.get(url1)
        # get used writer
        async with await connector.pools[":default"].acquire() as connection:
            writer = connection.writer

        await client.get(url2)
        # check that old writer is closed
        assert not writer.is_closing()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
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

    _connect = mocker.patch("aiosonic.connectors.TCPConnector.wait_free_pool", new=long_connect)

    _connect.return_value = await long_connect()
    async with aiosonic.HTTPClient() as client:
        assert not await client.wait_requests(0)

    connector = TCPConnector(pool_cls=CyclicQueuePool)
    async with aiosonic.HTTPClient(connector) as client:
        assert not await client.wait_requests(0)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
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


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_auths_by_host(http_serv):
    """Only the hosts in auths get credentials; per request auth and url credentials take precedence."""

    async def authorization(client, url, **kwargs):
        res = await client.get(url, **kwargs)
        return json.loads(await res.text()).get("authorization")

    basic = "Basic " + base64.b64encode(b"user:pass").decode()
    url = http_serv + "/headers"
    port = urlparse(http_serv).port

    async with aiosonic.HTTPClient(auths={"127.0.0.1": ("user", "pass")}) as client:
        assert await authorization(client, url) == basic
        assert await authorization(client, url, auth=BearerAuth("tok")) == "Bearer tok"
        other = "Basic " + base64.b64encode(b"other:secret").decode()
        assert await authorization(client, url.replace("http://", "http://other:secret@")) == other

    async with aiosonic.HTTPClient(auths={"LOCALHOST": ("user", "pass")}) as client:
        assert await authorization(client, url) is None

    async with aiosonic.HTTPClient(auths={f"127.0.0.1:{port}": BearerAuth("with-port")}) as client:
        assert await authorization(client, url) == "Bearer with-port"

    async with aiosonic.HTTPClient(auths={f"127.0.0.1:{port + 1}": BearerAuth("other-port")}) as client:
        assert await authorization(client, url) is None


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_raise_for_status(http_serv):
    """raise_for_status returns the response on success and raises HTTPStatusError on 4xx/5xx."""
    assert issubclass(HTTPStatusError, AiosonicError)
    assert issubclass(ReadTimeout, AiosonicError)
    async with aiosonic.HTTPClient() as client:
        res = await client.get(http_serv)
        assert res.raise_for_status() is res
        assert res.reason == "OK"
        assert res.method == "GET"
        assert res.url == http_serv

        for code in (404, 500):
            res = await client.get(f"{http_serv}/status?code={code}")
            with pytest.raises(HTTPStatusError) as exc_info:
                res.raise_for_status()
            assert exc_info.value.response is res
            assert str(code) in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_event_hooks(http_serv):
    """Request hooks and response hooks, sync or async, run for every sent request."""
    calls = []

    def on_request(method, url, headers):
        calls.append(("request", method, url))

    async def on_response(response):
        calls.append(("response", response.status_code))

    async with aiosonic.HTTPClient(event_hooks={"request": [on_request], "response": [on_response]}) as client:
        res = await client.get(http_serv + "/get_redirect", follow=True)
        assert await res.text() == "Hello, world"

    assert [call[0] for call in calls] == ["request", "response", "request", "response"]
    assert calls[0][1] == "GET"
    assert calls[1] == ("response", 302)
    assert calls[3] == ("response", 200)

    with pytest.raises(ValueError):
        aiosonic.HTTPClient(event_hooks={"nope": []})


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_stream_content_length_body(http_serv):
    """stream reads a Content-Length body in several chunks, also decompressing it with iter_bytes."""
    async with aiosonic.HTTPClient() as client:
        async with client.stream("GET", http_serv + "/random") as res:
            chunks = [chunk async for chunk in res.iter_bytes()]
        expected = b"".join(chunks)
        assert len(chunks) > 1
        assert len(expected) == 300000

        async with client.stream("GET", http_serv + "/random_gzip") as res:
            assert b"".join([chunk async for chunk in res.iter_bytes()]) == expected

        async with client.stream("GET", http_serv + "/gzip") as res:
            assert b"".join([chunk async for chunk in res.iter_bytes()]) == b"Hello, world"

        async with client.stream("GET", http_serv + "/chunked") as res:
            assert b"".join([chunk async for chunk in res.iter_bytes()]) == b"foobar"

        assert client.connector.pools[":default"].is_all_free()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_stream_early_exit_frees_pool(http_serv):
    """Leaving a stream block before reading the body releases the connection for later requests."""
    async with aiosonic.HTTPClient() as client:
        async with client.stream("GET", http_serv + "/random") as res:
            async for _ in res.iter_bytes():
                break
        pool = client.connector.pools[":default"]
        assert pool.is_all_free()

        res = await client.get(http_serv)
        assert await res.text() == "Hello, world"
        assert pool.is_all_free()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_iter_lines(http_serv):
    """iter_lines splits on LF and CRLF."""
    async with aiosonic.HTTPClient() as client:
        async with client.stream("GET", http_serv + "/lines") as res:
            assert [line async for line in res.iter_lines()] == ["one", "two", "three"]


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_head_and_options(http_serv):
    """HEAD gives no body and does not hang, OPTIONS is sent with its method."""
    async with aiosonic.HTTPClient() as client:
        res = await client.head(http_serv)
        assert res.status_code == 405
        assert await res.content() == b""

        res = await client.options(http_serv)
        assert res.method == "OPTIONS"
        assert res.status_code == 405


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_stream_follow_redirect_releases_connections(http_serv):
    """A streamed request following a redirect does not leave the redirect hop's connection blocked."""
    async with aiosonic.HTTPClient() as client:
        async with client.stream("GET", http_serv + "/get_redirect", follow=True) as res:
            assert [chunk async for chunk in res.iter_bytes()] == [b"Hello, world"]
        assert client.connector.pools[":default"].is_all_free()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_stream_partial_read_without_aclose_discards_connection(http_serv):
    """Closing the body iterator early closes the socket so its unread bytes never reach the next request."""
    connector = TCPConnector({":default": PoolConfig(size=1)})
    async with aiosonic.HTTPClient(connector) as client:
        res = await client.request(http_serv + "/random", "GET", stream=True)
        chunks = res.iter_bytes()
        await chunks.__anext__()
        await chunks.aclose()

        res = await client.get(http_serv)
        assert await res.text() == "Hello, world"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_response_history_and_elapsed(http_serv):
    """A followed redirect leaves its responses in the history of the final response, and every one has elapsed."""
    async with aiosonic.HTTPClient() as client:
        res = await client.get(http_serv + "/get_redirect", follow=True)
        assert res.status_code == 200
        assert [hop.status_code for hop in res.history] == [302]
        assert res.history[0].headers["Location"] == "/"
        assert res.history[0].elapsed > timedelta(0)
        assert res.elapsed > timedelta(0)

        res = await client.get(http_serv)
        assert res.history == []


def test_response_links():
    """The Link headers of a response are parsed by rel, or by url when they have none."""
    response = HttpResponse()
    assert response.links == {}

    response._set_header(
        "Link", '<https://api.example/p2>; rel="next", <https://api.example/p9>; rel=last; title="end"'
    )
    response._set_header("link", "<https://api.example/doc>")

    assert response.links == {
        "next": {"url": "https://api.example/p2", "rel": "next"},
        "last": {"url": "https://api.example/p9", "rel": "last", "title": "end"},
        "https://api.example/doc": {"url": "https://api.example/doc"},
    }


@pytest.mark.asyncio
@pytest.mark.timeout(30)
@pytest.mark.skipif(sys.platform == "win32", reason="unix sockets are not available on windows")
async def test_unix_socket_connector():
    """With ``uds`` the requests go through the unix socket, keeping the host of the url in the Host header."""
    requests = []

    async def serve(reader, writer):
        while True:
            head = await reader.readuntil(b"\r\n\r\n")
            requests.append(head.decode())
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            await writer.drain()

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "s.sock")
        server = await asyncio.start_unix_server(serve, path)
        async with aiosonic.HTTPClient(TCPConnector(uds=path)) as client:
            for _ in range(2):
                res = await client.get("http://docker.invalid/ping")
                assert (res.status_code, await res.text()) == (200, "ok")
        server.close()

    assert len(requests) == 2
    assert requests[0].startswith("GET /ping HTTP/1.1\r\n") and "HOST: docker.invalid\r\n" in requests[0]


def _open_connections(connector):
    open_conns = []
    for pool in connector.pools.values():
        stored = pool.pool.values() if isinstance(pool.pool, dict) else [pool.pool._queue]
        open_conns += [conn for bucket in stored for conn in bucket if conn.reader]
    return open_conns


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_async_with_closes_only_its_own_connector(http_serv):
    """Leaving ``async with`` closes the connections of the connector the client created, not a given one."""
    async with aiosonic.HTTPClient() as client:
        await client.get(http_serv)
        own_connector = client.connector
        assert _open_connections(own_connector)
    assert not _open_connections(own_connector)

    shared_connector = TCPConnector()
    async with aiosonic.HTTPClient(shared_connector) as client:
        await client.get(http_serv)
    assert _open_connections(shared_connector)
    await shared_connector.cleanup()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
@pytest.mark.parametrize("pool_cls", [None, CyclicQueuePool])
async def test_response_in_use_survives_client_close(http_serv, pool_cls):
    """A chunked response not read yet can still be read after closing the client, and then its connection closes."""
    client = aiosonic.HTTPClient(TCPConnector(pool_cls=pool_cls))
    res = await client.get(http_serv + "/chunked")
    await client.aclose()

    assert await res.text() == "foobar"
    assert not _open_connections(client.connector)
    assert await (await client.get(http_serv)).text() == "Hello, world"
    assert _open_connections(client.connector)
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
@pytest.mark.parametrize("pool_cls", [None, CyclicQueuePool])
async def test_aclose_with_unread_stream_does_not_hang(http_serv, pool_cls):
    """Closing the client while a streamed response is unread closes its connection and keeps the client usable."""
    client = aiosonic.HTTPClient(TCPConnector({":default": PoolConfig(size=2)}, pool_cls=pool_cls))
    res = await client.request(http_serv + "/random", "GET", stream=True)

    await asyncio.wait_for(client.aclose(), 5)
    await res.aclose()

    assert not _open_connections(client.connector)
    assert await (await client.get(http_serv)).text() == "Hello, world"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_hooks_url_and_response_hook_error(http_serv):
    """Request hooks get the url without credentials and a failing response hook releases the response."""
    urls = []

    def on_request(method, url, headers):
        urls.append(url)

    def on_response(response):
        response.raise_for_status()

    async with aiosonic.HTTPClient(event_hooks={"request": [on_request], "response": [on_response]}) as client:
        await client.get(http_serv.replace("http://", "http://user:pass@") + "/headers")
        assert urls == [http_serv + "/headers"]

        with pytest.raises(HTTPStatusError):
            await client.request(http_serv + "/status?code=500", "GET", stream=True)
        assert client.connector.pools[":default"].is_all_free()

    assert aiosonic.utils.join_url("http://base", "httpbin/get") == "http://base/httpbin/get"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_stream_close_of_bodyless_response_keeps_other_request_connection(http_serv):
    """Closing a response whose connection went back to the pool does not abort the request now using it."""
    connector = TCPConnector({":default": PoolConfig(size=1)})
    async with aiosonic.HTTPClient(connector) as client:
        async with client.stream("HEAD", http_serv) as head_res:
            assert head_res.status_code == 405
            other = await client.request(http_serv + "/random", "GET", stream=True)
        assert len(await other.content()) == 300000


def test_resolve_auth_host_keys():
    """auths keys match by host, host with the default or explicit port, and IPv6 hosts with brackets."""
    auths = normalize_auths({"Example.com:443": ("a", "b"), "[::1]:8080": BearerAuth("v6"), "plain.org": ("c", "d")})

    secure = resolve_auth(None, urlparse("https://example.com/path"), auths)
    assert isinstance(secure, BasicAuth) and secure.username == "a"
    assert resolve_auth(None, urlparse("http://example.com/"), auths) is None
    assert resolve_auth(None, urlparse("http://[::1]:8080/"), auths).token == "v6"
    assert resolve_auth(None, urlparse("http://plain.org:9000/"), auths).username == "c"
    assert resolve_auth(None, urlparse("http://other.org/"), auths) is None


def test_redirect_to_other_host_drops_credentials():
    """Following a redirect to another host does not send the Authorization and Cookie headers."""
    client = aiosonic.HTTPClient()
    response = HttpResponse()
    response._set_response_initial(b"HTTP/1.1 302 Found\r\n")
    response.headers["Location"] = "http://other.example/x"
    headers = HttpHeaders({"Authorization": "Basic abc", "Cookie": "a=b", "X-Keep": "1"})

    client._handle_redirect(
        current_urlparsed=urlparse("http://first.example/"),
        headers=headers,
        response=response,
        max_redirects=5,
        method="GET",
        body=b"",
        transfer_chunked=True,
    )

    assert "Authorization" not in headers and "Cookie" not in headers
    assert headers["X-Keep"] == "1"


def _response_setting_cookie(set_cookie: str) -> HttpResponse:
    response = HttpResponse()
    response._update_cookies(("Set-Cookie", set_cookie))
    return response


def _redirect_response(status: int, location: str) -> HttpResponse:
    response = HttpResponse()
    response._set_response_initial(f"HTTP/1.1 {status} Found\r\n".encode())
    response.headers["Location"] = location
    return response


def _follow_redirect(client, headers, current_url: str, location: str):
    client._handle_redirect(
        current_urlparsed=urlparse(current_url),
        headers=headers,
        response=_redirect_response(302, location),
        max_redirects=5,
        method="GET",
        body=b"",
        transfer_chunked=True,
    )


def test_cookie_jar_merges_responses_and_sends_all_cookies():
    """Cookies of different responses are kept together and sent in one Cookie header without attributes."""
    client = aiosonic.HTTPClient(handle_cookies=True)
    client._save_new_cookies("example.com", _response_setting_cookie("a=1; Path=/; Max-Age=60"))
    client._save_new_cookies("example.com", _response_setting_cookie("b=2; Path=/"))
    headers = HttpHeaders()

    client._add_cookies_to_request("example.com", headers)

    assert headers["Cookie"] == "a=1; b=2"


def test_redirect_same_host_sends_cookies_set_by_the_redirect():
    """A cookie set by a redirect response is sent in the next hop even if the request already had cookies."""
    client = aiosonic.HTTPClient(handle_cookies=True)
    client._save_new_cookies("example.com", _response_setting_cookie("sid=old"))
    headers = HttpHeaders()
    client._add_cookies_to_request("example.com", headers)
    client._save_new_cookies("example.com", _response_setting_cookie("login=ok"))

    _follow_redirect(client, headers, "http://example.com/login", "/home")

    assert headers["Cookie"] == "sid=old; login=ok"


def test_redirect_to_other_host_sends_its_own_cookies_only():
    """After a cross host redirect the cookies of the first host are dropped and those of the new host are sent."""
    client = aiosonic.HTTPClient(handle_cookies=True)
    client.cookies_map["first.example"] = SimpleCookie("a=b")
    client.cookies_map["other.example"] = SimpleCookie("sid=xyz")
    headers = HttpHeaders({"Cookie": "a=b"})

    _follow_redirect(client, headers, "http://first.example/", "http://other.example/x")

    assert headers["Cookie"] == "sid=xyz"
