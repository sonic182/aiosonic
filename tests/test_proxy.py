"""Test proxy requests."""

import sys
from urllib.parse import urlparse

import pytest

from aiosonic import HTTPClient
from aiosonic.client import _do_request, _proxy_connect, _update_transport
from aiosonic.connectors import TCPConnector
from aiosonic.pools import PoolConfig
from aiosonic.proxy import Proxy
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
    connection.http2_request = mocker.AsyncMock(return_value=object())
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
async def test_connector_reconnects_proxy_tunnel_for_different_origin(mocker):
    """Test a proxy tunnel is closed before it is reused for another HTTPS origin."""
    connector = TCPConnector({":default": PoolConfig(size=1)}, connection_cls=TunnelTrackingConnection)
    mocker.patch.object(connector, "after_acquire", side_effect=_return_connection)

    connection = await connector.acquire(
        urlparse("http://proxy.example:8080"),
        True,
        None,
        Timeouts(),
        False,
        proxy_target=("https", "second.example", 443),
    )

    assert connection.close_calls == 1


@pytest.mark.asyncio
async def test_connector_keeps_proxy_tunnel_for_same_origin(mocker):
    """Test a proxy tunnel remains reusable for its original HTTPS origin."""
    connector = TCPConnector({":default": PoolConfig(size=1)}, connection_cls=TunnelTrackingConnection)
    mocker.patch.object(connector, "after_acquire", side_effect=_return_connection)

    connection = await connector.acquire(
        urlparse("http://proxy.example:8080"),
        True,
        None,
        Timeouts(),
        False,
        proxy_target=("https", "first.example", 443),
    )

    assert connection.close_calls == 0


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
