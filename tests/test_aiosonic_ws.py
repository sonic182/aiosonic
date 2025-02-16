import asyncio
import json
import ssl

import pytest

from aiosonic import WebSocketClient
from aiosonic.exceptions import ReadTimeout


@pytest.mark.asyncio
async def test_ws_connect(ws_serv):
    """Test basic WebSocket connection."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            assert ws.connected
            await ws.close()
            assert not ws.connected


@pytest.mark.asyncio
async def test_ws_send_receive_text(ws_serv):
    """Test sending and receiving text messages."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            await ws.send_text("Hello WebSocket")
            msg = await ws.receive_text()
            assert msg == "Echo: Hello WebSocket"


@pytest.mark.asyncio
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
async def test_ws_send_receive_bytes(ws_serv):
    """Test sending and receiving binary messages."""
    test_bytes = b"Hello Binary WebSocket"

    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            await ws.send_bytes(test_bytes)
            response = await ws.receive_bytes()
            assert response == b"Echo binary: " + test_bytes


@pytest.mark.asyncio
async def test_ws_ping_pong(ws_serv):
    """Test WebSocket ping/pong functionality."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            await ws.ping()
            response = await ws.receive_pong()
            assert response is not None


@pytest.mark.asyncio
async def test_ws_close_codes(ws_serv):
    """Test WebSocket close with different status codes."""
    async with WebSocketClient() as client:
        ws = await client.connect(ws_serv)
        await ws.close(code=1000, reason="Normal closure")
        assert ws.close_code == 1000
        assert not ws.connected


@pytest.mark.asyncio
async def test_ws_receive_timeout(ws_serv):
    """Test WebSocket receive timeout."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv) as ws:
            with pytest.raises(ReadTimeout):
                await ws.receive_text(timeout=0.1)


@pytest.mark.asyncio
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
async def test_ws_subprotocol_negotiation(ws_serv):
    """Test WebSocket subprotocol negotiation."""
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv, subprotocols=["chat", "json"]) as ws:
            assert ws.subprotocol in ["chat", "json", None]


@pytest.mark.asyncio
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
async def test_ws_drop_frames(ws_serv):
    """Test that with drop_frames enabled, extra frames are dropped (queue does not grow indefinitely)."""
    # Use small queues and enable drop mode.
    conn_opts = {"text_queue_maxsize": 2, "drop_frames": True}
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
@pytest.mark.timeout(5)
async def test_ws_ssl_connect(ws_serv_ssl):
    # Create an SSL context that skips verification for testing purposes.
    ssl_ctx = ssl._create_unverified_context()
    async with WebSocketClient() as client:
        async with await client.connect(ws_serv_ssl, ssl=ssl_ctx) as ws:
            await ws.send_text("Hello Secure WebSocket")
            msg = await ws.receive_text()
            assert msg == "Echo: Hello Secure WebSocket"
