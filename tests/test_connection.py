import asyncio
from urllib.parse import urlparse
from unittest.mock import MagicMock

import pytest

import aiosonic
from aiosonic.connection import Connection
from aiosonic.connectors import TCPConnector
from aiosonic.exceptions import MissingReaderException, MissingWriterException
from aiosonic.pools import PoolConfig


class IdleTrackingConnection(Connection):
    """Connection class that tracks creation with unique IDs."""

    next_id = 0

    def __init__(self, pool):
        super().__init__(pool)
        self.id = IdleTrackingConnection.next_id
        IdleTrackingConnection.next_id += 1


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_max_conn_idle_ms(http_serv):
    """Test that connections idle longer than max_conn_idle_ms are closed and recreated."""
    url = http_serv

    IdleTrackingConnection.next_id = 0

    # Create a pool with a 500ms idle timeout
    pool_config = PoolConfig(size=1, max_conn_idle_ms=500)
    connector = TCPConnector({":default": pool_config}, connection_cls=IdleTrackingConnection)

    async with aiosonic.HTTPClient(connector) as client:
        # First request - creates connection #0
        res1 = await client.get(url)
        assert res1.status_code == 200
        await res1.text()

        # Check we have connection #0
        conn1_id = None
        async with await connector.pools[":default"].acquire() as conn:
            conn1_id = conn.id
        assert conn1_id == 0

        # Wait a short time (not exceeding idle timeout)
        await asyncio.sleep(0.2)

        # Second request - should reuse the same connection
        res2 = await client.get(url)
        assert res2.status_code == 200
        await res2.text()

        # Verify same connection was used
        async with await connector.pools[":default"].acquire() as conn:
            assert conn.id == conn1_id

        # Now wait longer than the idle timeout
        await asyncio.sleep(0.6)

        # Third request - should create a new connection
        res3 = await client.get(url)
        assert res3.status_code == 200
        await res3.text()

        # Verify a new connection was created
        async with await connector.pools[":default"].acquire() as conn:
            assert conn.id > conn1_id


def test_is_connected_false_before_connect():
    from aiosonic.pools import CyclicQueuePool, PoolConfig

    pool = CyclicQueuePool(PoolConfig(size=1), Connection)
    conn = Connection(pool)
    assert not conn.is_connected


@pytest.mark.asyncio
async def test_write_without_writer():
    from aiosonic.pools import CyclicQueuePool, PoolConfig

    pool = CyclicQueuePool(PoolConfig(size=1), Connection)
    conn = Connection(pool)
    with pytest.raises(MissingWriterException):
        conn.write(b"data")


@pytest.mark.asyncio
async def test_readline_without_reader():
    from aiosonic.pools import CyclicQueuePool, PoolConfig

    pool = CyclicQueuePool(PoolConfig(size=1), Connection)
    conn = Connection(pool)
    with pytest.raises(MissingReaderException):
        await conn.readline()


@pytest.mark.asyncio
async def test_readexactly_without_reader():
    from aiosonic.pools import CyclicQueuePool, PoolConfig

    pool = CyclicQueuePool(PoolConfig(size=1), Connection)
    conn = Connection(pool)
    with pytest.raises(MissingReaderException):
        await conn.readexactly(4)


@pytest.mark.asyncio
async def test_read_without_reader():
    from aiosonic.pools import CyclicQueuePool, PoolConfig

    pool = CyclicQueuePool(PoolConfig(size=1), Connection)
    conn = Connection(pool)
    with pytest.raises(MissingReaderException):
        await conn.read(4)


@pytest.mark.asyncio
async def test_readuntil_without_reader():
    from aiosonic.pools import CyclicQueuePool, PoolConfig

    pool = CyclicQueuePool(PoolConfig(size=1), Connection)
    conn = Connection(pool)
    with pytest.raises(MissingReaderException):
        await conn.readuntil(b"\n")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "expected_port", "expects_tls"),
    [
        ("https://example.com/resource", 443, True),
        ("wss://example.com/socket", 443, True),
        ("http://example.com/resource", 80, False),
        ("ws://example.com/socket", 80, False),
    ],
)
async def test_connect_uses_expected_default_port_and_tls_for_scheme(mocker, url, expected_port, expects_tls):
    from aiosonic.pools import CyclicQueuePool, PoolConfig

    pool = CyclicQueuePool(PoolConfig(size=1), Connection)
    conn = Connection(pool)
    reader = object()
    writer = MagicMock()
    writer.get_extra_info.return_value = None
    open_connection = mocker.patch(
        "aiosonic.connection.open_connection",
        new=mocker.AsyncMock(return_value=(reader, writer)),
    )

    await conn.connect(
        urlparse(url),
        {"hostname": "example.com", "family": 0, "proto": 0, "flags": 0},
        verify=True,
        ssl_context=None,
    )

    assert open_connection.await_count == 1
    kwargs = open_connection.await_args.kwargs
    assert kwargs["port"] == expected_port
    if expects_tls:
        assert kwargs["server_hostname"] == "example.com"
        assert kwargs["ssl"] is not None
    else:
        assert "server_hostname" not in kwargs
        assert kwargs["ssl"] is None
