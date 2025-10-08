import asyncio
from json import dumps as json_dumps
from ssl import SSLContext
from typing import AsyncIterator, Optional, Set, Union

from aiosonic.client import HeadersType, HTTPClient, HttpHeaders
from aiosonic.exceptions import SSEConnectionError, SSEParsingError

# TYPES
from aiosonic.sse_config import RequestConfig
from aiosonic.timeout import Timeouts
from aiosonic.types import DataType, ParamsType, SSEEvent


class SSEConnection:
    """Manages an active SSE connection."""

    def __init__(self, response, client: HTTPClient, config: RequestConfig):
        self._response = response
        self._connection = getattr(response, "_connection", None)
        self._client = client
        # Store the config and derive commonly used fields
        self._config = config
        self._method = config.method
        self._url = config.url
        # Always convert headers to dict for internal use (use a copy)
        self._headers = dict(config.headers) if config.headers else {}
        self._params = config.params
        self._data = config.data
        self._json = config.json
        self._request_kwargs = (
            dict(config.request_kwargs) if config.request_kwargs else {}
        )
        self._reconnect = config.reconnect
        self._retry_delay = config.retry_delay
        self._keep_connection = config.keep_connection
        self._last_event_id: Optional[str] = None
        self._closed = False
        self._seen_ids: Set[str] = set()
        self._last_yielded_data: Optional[str] = None

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
                        # Deduplicate by last yielded data to avoid dupes after reconnect
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
                # Reconnect with the same request parameters
                self._response = await self._client.request(
                    method=self._method,
                    url=self._url,
                    headers=self._headers,
                    params=self._params,
                    data=self._data,
                    json=self._json,
                    **self._request_kwargs,
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
        if self._connection and not self._keep_connection:
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
        config: RequestConfig,
    ):
        self._client = client
        self._config = config
        # make a shallow mutable copy for the awaitable (headers may be mutated per connection)
        self._headers = dict(config.headers) if config.headers else {}
        self._method = config.method
        self._url = config.url
        self._params = config.params
        self._data = config.data
        self._json = config.json
        self._request_kwargs = (
            dict(config.request_kwargs) if config.request_kwargs else {}
        )
        self._reconnect = config.reconnect
        self._retry_delay = config.retry_delay
        self._keep_connection = config.keep_connection
        self._conn_obj: Optional[SSEConnection] = None

    def __await__(self):
        return self._do_connect().__await__()

    async def _do_connect(self) -> SSEConnection:
        while True:
            try:
                response = await self._client.request(
                    method=self._method,
                    url=self._url,
                    headers=self._headers,
                    params=self._params,
                    data=self._data,
                    json=self._json,
                    **self._request_kwargs,
                )
                if response.status_code != 200:
                    raise SSEConnectionError(
                        f"Failed to connect to SSE endpoint: {response.status_code}"
                    )
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    raise SSEConnectionError(
                        "Endpoint did not return 'text/event-stream'"
                    )
                # pass a per-connection RequestConfig copy so each connection can mutate headers
                per_conn_config = self._config.with_headers_copy()
                per_conn_config.request_kwargs = dict(self._request_kwargs)
                conn = SSEConnection(response, self._client, per_conn_config)
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

        POST request with JSON body (OpenAI-style streaming):

        >>> async def main():
        ...     async with SSEClient() as client:
        ...         async with client.connect(
        ...             "https://api.openai.com/v1/chat/completions",
        ...             method="POST",
        ...             json={"model": "gpt-4", "messages": [...], "stream": True},
        ...             headers={"Authorization": "Bearer token"}
        ...         ) as sse_conn:
        ...             async for event in sse_conn:
        ...                 print(event['data'])
        >>>
        >>> asyncio.run(main())
    """

    def __init__(self, http_client: Optional[HTTPClient] = None):
        """Initialize the SSE client."""
        self._client = http_client or HTTPClient()

    def connect(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[HeadersType] = None,
        params: Optional[ParamsType] = None,
        data: Optional[DataType] = None,
        json: Optional[Union[dict, list]] = None,
        multipart: bool = False,
        verify: bool = True,
        ssl: Optional[SSLContext] = None,
        timeouts: Optional[Timeouts] = None,
        follow: bool = False,
        http2: bool = False,
        reconnect: bool = True,
        retry_delay: int = 3000,
        json_serializer=json_dumps,
        keep_connection: bool = False,
    ) -> _ConnectAwaitable:
        """Return an awaitable/async-context-manager that establishes an SSE connection.

        Args:
            url: The URL to connect to
            method: HTTP method to use (GET, POST, PUT, PATCH, DELETE, etc.)
            headers: HTTP headers to send
            params: Query parameters to include in the URL
            data: Request body data
            json: JSON data to send as request body
            multipart: Whether to send data as multipart form
            verify: Whether to verify SSL certificates
            ssl: Custom SSL context
            timeouts: Request timeout settings
            follow: Whether to follow redirects
            http2: Whether to use HTTP/2
            reconnect: Whether to automatically reconnect on connection loss
            retry_delay: Delay between reconnection attempts in milliseconds
            json_serializer: Custom JSON serializer function
            keep_connection: Whether to keep the connection open after the SSE stream ends
                (experimental)

        Usage:
          - `sse_conn = await client.connect(url, method="POST", json=data)`
          - `async with client.connect(url, method="POST", json=data) as sse_conn:`
        """
        # Convert headers to dict format
        if headers is None:
            headers_dict = {}
        elif isinstance(headers, dict):
            headers_dict = dict(headers)
        elif isinstance(headers, list):
            headers_dict = dict(headers)
        elif isinstance(headers, HttpHeaders):
            headers_dict = dict(headers)

        headers_dict.setdefault("Accept", "text/event-stream")
        headers_dict.setdefault("Cache-Control", "no-cache")

        # Build request kwargs for HTTPClient.request()
        request_kwargs = {
            "multipart": multipart,
            "verify": verify,
            "ssl": ssl,
            "timeouts": timeouts,
            "follow": follow,
            "http2": http2,
            "json_serializer": json_serializer,
        }

        config = RequestConfig(
            method=method,
            url=url,
            headers=headers_dict,
            params=params,
            data=data,
            json=json,
            request_kwargs=request_kwargs,
            reconnect=reconnect,
            retry_delay=retry_delay,
            keep_connection=keep_connection,
        )

        return _ConnectAwaitable(self._client, config)
