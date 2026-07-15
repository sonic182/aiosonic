from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest

from aiosonic.connection import Connection
from aiosonic.exceptions import ConnectionPoolAcquireTimeout
from aiosonic.http2 import Http2Config
from aiosonic.pools import CyclicQueuePool, Http2MultiplexPool, PoolConfig, WsPool
from aiosonic.timeout import Timeouts


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
