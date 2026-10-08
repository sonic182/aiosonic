from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest

from aiosonic.connection import Connection
from aiosonic.exceptions import ConnectionPoolAcquireTimeout
from aiosonic.http2 import Http2Config
from aiosonic.pools import CyclicQueuePool, Http2MultiplexPool, PoolConfig, SmartPool, WsPool
from aiosonic.timeout import Timeouts
from aiosonic.utils import connection_key


def make_cyclic_pool(**kwargs):
    conf = PoolConfig(**kwargs)
    return CyclicQueuePool(conf, Connection)


def make_h2_pool():
    conf = PoolConfig()
    return Http2MultiplexPool(conf, Connection)


def make_ws_pool():
    conf = PoolConfig()
    return WsPool(conf, Connection)


def test_pool_config_hash():
    a = PoolConfig(size=10, max_conn_requests=500, max_conn_idle_ms=30000)
    b = PoolConfig(size=10, max_conn_requests=500, max_conn_idle_ms=30000)
    assert hash(a) == hash(b)
    d = {a: "value"}
    assert d[b] == "value"


def test_pool_defaults_http2_config():
    pool = CyclicQueuePool(PoolConfig(), Connection)
    assert pool.http2_config == Http2Config()


def test_pool_carries_custom_http2_config():
    custom = Http2Config(initial_window_size=123, max_streams=5)
    pool = Http2MultiplexPool(PoolConfig(), Connection, http2_config=custom)
    assert pool.http2_config is custom


def test_ws_pool_release_noop():
    pool = make_ws_pool()
    pool.release(MagicMock())


def test_ws_pool_free_conns():
    pool = make_ws_pool()
    assert pool.free_conns() == 100


def test_ws_pool_is_all_free():
    pool = make_ws_pool()
    assert pool.is_all_free() is True


@pytest.mark.asyncio
async def test_ws_pool_cleanup_noop():
    pool = make_ws_pool()
    await pool.cleanup()


def test_h2_pool_host_key_none():
    pool = make_h2_pool()
    assert pool._host_key(None) == ":default"


def test_h2_pool_host_key_no_hostname():
    pool = make_h2_pool()
    parsed = urlparse("http://")
    assert pool._host_key(parsed) == ":default"


def test_h2_pool_host_key_http():
    pool = make_h2_pool()
    parsed = urlparse("http://example.com/path")
    assert pool._host_key(parsed) == "http://example.com:80"


def test_h2_pool_host_key_https():
    pool = make_h2_pool()
    parsed = urlparse("https://example.com/path")
    assert pool._host_key(parsed) == "https://example.com:443"


def test_h2_pool_host_key_wss():
    pool = make_h2_pool()
    parsed = urlparse("wss://example.com/path")
    assert pool._host_key(parsed) == "wss://example.com:443"


def test_h2_pool_host_key_explicit_port():
    pool = make_h2_pool()
    parsed = urlparse("https://example.com:8443/path")
    assert pool._host_key(parsed) == "https://example.com:8443"


def test_h2_pool_free_conns_empty():
    pool = make_h2_pool()
    assert pool.free_conns() == 0


def test_h2_pool_is_all_free():
    pool = make_h2_pool()
    assert pool.is_all_free() is True


@pytest.mark.asyncio
async def test_h2_pool_cleanup():
    pool = make_h2_pool()
    conn = MagicMock()
    pool.connections["http://example.com:80"] = conn
    await pool.cleanup()
    conn.close.assert_called_once()
    assert pool.connections == {}


@pytest.mark.asyncio
async def test_cyclic_pool_acquire_timeout():
    pool = make_cyclic_pool(size=1)
    pool.timeouts = Timeouts(pool_acquire=0.1)
    conn = await pool.acquire()
    with pytest.raises(ConnectionPoolAcquireTimeout):
        await pool.acquire()
    pool.release(conn)


def test_connection_key_uses_scheme_and_effective_port():
    assert connection_key(urlparse("http://a.test/x")) == connection_key(urlparse("http://a.test:80/y"))
    assert connection_key(urlparse("http://a.test/")) != connection_key(urlparse("https://a.test/"))


@pytest.mark.asyncio
async def test_smart_pool_matches_connection_by_effective_port():
    pool = SmartPool(PoolConfig(size=2), Connection)
    https_conn = await pool.acquire()
    http_conn = await pool.acquire()
    https_conn.key = connection_key(urlparse("https://a.test/"))
    http_conn.key = connection_key(urlparse("http://a.test/"))
    pool.release(https_conn)
    pool.release(http_conn)

    conn = await pool.acquire(urlparse("http://a.test:80/"))

    assert conn is http_conn
    pool.release(conn)

    conn = await pool.acquire(urlparse("https://a.test:443/"))
    assert conn is https_conn
    pool.release(conn)
    assert pool.free_conns() == 2


@pytest.mark.asyncio
async def test_smart_pool_prefers_most_recently_released_connection():
    pool = SmartPool(PoolConfig(size=2), Connection)
    url = urlparse("http://a.test/")
    first = await pool.acquire(url)
    second = await pool.acquire(url)
    first.key = second.key = connection_key(url)
    pool.release(first)
    pool.release(second)

    recent = await pool.acquire(url)
    assert recent is second
    remaining = await pool.acquire(url)
    assert remaining is first
    pool.release(remaining)
    pool.release(recent)
    assert pool.free_conns() == 2


@pytest.mark.asyncio
async def test_smart_pool_preserves_destinations_when_unassigned_connections_are_available():
    """Assign spare connections before replacing another destination's connection."""
    pool = SmartPool(PoolConfig(size=2), Connection)
    first_url = urlparse("http://a.test/")
    second_url = urlparse("http://b.test/")
    first = await pool.acquire(first_url)
    first.key = connection_key(first_url)
    pool.release(first)

    second = await pool.acquire(second_url)
    assert second is not first
    second.key = connection_key(second_url)
    pool.release(second)

    reused = await pool.acquire(first_url)
    assert reused is first
    pool.release(reused)
    assert pool.free_conns() == 2


@pytest.mark.asyncio
async def test_smart_pool_reuses_connection_after_destination_changes():
    pool = SmartPool(PoolConfig(size=1), Connection)
    first_url = urlparse("http://a.test/")
    second_url = urlparse("http://b.test/")
    conn = await pool.acquire(first_url)
    conn.key = connection_key(first_url)
    pool.release(conn)

    replacement = await pool.acquire(second_url)
    assert replacement is conn
    replacement.key = connection_key(second_url)
    pool.release(replacement)

    reused = await pool.acquire(second_url)
    assert reused is replacement
    assert pool.free_conns() == 0
    pool.release(reused)
    assert pool.free_conns() == 1
