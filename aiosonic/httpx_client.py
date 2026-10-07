"""Client with the API of ``httpx.AsyncClient``, to replace httpx with aiosonic with few changes.

Example:

.. code-block:: python

    from aiosonic.httpx_client import AsyncClient

    async with AsyncClient(base_url="https://api.example.com", timeout=10.0) as client:
        response = await client.get("/users", params={"page": "1"})
        response.raise_for_status()
        users = response.json()
"""

from __future__ import annotations
from codecs import getincrementaldecoder
from contextlib import aclosing, asynccontextmanager
from io import BytesIO, IOBase
from json import loads
from ssl import SSLContext
from typing import Any, AsyncIterator, Callable, Dict, Iterable, List, Optional, Tuple, Union

from aiosonic.auth import AuthType
from aiosonic.base_client import BaseClient
from aiosonic.client import HeadersType, HttpHeaders, HTTPClient, HttpResponse
from aiosonic.exceptions import HTTPStatusError, ResponseNotRead, StreamConsumed
from aiosonic.multipart import MultipartFile, MultipartForm
from aiosonic.proxy import Proxy
from aiosonic.timeout import Timeouts
from aiosonic.types import DataType, ParamsType

DEFAULT_TIMEOUT = 5.0
DEFAULT_MAX_REDIRECTS = 20

TimeoutType = Union[None, float, Timeouts]
FileContent = Union[bytes, str, IOBase]
FileType = Union[FileContent, Tuple[Optional[str], FileContent], Tuple[Optional[str], FileContent, Optional[str]]]
FilesType = Union[Dict[str, FileType], Iterable[Tuple[str, FileType]]]

_STATUS_ERROR_KINDS = {
    1: "Informational response",
    3: "Redirect response",
    4: "Client error",
    5: "Server error",
}


class UseClientDefault:
    """Type of :data:`USE_CLIENT_DEFAULT`, the default of request arguments that fall back to the client."""


USE_CLIENT_DEFAULT = UseClientDefault()


def to_timeouts(timeout: TimeoutType) -> Timeouts:
    """Convert an httpx style timeout to :class:`aiosonic.timeout.Timeouts`.

    Args:
        timeout (TimeoutType): Seconds for connecting, reading and getting a connection from the pool,
            None to disable them, or a :class:`aiosonic.timeout.Timeouts` that is used as is.

    Returns:
        Timeouts: The timeouts, without a limit for the whole request when built from a number.
    """
    if isinstance(timeout, Timeouts):
        return timeout
    return Timeouts(sock_connect=timeout, sock_read=timeout, pool_acquire=timeout, request_timeout=None)


class Request:
    """Request that produced a :class:`Response`.

    Attributes:
        method (str): The http method.
        url (str): The url, without credentials.
        headers (HttpHeaders): The headers. Request hooks may modify them before the request is sent.
    """

    def __init__(self, method: str, url: str, headers: Optional[HeadersType] = None):
        self.method = method
        self.url = url
        self.headers = headers if headers is not None else HttpHeaders()

    def __repr__(self) -> str:
        return f"<Request({self.method!r}, {self.url!r})>"


class Response:
    """Response with the API of ``httpx.Response``.

    The body is read before the response is returned, except for :meth:`AsyncClient.stream`, where it must be
    read with :meth:`aread` or one of the ``aiter_*`` methods.

    Args:
        response (HttpResponse): The aiosonic response to wrap.
    """

    def __init__(self, response: HttpResponse):
        self._response = response
        self._read = not response._has_pending_body()
        self._consumed = False

    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def headers(self) -> HttpHeaders:
        return self._response.headers

    @property
    def url(self) -> str:
        return self._response.url

    @property
    def request(self) -> Request:
        return Request(self._response.method, self._response.url)

    @property
    def http_version(self) -> str:
        return f"HTTP/{self._response.http_version}"

    @property
    def reason_phrase(self) -> str:
        return self._response.reason

    @property
    def cookies(self) -> Dict[str, str]:
        return {name: morsel.value for name, morsel in (self._response.cookies or {}).items()}

    @property
    def encoding(self) -> str:
        return self._response._get_encoding()

    @property
    def is_informational(self) -> bool:
        return 100 <= self.status_code <= 199

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code <= 299

    @property
    def is_redirect(self) -> bool:
        return self.status_code in {301, 302, 303, 307, 308} and "location" in self.headers

    @property
    def is_client_error(self) -> bool:
        return 400 <= self.status_code <= 499

    @property
    def is_server_error(self) -> bool:
        return 500 <= self.status_code <= 599

    @property
    def is_error(self) -> bool:
        return 400 <= self.status_code <= 599

    @property
    def is_stream_consumed(self) -> bool:
        return self._consumed

    @property
    def content(self) -> bytes:
        """Get the body.

        Raises:
            ResponseNotRead: If the body of a streamed response was not read with :meth:`aread`.
        """
        if not self._read:
            raise ResponseNotRead()
        return self._response.body

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding, errors="replace")

    def json(self, **kwargs: Any) -> Any:
        """Decode the body as json.

        Args:
            **kwargs: Arguments for :func:`json.loads`.
        """
        return loads(self.content, **kwargs)

    def raise_for_status(self) -> Response:
        """Raise :class:`aiosonic.exceptions.HTTPStatusError` when the status code is not 2xx.

        Returns:
            Response: This response, so the call can be chained.
        """
        if self.is_success:
            return self
        kind = _STATUS_ERROR_KINDS.get(self.status_code // 100, "Invalid status code")
        raise HTTPStatusError(f"{kind} '{self.status_code} {self.reason_phrase}' for url '{self.url}'", self)

    def _start_stream(self):
        if self._consumed:
            raise StreamConsumed()
        self._consumed = True

    async def aread(self) -> bytes:
        """Read the whole body.

        Returns:
            bytes: The body, decompressed when it was sent with gzip or deflate.

        Raises:
            StreamConsumed: If the body was already iterated.
        """
        if not self._read:
            self._start_stream()
            if not self._response.chunks_readed:
                await self._response.content()
            self._read = True
        return self._response.body

    async def aiter_raw(self) -> AsyncIterator[bytes]:
        """Iterate over the body as it comes from the server, without decompressing it."""
        if self._read:
            raise StreamConsumed()
        self._start_stream()
        async with aclosing(self._response.read_chunks()) as chunks:
            async for chunk in chunks:
                yield chunk

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        """Iterate over the body, decompressing gzip and deflate bodies as they arrive."""
        if self._read:
            if self._response.body:
                yield self._response.body
            return
        self._start_stream()
        async with aclosing(self._response.iter_bytes()) as chunks:
            async for chunk in chunks:
                yield chunk

    async def aiter_text(self) -> AsyncIterator[str]:
        """Iterate over the decoded body."""
        decoder = getincrementaldecoder(self.encoding)(errors="replace")
        async with aclosing(self.aiter_bytes()) as chunks:
            async for chunk in chunks:
                text = decoder.decode(chunk)
                if text:
                    yield text
        tail = decoder.decode(b"", final=True)
        if tail:
            yield tail

    async def aiter_lines(self) -> AsyncIterator[str]:
        """Iterate over the decoded body line by line, without the line terminators."""
        pending = ""
        async with aclosing(self.aiter_text()) as texts:
            async for text in texts:
                *lines, pending = (pending + text).split("\n")
                for line in lines:
                    yield line.removesuffix("\r")
        if pending:
            yield pending.removesuffix("\r")

    async def aclose(self):
        """Release the connection of a response whose body was not fully read."""
        await self._response.aclose()

    def __repr__(self) -> str:
        return f"<Response [{self.status_code} {self.reason_phrase}]>"


def _to_multipart_file(value: FileType) -> MultipartFile:
    filename, content_type = None, None
    if isinstance(value, tuple):
        filename, value, *rest = value
        content_type = rest[0] if rest else None
    if isinstance(value, str):
        value = value.encode()
    if isinstance(value, bytes):
        value = BytesIO(value)
    return MultipartFile(value, filename=filename, content_type=content_type)


def _build_body(
    content: Optional[DataType], data: Optional[DataType], files: Optional[FilesType]
) -> Optional[DataType]:
    if files:
        form = MultipartForm()
        for name, value in (data or {}).items():
            form.add_field(name, str(value))
        for name, file in files.items() if isinstance(files, dict) else files:
            form.add_field(name, _to_multipart_file(file))
        return form
    if content is not None:
        return content
    return data


def _wrap_hook(name: str, hook: Callable) -> Callable:
    if name == "request":
        return lambda method, url, headers: hook(Request(method, url, headers))
    if name == "response":
        return lambda response: hook(Response(response))
    return hook


class AsyncClient(BaseClient):
    """Client with the API of ``httpx.AsyncClient``.

    Requests return a :class:`Response` whose body was already read, so ``response.json()``,
    ``response.text`` and ``response.content`` work as in httpx. Cookies are kept between requests.

    Args:
        auth: :class:`aiosonic.auth.Auth` or ``(username, password)`` tuple used for every request.
        params: Query params added to every request.
        headers: Headers added to every request.
        verify: Whether to verify ssl certificates, or the :class:`ssl.SSLContext` to use.
        http2: Whether to use HTTP/2.
        timeout: Seconds for connecting, reading and getting a connection from the pool, None to disable them,
            or a :class:`aiosonic.timeout.Timeouts`.
        follow_redirects: Whether to follow redirects.
        max_redirects: Maximum redirects to follow.
        event_hooks: Dict with the ``"request"`` and ``"response"`` keys, each one a list of sync or async
            callables, called with a :class:`Request` before sending each request and with a :class:`Response`,
            whose body may be unread, after receiving each response.
        base_url: Url prepended to relative request urls.
        proxy: Proxy url or :class:`aiosonic.proxy.Proxy`.
        http_client: :class:`aiosonic.HTTPClient` to send the requests, to share its connections. It can not
            be combined with ``event_hooks`` or ``proxy``, and it is not closed by :meth:`aclose`.
    """

    def __init__(
        self,
        *,
        auth: Optional[AuthType] = None,
        params: Optional[ParamsType] = None,
        headers: Optional[HeadersType] = None,
        verify: Union[bool, SSLContext] = True,
        http2: bool = False,
        timeout: TimeoutType = DEFAULT_TIMEOUT,
        follow_redirects: bool = False,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        event_hooks: Optional[Dict[str, List[Callable]]] = None,
        base_url: str = "",
        proxy: Optional[Union[str, Proxy]] = None,
        http_client: Optional[HTTPClient] = None,
    ):
        if http_client is not None and (event_hooks or proxy):
            raise ValueError("event_hooks and proxy can not be used with http_client, configure it instead")
        if http_client is None:
            hooks = {name: [_wrap_hook(name, hook) for hook in hooks] for name, hooks in (event_hooks or {}).items()}
            http_client = HTTPClient(
                handle_cookies=True,
                proxy=Proxy(proxy) if isinstance(proxy, str) else proxy,
                event_hooks=hooks,
            )
            self._owns_client = True
        else:
            self._owns_client = False
        super().__init__(http_client)
        self.base_url = base_url
        self.default_headers = HttpHeaders(headers or {})
        self.default_params = params or {}
        self.auth = auth
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self.max_redirects = max_redirects
        self.http2 = http2
        self._verify = verify if isinstance(verify, bool) else True
        self._ssl = verify if isinstance(verify, SSLContext) else None
        self._closed = False

    @property
    def headers(self) -> HttpHeaders:
        return self.default_headers

    @property
    def params(self) -> ParamsType:
        return self.default_params

    @property
    def is_closed(self) -> bool:
        return self._closed

    def merge_headers(self, headers: Optional[HeadersType] = None) -> HttpHeaders:
        """Merge default headers with the provided ones, ignoring the case of their names."""
        merged = HttpHeaders(self.default_headers)
        merged.update(headers or {})
        return merged

    async def process_request(self, method: str, url: str, **kwargs) -> HttpResponse:
        """Send the request with :meth:`aiosonic.HTTPClient.request` and return the aiosonic response."""
        return await self.client.request(
            self.process_request_url(url),
            method=method.upper(),
            headers=self.merge_headers(kwargs.pop("headers", None)),
            params=self.merge_params(kwargs.pop("params", None)),
            **kwargs,
        )

    async def _send(
        self,
        method: str,
        url: str,
        stream: bool,
        content: Optional[DataType],
        data: Optional[DataType],
        files: Optional[FilesType],
        json: Any,
        params: Optional[ParamsType],
        headers: Optional[HeadersType],
        auth: Union[AuthType, UseClientDefault, None],
        follow_redirects: Union[bool, UseClientDefault],
        timeout: Union[TimeoutType, UseClientDefault],
    ) -> Response:
        response = await self.process_request(
            method,
            url,
            headers=headers,
            params=params,
            data=_build_body(content, data, files),
            json=json,
            auth=self.auth if isinstance(auth, UseClientDefault) else auth,
            follow=self.follow_redirects if isinstance(follow_redirects, UseClientDefault) else follow_redirects,
            timeouts=to_timeouts(self.timeout if isinstance(timeout, UseClientDefault) else timeout),
            verify=self._verify,
            ssl=self._ssl,
            http2=self.http2,
            max_redirects=self.max_redirects,
            stream=stream,
        )
        return Response(response)

    async def request(
        self,
        method: str,
        url: str,
        *,
        content: Optional[DataType] = None,
        data: Optional[DataType] = None,
        files: Optional[FilesType] = None,
        json: Any = None,
        params: Optional[ParamsType] = None,
        headers: Optional[HeadersType] = None,
        auth: Union[AuthType, UseClientDefault, None] = USE_CLIENT_DEFAULT,
        follow_redirects: Union[bool, UseClientDefault] = USE_CLIENT_DEFAULT,
        timeout: Union[TimeoutType, UseClientDefault] = USE_CLIENT_DEFAULT,
    ) -> Response:
        """Send a request and read its body.

        Args:
            method: The http method.
            url: Absolute url, or a path relative to ``base_url``.
            content: Raw body, as bytes, str or a (async) iterator of bytes.
            data: Form fields, sent url encoded, or as multipart fields along with ``files``.
            files: Files to send as ``multipart/form-data``, by field name: a file object, bytes, or a
                ``(filename, file)`` or ``(filename, file, content_type)`` tuple. File objects are closed after
                sending them.
            json: Object to send encoded as json.
            params: Query params, merged with the client ones.
            headers: Headers, merged with the client ones.
            auth: Auth for this request, None to send none.
            follow_redirects: Whether to follow redirects.
            timeout: Timeout for this request, see :class:`AsyncClient`.

        Returns:
            Response: The response, with its body read.
        """
        response = await self._send(
            method, url, False, content, data, files, json, params, headers, auth, follow_redirects, timeout
        )
        try:
            await response.aread()
        except BaseException:
            await response.aclose()
            raise
        return await self.process_response(response)

    @asynccontextmanager
    async def stream(
        self,
        method: str,
        url: str,
        *,
        content: Optional[DataType] = None,
        data: Optional[DataType] = None,
        files: Optional[FilesType] = None,
        json: Any = None,
        params: Optional[ParamsType] = None,
        headers: Optional[HeadersType] = None,
        auth: Union[AuthType, UseClientDefault, None] = USE_CLIENT_DEFAULT,
        follow_redirects: Union[bool, UseClientDefault] = USE_CLIENT_DEFAULT,
        timeout: Union[TimeoutType, UseClientDefault] = USE_CLIENT_DEFAULT,
    ) -> AsyncIterator[Response]:
        """Send a request and give its response without reading the body.

        The response is released when leaving the block, even if its body was not fully read. The arguments
        are the ones of :meth:`request`.
        """
        response = await self._send(
            method, url, True, content, data, files, json, params, headers, auth, follow_redirects, timeout
        )
        try:
            yield response
        finally:
            await response.aclose()

    async def aclose(self):
        """Close the connections of the client, unless it was given an ``http_client``."""
        if self._owns_client and not self._closed:
            await self.client.aclose()
        self._closed = True

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(self, *args):
        await self.aclose()
