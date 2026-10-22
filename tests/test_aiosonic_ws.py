import asyncio
import base64
import hashlib
import json
import re
import ssl
import struct
import sys

import pytest

from aiosonic import WebSocketClient
from aiosonic.exceptions import ConnectionDisconnected, ReadTimeout, WebSocketMessageTooBig
from aiosonic.web_socket_client import WEBSOCKET_GUID


def _raw_ws_server(frames: bytes, delay: float = 0, received: list = None):
    """Return a handler that accepts the upgrade, sends ``frames`` as they are after ``delay`` seconds, and waits for
    the client to leave. The bytes the client sends after the upgrade are appended to ``received``."""

    async def handle(reader, writer):
        request = await reader.readuntil(b"\r\n\r\n")
        key = re.search(rb"Sec-WebSocket-Key: (\S+)", request).group(1)
        accept = base64.b64encode(hashlib.sha1(key + WEBSOCKET_GUID.encode()).digest())
        writer.write(
            b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n"
        )
        await asyncio.sleep(delay)
        writer.write(frames)
        try:
            await writer.drain()
            while chunk := await reader.read(4096):
                if received is not None:
                    received.append(chunk)
        except ConnectionError:
            pass
        writer.close()

    return handle


def _client_frames(data: bytes):
    """Decode the masked frames a client sent into a list of ``(opcode, payload)``."""
    frames = []
    while data:
        opcode, length = data[0] & 0x0F, data[1] & 0x7F
        key, payload = data[2:6], bytearray(data[6 : 6 + length])
        for i in range(length):
            payload[i] ^= key[i % 4]
        frames.append((opcode, bytes(payload)))
        data = data[6 + length :]
    return frames


async def _wait_for_client_frames(received: list, count: int):
    for _ in range(100):
        frames = _client_frames(b"".join(received))
        if len(frames) >= count:
            return frames
        await asyncio.sleep(0.05)
    return _client_frames(b"".join(received))


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_connect(ws_serv):
    """Test basic WebSocket connection."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            assert ws.connected
            await ws.close()
            assert not ws.connected


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_send_receive_text(ws_serv):
    """Test sending and receiving text messages."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            await ws.send_text("Hello WebSocket")
            msg = await ws.receive_text()
            assert msg == "Echo: Hello WebSocket"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_send_receive_json(ws_serv):
    """Test sending and receiving JSON messages."""
    test_data = {"message": "Hello", "type": "greeting"}

    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            await ws.send_json(test_data)
            response = await ws.receive_text()
            response = json.loads(response.lstrip("Echo: "))
            assert response == test_data


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_send_receive_bytes(ws_serv):
    """Test sending and receiving binary messages."""
    test_bytes = b"Hello Binary WebSocket"

    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            await ws.send_bytes(test_bytes)
            response = await ws.receive_bytes()
            assert response == b"Echo binary: " + test_bytes


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_ping_pong(ws_serv):
    """Test WebSocket ping/pong functionality."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            await ws.ping()
            response = await ws.receive_pong()
            assert response is not None


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_close_codes(ws_serv):
    """Test WebSocket close with different status codes."""
    async with WebSocketClient() as client:
        ws = await client.connect(ws_serv)
        await ws.close(code=1000, reason="Normal closure")
        assert ws.close_code == 1000
        assert not ws.connected


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_receive_timeout(ws_serv):
    """Test WebSocket receive timeout."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            with pytest.raises(ReadTimeout):
                await ws.receive_text(timeout=0.1)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_concurrent_messages(ws_serv):
    """Test handling multiple concurrent messages."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            messages = ["Message 1", "Message 2", "Message 3"]
            for msg in messages:
                await ws.send_text(msg)

            received = []
            for _ in range(len(messages)):
                msg = await ws.receive_text()
                received.append(msg.replace("Echo: ", ""))

            assert sorted(received) == sorted(messages)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_subprotocol_negotiation(ws_serv):
    """Test WebSocket subprotocol negotiation."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv, subprotocols=["chat", "json"]) as ws:
            assert ws.subprotocol in ["chat", "json", None]


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_custom_headers(ws_serv):
    """Test WebSocket connection with custom headers."""
    headers = {"X-Custom-Header": "test-value", "Authorization": "Bearer token123"}

    async with WebSocketClient() as client:
        async with await client.connect(ws_serv, headers=headers) as ws:
            assert ws.connected
            # Send a message to verify connection is working
            await ws.send_text("test")
            response = await ws.receive_text()
            assert "Echo" in response


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_connect_rejects_crlf_in_headers(ws_serv):
    """Test WebSocket connect rejects CRLF injection in header values."""
    headers = {"X-Evil": "a\r\nX-Injected: 1"}

    async with WebSocketClient() as client:
        with pytest.raises(ValueError):
            await client.connect(ws_serv, headers=headers)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_drop_frames(ws_serv):
    """Test drop_frames: extra frames dropped, queue doesn't grow."""
    # Use small queues and enable drop mode.
    conn_opts = {"queue_maxsize": 2, "drop_frames": True}
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv, conn_opts=conn_opts) as ws:
            # Send three messages quickly.
            await ws.send_text("Message 1")
            await ws.send_text("Message 2")
            await ws.send_text("Message 3")
            # Allow some time for echoes to arrive.
            await asyncio.sleep(0.2)
            # Since the queue can hold at most 2 messages, we should only be able to get 2.
            messages = []
            try:
                while True:
                    msg = await asyncio.wait_for(ws.receive_text(), timeout=0.1)
                    messages.append(msg)
            except Exception:
                pass
            assert len(messages) <= 2


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_large_payload_2byte(ws_serv):
    """Send a message > 125 bytes to exercise the 2-byte extended payload length path."""
    payload = "x" * 200
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            await ws.send_text(payload)
            response = await ws.receive_text()
            assert payload in response


@pytest.mark.asyncio
@pytest.mark.timeout(30)
@pytest.mark.skipif(sys.platform == "win32", reason="large WS payload hangs on Windows")
async def test_ws_large_payload_8byte(ws_serv):
    """Send a message > 65535 bytes to exercise the 8-byte extended payload length path."""
    payload = "x" * 70000
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            await ws.send_text(payload)
            response = await ws.receive_text()
            assert payload in response


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_send_protocol_no_handler(ws_serv):
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            with pytest.raises(RuntimeError, match="No protocol handler"):
                await ws.send_protocol("data")


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_receive_protocol_no_handler(ws_serv):
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            with pytest.raises(RuntimeError, match="No protocol handler"):
                await ws.receive_protocol(timeout=0.1)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_receive_text_wrong_type(ws_serv):
    """Server echoes binary when we send bytes; calling receive_text should raise ValueError."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            await ws.send_bytes(b"binary data")
            with pytest.raises(ValueError, match="text"):
                await ws.receive_text()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_receive_bytes_wrong_type(ws_serv):
    """Server echoes text when we send text; calling receive_bytes should raise ValueError."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            await ws.send_text("hello")
            with pytest.raises(ValueError, match="binary"):
                await ws.receive_bytes()


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_ws_ssl_connect(ws_serv_ssl):
    # Create an SSL context that skips verification for testing purposes.
    ssl_ctx = ssl._create_unverified_context()
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv_ssl, ssl=ssl_ctx) as ws:
            await ws.send_text("Hello Secure WebSocket")
            msg = await ws.receive_text()
            assert msg == "Echo: Hello Secure WebSocket"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_ws_message_over_max_msg_size_closes_the_connection(ws_serv):
    """A message bigger than max_msg_size is not read: the connection is closed with code 1009 and receivers fail."""
    async with WebSocketClient() as client:
        ws = await client.connect(ws_serv, max_msg_size=1024)
        await ws.send_text("small")
        assert await ws.receive_text(timeout=5) == "Echo: small"

        pending = asyncio.ensure_future(ws.receive_text())
        await ws.send_text("x" * 2048)
        with pytest.raises(WebSocketMessageTooBig, match="max_msg_size"):
            await asyncio.wait_for(pending, timeout=5)
        with pytest.raises(WebSocketMessageTooBig):
            await ws.receive_text()
        with pytest.raises(WebSocketMessageTooBig):
            await ws.send_text("late")
        await ws.close()
        assert ws.close_code == 1009
        assert not ws.connected


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_ws_unsolicited_pongs_and_big_control_frames_are_bounded():
    """Unsolicited pongs take at most queue_maxsize slots, and a control frame over 125 bytes closes the connection."""
    frames = b"\x8a\x00" * 50 + b"\x81\x05after" + b"\x8a\x7e" + struct.pack(">H", 126) + b"p" * 126
    server = await asyncio.start_server(_raw_ws_server(frames), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server, WebSocketClient() as client:
        ws = await client.connect(f"ws://127.0.0.1:{port}/", start_keepalive=False, conn_opts={"queue_maxsize": 5})
        assert await ws.receive_text(timeout=5) == "after"
        assert ws._pong_queue.qsize() <= 5
        with pytest.raises(WebSocketMessageTooBig, match="control frame"):
            await ws.receive_text(timeout=5)
        assert ws.close_code == 1009


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_ws_pending_receivers_fail_when_the_server_closes():
    """Receivers already waiting when the server closes fail, iterating ends, and sending raises."""
    server = await asyncio.start_server(_raw_ws_server(b"\x88\x02\x03\xe8", delay=0.2), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server, WebSocketClient() as client:
        ws = await client.connect(f"ws://127.0.0.1:{port}/", start_keepalive=False)
        pending_text = asyncio.ensure_future(ws.receive_text())
        pending_pong = asyncio.ensure_future(ws.receive_pong())
        with pytest.raises(ConnectionDisconnected):
            await asyncio.wait_for(pending_text, timeout=5)
        with pytest.raises(ConnectionDisconnected):
            await asyncio.wait_for(pending_pong, timeout=5)
        assert [msg async for msg in ws] == []
        with pytest.raises(ConnectionDisconnected):
            await ws.send_text("late")
        await ws.close()


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_ws_connect_fails_when_the_server_closes_during_the_handshake():
    """A server that closes in the middle of the upgrade response makes connect raise instead of freezing the loop."""

    async def answer_101_then_close(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(answer_101_then_close, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        with pytest.raises(ConnectionError, match="closed during the handshake"):
            await WebSocketClient().connect(f"ws://127.0.0.1:{port}/", start_keepalive=False)


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_ws_server_ping_is_answered_with_a_pong_of_the_same_payload():
    """A ping from the server gets a pong with the same payload, and later messages still arrive."""
    received = []
    frames = b"\x89\x08srv-ping" + b"\x81\x05after"
    server = await asyncio.start_server(_raw_ws_server(frames, received=received), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server, WebSocketClient() as client:
        ws = await client.connect(f"ws://127.0.0.1:{port}/", start_keepalive=False)
        assert await ws.receive_text(timeout=5) == "after"
        assert await _wait_for_client_frames(received, 1) == [(0xA, b"srv-ping")]
        await ws.close()


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_ws_server_close_is_echoed_and_its_code_is_kept():
    """A Close frame from the server is sent back, close_code is the server's code, and close() adds no second one."""
    received = []
    close_payload = struct.pack(">H", 4000) + b"bye"
    frames = b"\x88\x05" + close_payload
    server = await asyncio.start_server(_raw_ws_server(frames, received=received), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server, WebSocketClient() as client:
        ws = await client.connect(f"ws://127.0.0.1:{port}/", start_keepalive=False)
        with pytest.raises(ConnectionDisconnected):
            await ws.receive_text(timeout=5)
        assert ws.close_code == 4000
        assert await _wait_for_client_frames(received, 1) == [(0x8, close_payload)]
        await ws.close()
        await asyncio.sleep(0.2)
        assert _client_frames(b"".join(received)) == [(0x8, close_payload)]
        assert ws.close_code == 4000


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_ws_fragmented_messages_are_joined_until_the_fin_frame():
    """A message split in several frames arrives whole, also when a ping comes between the fragments."""
    frames = b"\x01\x06hello " + b"\x89\x00" + b"\x80\x05world" + b"\x02\x00" + b"\x80\x03abc" + b"\x81\x05after"
    server = await asyncio.start_server(_raw_ws_server(frames), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server, WebSocketClient() as client:
        ws = await client.connect(f"ws://127.0.0.1:{port}/", start_keepalive=False)
        assert await ws.receive_text(timeout=5) == "hello world"
        assert await ws.receive_bytes(timeout=5) == b"abc"
        assert await ws.receive_text(timeout=5) == "after"
        await ws.close()


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_ws_text_message_split_inside_a_multibyte_character_is_decoded_once_complete():
    """Text is decoded only after the last fragment, so a split inside a character does not break the connection."""
    encoded = "ñandú".encode("utf-8")
    frames = b"\x01\x01" + encoded[:1] + b"\x80" + bytes([len(encoded) - 1]) + encoded[1:] + b"\x81\x05after"
    server = await asyncio.start_server(_raw_ws_server(frames), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server, WebSocketClient() as client:
        ws = await client.connect(f"ws://127.0.0.1:{port}/", start_keepalive=False)
        assert await ws.receive_text(timeout=5) == "ñandú"
        assert await ws.receive_text(timeout=5) == "after"
        await ws.close()


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_ws_fragments_over_max_msg_size_close_the_connection():
    """The size limit applies to the whole message, not only to each fragment."""
    frames = b"\x01\x08" + b"a" * 8 + b"\x00\x08" + b"b" * 8 + b"\x80\x08" + b"c" * 8
    server = await asyncio.start_server(_raw_ws_server(frames), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server, WebSocketClient() as client:
        ws = await client.connect(f"ws://127.0.0.1:{port}/", start_keepalive=False, max_msg_size=20)
        with pytest.raises(WebSocketMessageTooBig, match="max_msg_size"):
            await ws.receive_text(timeout=5)
        assert ws.close_code == 1009
