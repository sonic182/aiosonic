import asyncio

import pytest

import aiosonic
from aiosonic.connection import Connection
from aiosonic.connectors import TCPConnector
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
    connector = TCPConnector(
        {":default": pool_config}, connection_cls=IdleTrackingConnection
    )

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
