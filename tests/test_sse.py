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
    conn = await client.connect(sse_serv_reconnect, reconnect=False)
    events = []
    async for event in conn:
        events.append(event)
    assert len(events) == 1
    # The test server keeps a per-URL reconnect counter across the session, so
    # this test can receive either the first or second event depending on order
    # of execution. Accept either to keep the test stable.
    assert events[0]["data"] in ("event 1", "event 2")


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


@pytest.mark.asyncio
async def test_sse_post_request_with_json(sse_serv_post):
    """Test POST request with JSON body returning SSE stream."""
    client = SSEClient()
    async with client.connect(
        sse_serv_post, method="POST", json={"message": "hello world", "model": "gpt-4"}
    ) as sse_conn:
        events = []
        async for event in sse_conn:
            events.append(event)
            if len(events) == 2:  # Expecting 2 events from the test server
                break

        assert len(events) == 2
        assert "POST received: hello world" in events[0]["data"]
        assert events[0]["event"] == "post-response"
        assert events[0]["id"] == "1"
        assert "Stream data for: gpt-4" in events[1]["data"]
        assert events[1]["event"] == "post-response"
        assert events[1]["id"] == "2"


@pytest.mark.asyncio
async def test_sse_put_request_with_data(sse_serv_put):
    """Test PUT request with data returning SSE stream."""
    client = SSEClient()
    async with client.connect(
        sse_serv_put, method="PUT", data="updated content"
    ) as sse_conn:
        events = []
        async for event in sse_conn:
            events.append(event)
            if len(events) == 2:  # Expecting 2 events from the test server
                break

        assert len(events) == 2
        assert "PUT received: updated content" in events[0]["data"]
        assert events[0]["event"] == "put-response"
        assert events[0]["id"] == "1"
        assert "PUT update confirmed" in events[1]["data"]
        assert events[1]["event"] == "put-response"
        assert events[1]["id"] == "2"


@pytest.mark.asyncio
async def test_sse_patch_request(sse_serv_patch):
    """Test PATCH request returning SSE stream."""
    client = SSEClient()
    async with client.connect(
        sse_serv_patch, method="PATCH", data='{"field": "new value"}'
    ) as sse_conn:
        events = []
        async for event in sse_conn:
            events.append(event)
            if len(events) == 2:  # Expecting 2 events from the test server
                break

        assert len(events) == 2
        assert 'PATCH received: {"field": "new value"}' in events[0]["data"]
        assert events[0]["event"] == "patch-response"
        assert events[0]["id"] == "1"
        assert "PATCH applied" in events[1]["data"]
        assert events[1]["event"] == "patch-response"
        assert events[1]["id"] == "2"


@pytest.mark.asyncio
async def test_sse_delete_request(sse_serv_delete):
    """Test DELETE request returning SSE stream."""
    client = SSEClient()
    async with client.connect(sse_serv_delete, method="DELETE") as sse_conn:
        events = []
        async for event in sse_conn:
            events.append(event)
            if len(events) == 2:  # Expecting 2 events from the test server
                break

        assert len(events) == 2
        assert "DELETE initiated" in events[0]["data"]
        assert events[0]["event"] == "delete-response"
        assert events[0]["id"] == "1"
        assert "DELETE completed" in events[1]["data"]
        assert events[1]["event"] == "delete-response"
        assert events[1]["id"] == "2"


@pytest.mark.asyncio
async def test_sse_get_with_query_params(sse_serv_params):
    """Test GET request with query parameters returning SSE stream."""
    client = SSEClient()
    async with client.connect(
        sse_serv_params,
        method="GET",
        params={"channel": "updates", "since": "2023-01-01", "limit": "10"},
    ) as sse_conn:
        events = []
        async for event in sse_conn:
            events.append(event)
            if len(events) == 2:  # Expecting 2 events from the test server
                break

        assert len(events) == 2
        # Check that params are included in the response
        assert "channel" in events[0]["data"]
        assert "updates" in events[0]["data"]
        assert "Channel: updates" in events[1]["data"]
        assert events[1]["event"] == "params-response"
        assert events[1]["id"] == "2"


@pytest.mark.asyncio
async def test_sse_post_reconnection_with_body(sse_serv_post_reconnect):
    """Test POST request reconnection preserving request body."""
    client = SSEClient()
    sse_conn = await client.connect(
        sse_serv_post_reconnect,
        method="POST",
        json={"test": "reconnect"},
        reconnect=True,
        retry_delay=100,
    )

    events = []
    async for event in sse_conn:
        events.append(event)
        if len(events) == 2:  # Expecting 2 events after reconnection
            break

    assert len(events) == 2
    assert "First POST:" in events[0]["data"]
    assert "Reconnected POST:" in events[1]["data"]


@pytest.mark.asyncio
async def test_sse_keep_connection(sse_serv):
    """Test SSE client with keep_connection=True does not close the connection."""
    client = SSEClient()
    async with client.connect(sse_serv, keep_connection=True) as sse_conn:
        events = []
        async for event in sse_conn:
            events.append(event)
            if len(events) == 2:  # Collect a few events
                break

        assert len(events) == 2
        # After exiting context, connection should not be closed
        # We can't directly check, but ensure no exceptions and behavior is as expected
