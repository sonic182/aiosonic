import asyncio
import ssl

import pytest

import aiosonic
from aiosonic.connectors import TCPConnector
from aiosonic.exceptions import MissingEvent
from aiosonic.http2 import Http2Handler
from aiosonic.timeout import Timeouts


@pytest.mark.asyncio
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
async def test_get_http2(http2_serv):
    """Test simple get to node http2 server."""
    url = http2_serv
    connector = TCPConnector(timeouts=Timeouts(sock_connect=3, sock_read=4))

    async with aiosonic.HTTPClient(connector) as client:
        res = await client.get(url, verify=False)
        assert res.status_code == 200
        assert "Hello World" == await res.text()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_method_lower(http2_serv):
    """Test simple get to node http2 server."""
    url = http2_serv
    async with aiosonic.HTTPClient() as client:
        res = await client.request(url, method="get", verify=False)
        assert res.status_code == 200
        assert "Hello World" == await res.text()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
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


class WrongEvent:
    pass


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_http2_wrong_event(mocker):
    """Test json response parsing."""
    mocker.patch("aiosonic.http2.Http2Handler.__init__", lambda x: None)
    mocker.patch("aiosonic.http2.Http2Handler.h2conn")

    handler = Http2Handler()
    handler.connection = mocker.MagicMock()

    async def coro():
        pass

    with pytest.raises(MissingEvent):
        await handler.handle_events([WrongEvent])


@pytest.mark.asyncio
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
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
