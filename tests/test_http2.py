import asyncio
import ssl
import sys

import h2.events
import h2.settings
import pytest

import aiosonic
from aiosonic.connectors import TCPConnector
from aiosonic.exceptions import ConnectionDisconnected, MissingEvent
from aiosonic.http2 import Http2Config, Http2Handler
from aiosonic.timeout import Timeouts


# Integration tests with real HTTP2 server


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
                "user-agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:70.0) Gecko/20100101 Firefox/70.0")
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
@pytest.mark.timeout(30)
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
@pytest.mark.timeout(30)
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
async def test_h2_with_explicit_http2_flag(http2_serv):
    """Assert that http2=True explicitly negotiates HTTP/2."""
    url = http2_serv
    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, verify=False, http2=True)
        assert res.status_code == 200
        assert res.http_version == "2"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_h2_client_level_flag(http2_serv):
    """Assert that http2=True at client level applies to all requests."""
    url = http2_serv
    async with aiosonic.HTTPClient(http2=True) as client:
        res1 = await client.get(url, verify=False)
        assert res1.status_code == 200
        assert res1.http_version == "2", "Client-level http2=True must negotiate HTTP/2"

        res2 = await client.post(url, verify=False)
        assert res2.status_code == 200
        assert res2.http_version == "2", "Client-level http2=True must apply to POST too"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_h2_verify_false_applies_to_h2_ssl_context(http2_serv):
    """verify=False must disable cert verification even when http2=True.

    Bug: get_default_ssl_context returns early from the http2 branch before
    applying the verify=False override, so self-signed certs are rejected.
    """
    url = http2_serv
    async with aiosonic.HTTPClient(http2=True) as client:
        res = await client.get(url, verify=False)
        assert res.status_code == 200
        assert res.http_version == "2"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_h2_custom_ssl_ctx_gets_alpn(http2_serv):
    """A user-supplied ssl context must have 'h2' added to ALPN when http2=True.

    Bug: custom contexts passed via ssl= don't advertise h2 in ALPN, so
    the TLS handshake never negotiates h2 and the connection silently falls
    back to HTTP/1.1.
    """
    import ssl as _ssl

    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE
    url = http2_serv
    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, ssl=ctx, http2=True)
        assert res.status_code == 200
        assert res.http_version == "2"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_h2_connection_reused_across_requests(http2_serv):
    """h2conn must NOT be torn down between keep-alive requests.

    Both sequential requests on the same client must use HTTP/2 via the
    same underlying connection (h2handler kept alive across releases).
    """
    url = http2_serv
    connector = TCPConnector(timeouts=Timeouts(sock_connect=3, sock_read=4))
    async with aiosonic.HTTPClient(connector) as client:
        res1 = await client.get(url, verify=False, http2=True)
        assert res1.status_code == 200
        assert res1.http_version == "2", "First request must use HTTP/2"

        res2 = await client.get(url, verify=False, http2=True)
        assert res2.status_code == 200
        assert res2.http_version == "2", "Second request must still use HTTP/2 (connection was reused)"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_get_image(http2_serv):
    """Test get image."""
    url = f"{http2_serv}/sample.png"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, verify=False, http2=True)
        assert res.status_code == 200
        with open("tests/sample.png", "rb") as _file:
            assert (await res.content()) == _file.read()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_stream_request_body_h2(http2_serv):
    """Async-iterator request body must be sent and echoed back correctly over HTTP/2."""
    url = f"{http2_serv}/posted"

    async def body_gen():
        yield b"foo"
        yield b"bar"
        yield b"baz"

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=body_gen(), verify=False, http2=True)
        assert res.status_code == 200
        assert res.http_version == "2"
        text = await res.text()
        assert text == "foobarbaz"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_get_image_stream_h2(http2_serv):
    """HTTP/2 image download via read_chunks() must produce the same bytes as content()."""
    url = f"{http2_serv}/sample.png"

    async with aiosonic.HTTPClient() as client:
        res = await client.get(url, verify=False, http2=True)
        assert res.status_code == 200
        assert res.http_version == "2"
        assert res.chunked is True

        chunks = []
        async for chunk in res.read_chunks():
            assert isinstance(chunk, bytes)
            chunks.append(chunk)

        streamed = b"".join(chunks)

    with open("tests/sample.png", "rb") as f:
        expected = f.read()

    assert len(chunks) >= 1
    assert streamed == expected


def test_h2_custom_connector_requires_explicit_http2_flag_on_client():
    """Regression: TCPConnector(http2=True) does NOT propagate http2 to HTTPClient.

    http2=True must be passed to HTTPClient explicitly. Without it, client.http2
    stays False: ALPN never advertises h2, TLS negotiates HTTP/1.1, and
    Http2MultiplexPool's shared connection is used for HTTP/1.1 reads. Concurrent
    requests then crash with RuntimeError because asyncio StreamReader.readuntil()
    cannot be awaited by two coroutines simultaneously.
    """
    from aiosonic.pools import Http2MultiplexPool

    connector = TCPConnector(http2=True)
    assert connector.pool_cls is Http2MultiplexPool

    wrong = aiosonic.HTTPClient(connector)
    assert wrong.http2 is False, "footgun: http2 is not inferred from the connector"

    correct = aiosonic.HTTPClient(connector, http2=True)
    assert correct.http2 is True
    assert correct.connector.pool_cls is Http2MultiplexPool


@pytest.mark.asyncio
@pytest.mark.timeout(30)
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="concurrent HTTP/2 streams deadlock with WindowsSelectorEventLoopPolicy",
)
async def test_h2_multiplexing_concurrent_requests(http2_serv):
    """10 concurrent requests must all complete over a single shared TCP connection.

    Verifies two traits at once:
    - Multiplexing: parallel streams interleaved on one connection.
    - Single connection per host: Http2MultiplexPool opens exactly one TCP connection
      regardless of how many streams are in flight simultaneously.
    """
    url = http2_serv
    async with aiosonic.HTTPClient(http2=True) as client:
        responses = await asyncio.gather(*[client.get(url, verify=False) for _ in range(10)])
        texts = [await res.text() for res in responses]
        pool = client.connector.pools[":default"]

    for res, text in zip(responses, texts):
        assert res.status_code == 200
        assert res.http_version == "2"
        assert text == "Hello World"

    assert len(pool.connections) == 1


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_h2_custom_config_reaches_live_connection(http2_serv):
    """A Http2Config passed at HTTPClient creation must reach the real
    Http2Handler through HTTPClient -> TCPConnector -> pool -> Connection.

    Uses a deliberately low max_streams so the local stream semaphore actually
    throttles concurrency; requests must still all complete successfully,
    proving the setting was applied rather than silently ignored.
    """
    url = http2_serv
    config = Http2Config(max_streams=2)

    async def get_and_read():
        res = await client.get(url, verify=False)
        return res, await res.text()

    async with aiosonic.HTTPClient(http2=True, http2_config=config) as client:
        # Each task must read its own body (releasing its stream slot) rather than
        # collecting all responses first, otherwise requests 3-10 deadlock waiting
        # on a semaphore slot that only frees up once an earlier body is drained.
        results = await asyncio.gather(*[get_and_read() for _ in range(10)])
        pool = client.connector.pools[":default"]
        connection = next(iter(pool.connections.values()))

    for res, text in results:
        assert res.status_code == 200
        assert res.http_version == "2"
        assert text == "Hello World"

    assert connection.h2handler.http2_config == config
    assert connection.h2handler._max_streams == 2


@pytest.mark.asyncio
@pytest.mark.timeout(60)
@pytest.mark.skipif(sys.platform == "win32", reason="large body flow-control unreliable on Windows CI")
async def test_h2_flow_control_large_body(http2_serv):
    """POST a 1 MB body and verify the server echoes it back intact.

    Exercises the window-wait send loop in Http2Handler._send_bytes() under real
    flow-control backpressure from the Node server.
    """
    url = f"{http2_serv}/posted"
    body = b"x" * (1024 * 1024)
    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=body, verify=False, http2=True)

    assert res.status_code == 200
    assert res.http_version == "2"
    assert await res.content() == body


# Unit tests for HTTP2Handler with mocked components


@pytest.mark.asyncio
async def test_h2_handler_init_enlarges_flow_control_window(mocker):
    """__init__ must raise both the per-stream and connection-level flow-control
    window past the HTTP/2 default of 65535 bytes, otherwise download throughput
    is capped at roughly window_size / RTT (see aiosonic#579). With no explicit
    Http2Config, the Http2Config() defaults must be applied."""
    connection = mocker.MagicMock()
    connection.h2conn = mocker.MagicMock()
    connection.writer.drain = mocker.AsyncMock()
    connection.reader.read = mocker.AsyncMock(return_value=b"")

    defaults = Http2Config()
    handler = Http2Handler(connection)
    await asyncio.sleep(0)  # let the fire-and-forget reader/drain tasks run once

    connection.h2conn.update_settings.assert_called_once_with(
        {h2.settings.SettingCodes.INITIAL_WINDOW_SIZE: defaults.initial_window_size}
    )
    connection.h2conn.increment_flow_control_window.assert_called_once_with(defaults.initial_window_size)
    assert handler._max_streams == defaults.max_streams
    assert handler._stream_sem._value == defaults.max_streams

    handler.cleanup()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_h2_handler_init_uses_custom_http2_config(mocker):
    """A custom Http2Config passed at construction must override the defaults,
    so callers can tune the window size / concurrency at client creation time."""
    connection = mocker.MagicMock()
    connection.h2conn = mocker.MagicMock()
    connection.writer.drain = mocker.AsyncMock()
    connection.reader.read = mocker.AsyncMock(return_value=b"")

    custom = Http2Config(initial_window_size=123, max_streams=5)
    handler = Http2Handler(connection, custom)
    await asyncio.sleep(0)

    connection.h2conn.update_settings.assert_called_once_with(
        {h2.settings.SettingCodes.INITIAL_WINDOW_SIZE: 123}
    )
    connection.h2conn.increment_flow_control_window.assert_called_once_with(123)
    assert handler._max_streams == 5
    assert handler._stream_sem._value == 5

    handler.cleanup()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_reader_receive_data_exception(mocker):
    """If h2conn.receive_data raises, reader_t should exit gracefully."""
    # Prevent __init__ from starting tasks
    mocker.patch("aiosonic.http2.Http2Handler.__init__", lambda self: None)
    handler = Http2Handler()
    handler.loop = asyncio.get_event_loop()

    class DummyReader:
        def __init__(self):
            self._calls = 0

        async def read(self, n):
            # First call return some data, second call return b'' to stop loop
            self._calls += 1
            if self._calls == 1:
                return b"data"
            return b""

    handler.reader = DummyReader()

    class BadH2:
        def receive_data(self, data):
            raise RuntimeError("h2 failure")

    handler.h2conn = BadH2()

    # Should not raise
    await handler.reader_t()


@pytest.mark.asyncio
async def test_cleanup_cancels_reader_task(mocker):
    """cleanup() should cancel the reader_task."""
    mocker.patch("aiosonic.http2.Http2Handler.__init__", lambda self: None)
    handler = Http2Handler()
    handler.loop = asyncio.get_event_loop()

    # Create a task that waits forever
    async def sleeper():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # exit on cancel
            raise

    task = handler.loop.create_task(sleeper())
    handler.reader_task = task

    handler.cleanup()

    # Allow the loop to process the cancellation
    await asyncio.sleep(0)

    # The task should be cancelled or finished
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_send_body_waits_for_window_then_sends(mocker):
    """send_body must wait for a non-zero flow-control window before sending data.

    The sender must block while the window is 0 and only proceed once
    _window_updated is set (simulating a WindowUpdated event from the peer).
    Data must never be sent while the window is exhausted.
    """
    mocker.patch("aiosonic.http2.Http2Handler.__init__", lambda self: None)
    handler = Http2Handler()
    handler.loop = asyncio.get_event_loop()
    handler._window_updated = asyncio.Event()

    class FakeH2:
        def __init__(self):
            self.max_outbound_frame_size = 4
            self._sent = []
            self._window = 0

        def local_flow_control_window(self, stream_id):
            return self._window

        def data_to_send(self):
            return b""

        def send_headers(self, stream_id, headers, end_stream=False):
            pass

        def send_data(self, stream_id, chunk, end_stream=False):
            self._sent.append(bytes(chunk))

    fake = FakeH2()
    handler.h2conn = fake

    class DummyWriter:
        def write(self, data):
            pass

        async def drain(self):
            return None

    handler.writer = DummyWriter()

    stream_id = 1
    body = b"abcdefgh"  # 8 bytes
    handler.requests = {
        stream_id: {
            "body": body,
            "headers": [(b":method", b"POST")],
            "future": handler.loop.create_future(),
            "data_sent": False,
        }
    }

    async def open_window():
        await asyncio.sleep(0.01)
        fake._window = 65535
        handler._window_updated.set()

    await asyncio.gather(handler.send_body(stream_id), open_window())

    assert handler.requests[stream_id]["data_sent"] is True
    assert fake._sent == [b"abcd", b"efgh"]
    assert b"".join(fake._sent) == body


@pytest.mark.asyncio
async def test_concurrent_streams(mocker):
    """Send two streams concurrently and verify both complete independently."""
    mocker.patch("aiosonic.http2.Http2Handler.__init__", lambda self: None)
    handler = Http2Handler()
    handler.loop = asyncio.get_event_loop()

    class FakeH2:
        def __init__(self):
            self.max_outbound_frame_size = 4
            self._sent = []

        def local_flow_control_window(self, stream_id):
            return 65535

        def data_to_send(self):
            return b""

        def send_headers(self, stream_id, headers, end_stream=False):
            pass

        def send_data(self, stream_id, chunk, end_stream=False):
            # record (stream_id, bytes)
            self._sent.append((stream_id, bytes(chunk)))

    fake = FakeH2()
    handler.h2conn = fake

    class DummyWriter:
        def write(self, data):
            pass

        async def drain(self):
            return None

    handler.writer = DummyWriter()

    # Create two requests with different bodies
    handler.requests = {
        1: {
            "body": b"AAAAAAA",
            "headers": [(b":method", b"POST")],
            "future": handler.loop.create_future(),
            "data_sent": False,
        },
        3: {
            "body": b"BBBBBBB",
            "headers": [(b":method", b"POST")],
            "future": handler.loop.create_future(),
            "data_sent": False,
        },
    }

    # Run both senders concurrently
    await asyncio.gather(handler.send_body(1), handler.send_body(3))

    assert handler.requests[1]["data_sent"] is True
    assert handler.requests[3]["data_sent"] is True

    # Ensure both streams sent their chunks
    sent_streams = {sid: b"" for sid in (1, 3)}
    for sid, chunk in fake._sent:
        sent_streams[sid] += chunk

    assert sent_streams[1] == b"AAAAAAA"
    assert sent_streams[3] == b"BBBBBBB"


@pytest.mark.asyncio
async def test_stream_semaphore_limits_concurrency(mocker):
    """_stream_sem must block request() when max concurrent streams are in-flight."""
    mocker.patch("aiosonic.http2.Http2Handler.__init__", lambda self: None)
    handler = Http2Handler()
    handler.loop = asyncio.get_event_loop()
    handler.requests = {}
    handler._max_streams = 1
    handler._stream_sem = asyncio.Semaphore(1)

    acquired_order = []

    original_acquire = handler._stream_sem.acquire

    async def tracking_acquire():
        acquired_order.append("acquire")
        return await original_acquire()

    handler._stream_sem.acquire = tracking_acquire

    # Manually occupy the semaphore (simulates one stream in-flight)
    await handler._stream_sem.acquire()
    assert handler._stream_sem._value == 0

    # A second acquire must block until released
    released = asyncio.Event()

    async def waiter():
        await handler._stream_sem.acquire()
        released.set()
        handler._stream_sem.release()

    task = asyncio.get_event_loop().create_task(waiter())
    await asyncio.sleep(0.01)
    assert not released.is_set(), "Second acquire must block while semaphore is held"

    handler._stream_sem.release()
    await asyncio.wait_for(task, timeout=1)
    assert released.is_set(), "Second acquire must proceed after release"


@pytest.mark.asyncio
async def test_remote_settings_updates_max_streams(mocker):
    """RemoteSettingsChanged with MAX_CONCURRENT_STREAMS must update _max_streams and semaphore."""
    mocker.patch("aiosonic.http2.Http2Handler.__init__", lambda self: None)
    mocker.patch("aiosonic.http2.Http2Handler.h2conn")
    handler = Http2Handler()
    handler.loop = asyncio.get_event_loop()
    handler.connection = mocker.MagicMock()
    handler.requests = {}
    handler._max_streams = 100
    handler._stream_sem = asyncio.Semaphore(100)

    class FakeSetting:
        def __init__(self, value):
            self.new_value = value

    event = h2.events.RemoteSettingsChanged()
    event.changed_settings = {h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: FakeSetting(10)}

    await handler.handle_events([event])

    assert handler._max_streams == 10
    assert handler._stream_sem._value == 10


@pytest.mark.asyncio
async def test_disconnect_event_marks_connection_non_reusable(mocker):
    """ConnectionTerminated should fail pending streams and mark connection closing."""
    mocker.patch("aiosonic.http2.Http2Handler.__init__", lambda self, connection: None)
    handler = Http2Handler(mocker.MagicMock())
    handler.loop = asyncio.get_event_loop()
    handler.connection = mocker.MagicMock()
    handler.connection.keep = True
    handler.h2conn = mocker.MagicMock()

    fut = handler.loop.create_future()
    handler.requests = {
        1: {
            "future": fut,
            "chunk_queue": asyncio.Queue(),
            "headers": [],
            "data_sent": False,
            "send_scheduled": False,
        }
    }

    event = h2.events.ConnectionTerminated()
    await handler.handle_events([event])

    assert handler.connection.keep is False
    assert fut.done()
    assert isinstance(fut.exception(), ConnectionDisconnected)


@pytest.mark.asyncio
async def test_request_rejected_when_connection_is_closing(mocker):
    """No new streams should be accepted after disconnect has been observed."""
    mocker.patch("aiosonic.http2.Http2Handler.__init__", lambda self, connection: None)
    handler = Http2Handler(mocker.MagicMock())
    handler.loop = asyncio.get_event_loop()
    handler._max_streams = 1
    handler._stream_sem = asyncio.Semaphore(1)
    handler._closing = True

    with pytest.raises(ConnectionDisconnected):
        await handler.request([], b"")
