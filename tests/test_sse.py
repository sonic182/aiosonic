import asyncio
import pytest

from aiosonic import SSEClient
from aiosonic.exceptions import SSEConnectionError, SSEParsingError


@pytest.mark.asyncio
async def test_sse_connection(sse_serv):
    """Test basic SSE connection and event parsing."""
    client = SSEClient()
    async with client.connect(sse_serv) as sse_conn:
        events = []
        async for event in sse_conn:
            events.append(event)
            if len(events) == 3:  # Expecting 3 events from the test server
                break

        assert len(events) == 3
        assert events[0]["data"] == "hello"
        assert events[0]["event"] == "message"
        assert events[0]["id"] == "1"
        assert events[1]["data"] == "world"
        assert events[1]["event"] == "message"
        assert events[1]["id"] == "2"
        assert events[2]["data"] == "test data\nwith two lines"
        assert events[2]["event"] == "custom"
        assert events[2]["id"] == "3"


@pytest.mark.asyncio
async def test_sse_reconnection(sse_serv_reconnect):
    """Test SSE client with reconnection logic."""
    client = SSEClient()
    # The test server will close the connection after 1 event, then reconnect
    sse_conn = await client.connect(sse_serv_reconnect, reconnect=True, retry_delay=100)

    events = []
    async for event in sse_conn:
        events.append(event)
        if len(events) == 2:  # Expecting 2 events after reconnection
            break

    assert len(events) == 2
    assert events[0]["data"] == "event 1"
    assert events[1]["data"] == "event 2"


@pytest.mark.asyncio
async def test_sse_no_reconnection(sse_serv_reconnect):
    """Test SSE client without reconnection logic."""
    client = SSEClient()
    with pytest.raises(SSEConnectionError):
        await client.connect(sse_serv_reconnect, reconnect=False)


@pytest.mark.asyncio
async def test_sse_parsing_error(sse_serv_malformed):
    """Test SSE client with malformed events."""
    client = SSEClient()
    sse_conn = await client.connect(sse_serv_malformed)

    with pytest.raises(SSEParsingError):
        async for _ in sse_conn:
            pass


@pytest.mark.asyncio
async def test_sse_connection_error(http_serv):
    """Test SSE client with a non-SSE endpoint."""
    client = SSEClient()
    with pytest.raises(SSEConnectionError):
        await client.connect(http_serv)
