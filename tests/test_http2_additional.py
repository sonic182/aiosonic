import asyncio

import pytest

from aiosonic.http2 import Http2Handler


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
async def test_send_body_flow_control_fallback(mocker, monkeypatch):
    """When window is zero and wait_for times out, send_body falls back to max frame size."""
    mocker.patch("aiosonic.http2.Http2Handler.__init__", lambda self: None)
    handler = Http2Handler()
    handler.loop = asyncio.get_event_loop()

    # Prepare a fake h2conn
    class FakeH2:
        def __init__(self):
            self.max_outbound_frame_size = 4
            self._sent = []

        def local_flow_control_window(self, stream_id):
            return 0

        def data_to_send(self):
            return b""

        def send_headers(self, stream_id, headers, end_stream=False):
            # no-op
            pass

        def send_data(self, stream_id, chunk, end_stream=False):
            self._sent.append(bytes(chunk))

    fake = FakeH2()
    handler.h2conn = fake

    # stub writer to avoid actual IO
    class DummyWriter:
        def write(self, data):
            pass

        async def drain(self):
            return None

    handler.writer = DummyWriter()

    # create request with body larger than max_outbound_frame_size
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

    # Make asyncio.wait_for raise immediately to trigger fallback
    def fake_wait_for(coro, timeout):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    await handler.send_body(stream_id)

    assert handler.requests[stream_id]["data_sent"] is True
    # Expect data to be sent in chunks of at most 4 bytes
    assert fake._sent == [b"abcd", b"efgh"]


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
