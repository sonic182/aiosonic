"""Test proxy requests."""

import socket
import sys
from base64 import b64encode
from urllib.parse import urlparse

import pytest

from aiosonic import HTTPClient
from aiosonic.client import HttpResponse, _do_request, _proxy_connect, _update_transport
from aiosonic.connectors import TCPConnector
from aiosonic.pools import PoolConfig
from aiosonic.proxy import Proxy, proxy_from_environment
from aiosonic.timeout import Timeouts


class TunnelTrackingConnection:
    """Connection double that tracks proxy tunnel lifecycle."""

    def __init__(self, pool):
        self.pool = pool
        self.key = None
        self.proxy_connected = True
        self.proxy_target = ("https", "first.example", 443)
        self.last_released_time = None
        self.close_calls = 0

    def close(self):
        self.close_calls += 1
        self.proxy_connected = False
        self.proxy_target = None


async def _return_connection(_urlparsed, connection, *_args):
    return connection


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_proxy_request(http_serv, proxy_serv):
    """Test proxy request."""
    url = http_serv

    async with HTTPClient(proxy=Proxy(*proxy_serv)) as client:
        res = await client.get(url)
        assert await res.text() == "Hello, world"
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_https_proxy_request_passes_destination_to_connector(mocker):
    """Test HTTPS proxy requests identify the destination tunnel origin."""
    connection = mocker.MagicMock()
    connection.proxy_connected = False
    connection.h2conn = object()
    connection.__aenter__ = mocker.AsyncMock(return_value=connection)
    connection.__aexit__ = mocker.AsyncMock(return_value=False)
    connection.http2_request = mocker.AsyncMock(return_value=HttpResponse())
    connector = mocker.MagicMock()
    connector.timeouts = Timeouts()
    connector.acquire = mocker.AsyncMock(return_value=connection)
    mocker.patch("aiosonic.client._proxy_connect", new=mocker.AsyncMock())

    await _do_request(
        urlparse("https://second.example/resource"),
        lambda **_kwargs: {},
        connector,
        None,
        True,
        None,
        Timeouts(),
        proxy=Proxy("http://proxy.example:8080"),
    )

    assert connector.acquire.await_args.kwargs["proxy_target"] == ("https", "second.example", 443)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "proxy_target, close_calls",
    [
        (("https", "first.example", 443), 0),
        (("https", "second.example", 443), 1),
        (None, 1),
    ],
    ids=["same-origin", "other-origin", "plain-http"],
)
async def test_connector_reuses_proxy_tunnel_only_for_its_origin(mocker, proxy_target, close_calls):
    """Test a proxy tunnel is reused only for its HTTPS origin and closed otherwise."""
    connector = TCPConnector({":default": PoolConfig(size=1)}, connection_cls=TunnelTrackingConnection)
    mocker.patch.object(connector, "after_acquire", side_effect=_return_connection)

    connection = await connector.acquire(
        urlparse("http://proxy.example:8080"),
        True,
        None,
        Timeouts(),
        False,
        proxy_target=proxy_target,
    )

    assert connection.close_calls == close_calls


@pytest.mark.asyncio
async def test_proxy_connect_uses_destination_hostname_for_tls(mocker):
    """Test CONNECT TLS upgrade uses the destination hostname."""
    connection = mocker.MagicMock()
    connection.writer = mocker.MagicMock()
    connection.writer.drain = mocker.AsyncMock()
    connection.read = mocker.AsyncMock(return_value=b"HTTP/1.1 200 Connection established\r\n\r\n")
    connection.upgrade = mocker.AsyncMock()
    ssl_context = mocker.MagicMock()
    update_transport = None
    if sys.version_info < (3, 11):
        update_transport = mocker.patch("aiosonic.client._update_transport", new=mocker.AsyncMock())

    await _proxy_connect(
        connection,
        Proxy("http://proxy.example:8080"),
        urlparse("https://second.example/resource"),
        ssl_context,
    )

    if sys.version_info >= (3, 11):
        connection.upgrade.assert_awaited_once_with(ssl_context, server_hostname="second.example")
    else:
        update_transport.assert_awaited_once_with(connection, ssl_context, "second.example")
    assert connection.proxy_target == ("https", "second.example", 443)


@pytest.mark.asyncio
async def test_update_transport_uses_destination_hostname(mocker):
    """Test pre-3.11 TLS upgrades use the destination hostname."""
    transport = mocker.MagicMock()
    protocol = mocker.MagicMock()
    transport.get_protocol.return_value = protocol
    new_transport = mocker.MagicMock()
    new_transport.get_protocol.return_value = mocker.MagicMock()
    connection = mocker.MagicMock()
    connection.writer.transport = transport
    ssl_context = mocker.MagicMock()
    loop = mocker.MagicMock()
    loop.start_tls = mocker.AsyncMock(return_value=new_transport)
    mocker.patch("aiosonic.client.get_loop", return_value=loop)

    await _update_transport(connection, ssl_context, "second.example")

    loop.start_tls.assert_awaited_once_with(
        transport,
        protocol,
        ssl_context,
        server_side=False,
        server_hostname="second.example",
    )


def _clear_proxy_env(monkeypatch):
    for name in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.upper(), raising=False)


def test_proxy_from_environment(monkeypatch):
    """The proxy of a url comes from the environment by scheme, with its credentials, unless NO_PROXY matches."""
    _clear_proxy_env(monkeypatch)
    assert proxy_from_environment(urlparse("http://a.example/")) is None

    monkeypatch.setenv("http_proxy", "http://user:p%40ss@proxy.example:3128")
    monkeypatch.setenv("https_proxy", "secure-proxy.example:3129")
    proxy = proxy_from_environment(urlparse("http://a.example/"))
    assert (proxy.host, proxy.auth) == ("http://proxy.example:3128", b64encode(b"user:p@ss"))
    proxy = proxy_from_environment(urlparse("https://a.example/"))
    assert (proxy.host, proxy.auth) == ("http://secure-proxy.example:3129", None)

    monkeypatch.setenv("no_proxy", ".internal.example,localhost:8000")
    assert proxy_from_environment(urlparse("http://api.internal.example/")) is None
    assert proxy_from_environment(urlparse("http://localhost:8000/")) is None
    assert proxy_from_environment(urlparse("http://localhost:9000/")) is not None

    monkeypatch.delenv("http_proxy")
    monkeypatch.setenv("all_proxy", "socks5://proxy.example:1080")
    with pytest.raises(ValueError, match="socks5"):
        proxy_from_environment(urlparse("http://a.example/"))


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_trust_env_proxy(http_serv, proxy_serv, monkeypatch):
    """Proxies of the environment are only used with trust_env, NO_PROXY skips them and a given proxy wins."""
    _clear_proxy_env(monkeypatch)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        dead_proxy = f"http://127.0.0.1:{sock.getsockname()[1]}"
    monkeypatch.setenv("http_proxy", dead_proxy)

    async with HTTPClient() as client:
        assert await (await client.get(http_serv)).text() == "Hello, world"

    async with HTTPClient(trust_env=True) as client:
        with pytest.raises(OSError):
            await client.get(http_serv)

    monkeypatch.setenv("no_proxy", "127.0.0.1")
    async with HTTPClient(trust_env=True) as client:
        assert await (await client.get(http_serv)).text() == "Hello, world"

    monkeypatch.delenv("no_proxy")
    async with HTTPClient(trust_env=True, proxy=Proxy(*proxy_serv)) as client:
        assert await (await client.get(http_serv)).text() == "Hello, world"

    proxy_url, credentials = proxy_serv
    monkeypatch.setenv("http_proxy", proxy_url.replace("http://", f"http://{credentials}@"))
    async with HTTPClient(trust_env=True) as client:
        assert await (await client.get(http_serv)).text() == "Hello, world"
