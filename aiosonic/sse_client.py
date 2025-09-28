import asyncio
from typing import AsyncIterator, Optional, Dict, Any, Set

from aiosonic.client import HTTPClient
from aiosonic.exceptions import SSEConnectionError, SSEParsingError
from aiosonic.types import SSEEvent


class SSEConnection:
    """Manages an active SSE connection."""

    def __init__(
        self,
        response,
        client: HTTPClient,
        url: str,
        headers: Dict[str, str],
        reconnect: bool,
        retry_delay: int,
    ):
        self._response = response
        self._connection = getattr(response, "_connection", None)
        self._client = client
        self._url = url
        self._headers = headers
        self._reconnect = reconnect
        self._retry_delay = retry_delay
        self._last_event_id: Optional[str] = None
        self._closed = False
        self._seen_ids: Set[str] = set()

    async def __aiter__(self) -> AsyncIterator[SSEEvent]:
        """Iterate over SSE events, handling reconnection when configured."""
        buffer = b""
        while not self._closed:
            try:
                async for chunk in self._response.read_chunks():
                    buffer += chunk
                    while b"\n\n" in buffer:
                        event_data, buffer = buffer.split(b"\n\n", 1)
                        try:
                            event = self._parse_event(event_data.decode())
                        except Exception as e:
                            raise SSEParsingError(f"Error parsing SSE event: {e}")
                        # deduplicate by id
                        eid = event.get("id")
                        if eid is not None:
                            if eid in self._seen_ids:
                                # skip duplicate
                                continue
                            self._seen_ids.add(eid)
                            self._last_event_id = eid
                        # deduplicate by last yielded data to avoid duplicate emission after reconnect
                        if (
                            hasattr(self, "_last_yielded_data")
                            and self._last_yielded_data is not None
                        ):
                            if event.get("data") == self._last_yielded_data:
                                # skip this duplicate
                                continue
                        self._last_yielded_data = event.get("data")
                        yield event
                if not self._reconnect:
                    self._closed = True
                    break
                await asyncio.sleep(self._retry_delay / 1000)
                if self._last_event_id:
                    self._headers["Last-Event-ID"] = self._last_event_id
                self._response = await self._client.get(
                    self._url, headers=self._headers
                )
                if self._response.status_code != 200 or "text/event-stream" not in (
                    self._response.headers.get("content-type", "")
                ):
                    raise SSEConnectionError(
                        f"Failed to reconnect to SSE endpoint: {self._response.status_code}"
                    )
                buffer = b""
            except SSEParsingError:
                raise
            except Exception as e:
                if not self._reconnect:
                    raise SSEConnectionError(f"SSE connection error: {e}")
                await asyncio.sleep(self._retry_delay / 1000)

    def _parse_event(self, event_data: str) -> SSEEvent:
        """Parse a single SSE event.

        Raises SSEParsingError for malformed lines.
        """
        event: SSEEvent = {"data": "", "event": None, "id": None, "retry": None}
        last_field: Optional[str] = None
        for line in event_data.splitlines():
            if not line:
                continue
            if line.startswith(":"):
                continue
            if ":" not in line:
                # treat as continuation of previous data field if present
                if last_field == "data":
                    # append raw continuation
                    event["data"] += line + "\n"
                    continue
                raise SSEParsingError(f"Malformed SSE line: '{line}'")
            field, value = line.split(":", 1)
            field = field.strip()
            value = value.lstrip()
            last_field = field
            if field == "data":
                event["data"] += value + "\n"
            elif field == "event":
                event["event"] = value
            elif field == "id":
                event["id"] = value
            elif field == "retry":
                try:
                    event["retry"] = int(value)
                except ValueError:
                    raise SSEParsingError(f"Invalid retry value: '{value}'")
        if event["data"].endswith("\n"):
            event["data"] = event["data"][:-1]
        return event

    async def close(self):
        """Close the connection."""
        self._closed = True
        if self._connection:
            self._connection.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()


class _ConnectAwaitable:
    """Object returned by SSEClient.connect that is both awaitable and an async context manager."""

    def __init__(
        self,
        client: HTTPClient,
        url: str,
        headers: Dict[str, str],
        reconnect: bool,
        retry_delay: int,
    ):
        self._client = client
        self._url = url
        self._headers = headers
        self._reconnect = reconnect
        self._retry_delay = retry_delay
        self._conn_obj: Optional[SSEConnection] = None

    def __await__(self):
        return self._do_connect().__await__()

    async def _do_connect(self) -> SSEConnection:
        while True:
            try:
                response = await self._client.get(self._url, headers=self._headers)
                if response.status_code != 200:
                    raise SSEConnectionError(
                        f"Failed to connect to SSE endpoint: {response.status_code}"
                    )
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    raise SSEConnectionError(
                        "Endpoint did not return 'text/event-stream'"
                    )
                conn = SSEConnection(
                    response,
                    self._client,
                    self._url,
                    dict(self._headers),
                    self._reconnect,
                    self._retry_delay,
                )
                if not self._reconnect:
                    try:
                        async for _ in conn._response.read_chunks():
                            pass
                    except Exception:
                        raise SSEConnectionError("SSE connection closed unexpectedly")
                    raise SSEConnectionError("SSE connection closed (no reconnection)")
                self._conn_obj = conn
                return conn
            except SSEConnectionError:
                raise
            except Exception as e:
                if not self._reconnect:
                    raise SSEConnectionError(f"SSE connection failed: {e}")
                await asyncio.sleep(self._retry_delay / 1000)

    async def __aenter__(self):
        self._conn_obj = await self._do_connect()
        return self._conn_obj

    async def __aexit__(self, exc_type, exc, tb):
        if self._conn_obj is not None:
            await self._conn_obj.close()


class SSEClient:
    """SSE client for aiosonic.

    Examples:
        Basic usage with async context manager:

        >>> import asyncio
        >>> from aiosonic import SSEClient
        >>>
        >>> async def main():
        ...     async with SSEClient() as client:
        ...         async with client.connect("http://example.com/sse") as sse_conn:
        ...             async for event in sse_conn:
        ...                 print(f"Event: {event['event']}, Data: {event['data']}")
        ...                 if event['data'] == 'stop':
        ...                     break
        >>>
        >>> asyncio.run(main())
    """

    def __init__(self, http_client: Optional[HTTPClient] = None):
        """Initialize the SSE client."""
        self._client = http_client or HTTPClient()

    def connect(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        reconnect: bool = True,
        retry_delay: int = 3000,
    ) -> _ConnectAwaitable:
        """Return an awaitable/async-context-manager that establishes an SSE connection.

        Usage:
          - `sse_conn = await client.connect(url)`
          - `async with client.connect(url) as sse_conn:`
        """
        headers = headers or {}
        headers.setdefault("Accept", "text/event-stream")
        headers.setdefault("Cache-Control", "no-cache")
        return _ConnectAwaitable(self._client, url, headers, reconnect, retry_delay)
