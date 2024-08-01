"""Main module."""

import asyncio
import logging
import re
import sys
from asyncio import wait_for
from codecs import lookup
from copy import deepcopy
from functools import partial
from gzip import decompress as gzip_decompress
from http import cookies
from io import IOBase
from json import dumps as json_dumps
from json import loads
from os.path import basename
from random import randint
from ssl import SSLContext
from typing import AsyncIterator, Callable, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import ParseResult, urlencode
from zlib import decompress as zlib_decompress

from charset_normalizer import detect

from aiosonic import http_parser
from aiosonic.connection import Connection, get_default_ssl_context
from aiosonic.connectors import TCPConnector
from aiosonic.exceptions import (
    ConnectionDisconnected,
    ConnectTimeout,
    HttpParsingError,
    MaxRedirects,
    MissingWriterException,
    ReadTimeout,
    RequestTimeout,
    TimeoutException,
)
from aiosonic.proxy import Proxy
from aiosonic.resolver import get_loop
from aiosonic.timeout import Timeouts

# TYPES
from aiosonic.types import BodyType, DataType, ParamsType, ParsedBodyType
from aiosonic.utils import get_debug_logger
from aiosonic.version import VERSION
from aiosonic_utils.structures import CaseInsensitiveDict

# VARIABLES
_HTTP_RESPONSE_STATUS_LINE = re.compile(
    r"HTTP/(?P<version>(\d.)?(\d)) (?P<code>\d+) (?P<reason>[\w]*)"
)
_CHARSET_RGX = re.compile(r"charset=(?P<charset>[\w-]*);?")
_CHUNK_SIZE = 1024 * 4  # 4kilobytes
_NEW_LINE = "\r\n"
dlogger = get_debug_logger()
RANDOM_RANGE = (10**8, 10**9)

REPLACEABLE_HEADERS = {"host", "user-agent"}


# Classes


class HttpHeaders(CaseInsensitiveDict):
    """Http headers dict."""

    @staticmethod
    def _clear_line(line: bytes):
        """Clear readed line."""
        decoded = line.rstrip().decode()
        pair = decoded.split(": ", 1)
        if len(pair) < 2:
            return decoded.split(":")
        return pair


#: Headers
HeadersType = Union[Dict[str, str], List[Tuple[str, str]], HttpHeaders]


class HttpResponse:
    """Custom HttpResponse class for handling responses.

    Properties:
      * **status_code** (int): response status code
      * **headers** (:class:`aiosonic.HttpHeaders`): headers in case insensitive dict
      * **cookies** (:class:`http.cookies.SimpleCookie`): instance of SimpleCookies
        if cookies present in respone.
      * **raw_headers** (List[Tuple[bytes, bytes]]): headers as raw format
    """

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.headers = HttpHeaders()
        self.cookies = None
        self.raw_headers = []
        self.body = b""
        self.response_initial = {}
        self._connection = None
        self.chunked = False
        self.compressed = b""
        self.chunks_readed = False
        self.request_meta = {}
        self._loop = loop

    def _set_response_initial(self, data: bytes):
        """Parse first bytes from http response."""
        res = re.match(_HTTP_RESPONSE_STATUS_LINE, data.decode().rstrip("\r\n"))
        assert res
        self.response_initial = res.groupdict()

    def _set_header(self, key: str, val: str):
        """Set header to response."""
        self.headers[key] = val
        self.raw_headers.append((key, val))

    async def _set_response_headers(self, iterator):
        async for header_data in iterator:
            header_tuple = HttpHeaders._clear_line(header_data)
            self._set_header(*header_tuple)

            # set cookies in response
            if header_tuple[0].lower() == "set-cookie":
                self._update_cookies(header_tuple)

        if dlogger.level == logging.DEBUG:

            def logparse(data):
                return _NEW_LINE.join([f"{key}={value}" for key, value in data])

            info = {**self.response_initial, **self.request_meta}.items()
            to_log_info = [[key, val] for key, val in info]
            meta_log = logparse(to_log_info)
            headers_log = logparse(self.raw_headers)
            dlogger.debug(
                meta_log + _NEW_LINE + "Headers:" + _NEW_LINE * 2 + headers_log + "---"
            )  # noqa

    def _update_cookies(self, header_tuple):
        """Update jar of cookies."""
        self.cookies = self.cookies or cookies.SimpleCookie()
        self.cookies.load(header_tuple[1])

    def _set_connection(self, connection: Connection):
        """Set header to response."""
        self._connection = connection

    @property
    def status_code(self) -> int:
        """Get status code."""
        return int(self.response_initial["code"])

    @property
    def ok(self) -> bool:
        """Returns True if :attr:`status_code` is 2xx range, False if not."""
        return 200 <= self.status_code <= 299

    def _set_body(self, data):
        """Set body."""
        if self.compressed == "gzip":
            self.body += gzip_decompress(data)
        elif self.compressed == "deflate":
            self.body += zlib_decompress(data)
        else:
            self.body += data

    def _get_encoding(self) -> str:
        ctype = self.headers.get("content-type", "").lower()
        res = re.findall(_CHARSET_RGX, ctype)
        encoding = ""

        if res:
            encoding = res[0]

        if encoding:
            try:
                lookup(encoding)
            except LookupError:
                encoding = ""

        if not encoding:
            if "application" in ctype and "json" in ctype:
                # RFC 7159 states that the default encoding is UTF-8.
                encoding = "utf-8"
            else:
                encoding = detect(self.body)["encoding"]
        if not encoding:
            encoding = "utf-8"

        return encoding.lower()

    async def content(self) -> bytes:
        """Read response body."""
        if self.chunked and not self.body:
            res = b""
            async for chunk in self.read_chunks():
                res += chunk
            self._set_body(res)
        return self.body

    async def text(self) -> str:
        """Read response body."""
        body = await self.content()
        encoding = self._get_encoding()
        return (body).decode(encoding)

    async def json(self, json_decoder=loads) -> dict:
        """Read response body."""
        assert "application/json" in self.headers["content-type"].lower()
        body = await self.content()
        return json_decoder(body)

    async def read_chunks(self) -> AsyncIterator[bytes]:
        """Read chunks from chunked response."""
        if not self._connection:
            raise ConnectionError("missing connection, possible already read response.")
        try:
            while True and not self.chunks_readed:
                chunk_size = int((await self._connection.readline()).rstrip(), 16)
                if not chunk_size:
                    # read last CRLF
                    await self._connection.readline()
                    break
                chunk = await self._connection.readexactly(chunk_size + 2)
                yield chunk[:-2]
            self.chunks_readed = True
        finally:
            # Ensure the conn get's released
            if self._connection.blocked:
                await self._connection.release()
                self._connection = None

    def __del__(self):
        # clean it
        if self._connection and self._connection.blocked:
            clean_up = self._loop.create_task(self._connection.ensure_released())
            clean_up.add_done_callback(self._connection.background_tasks.discard)
            self._connection.background_tasks.add(clean_up)

    def _set_request_meta(self, urlparsed: ParseResult):
        self.request_meta = {"from_path": urlparsed.path or "/"}


def _get_hostname(hostname_arg, port):
    hostname = hostname_arg.encode("idna").decode()

    if port not in [80, 443]:
        hostname += ":" + str(port)
    return hostname


def _get_path(url: ParseResult, proxy: Optional[Proxy] = None):
    if proxy is None:
        return url.path or "/"
    else:
        return f"{url.scheme}://{url.netloc}{url.path}"


def _prepare_request_headers(
    url: ParseResult,
    connection: Connection,
    method: str,
    headers: Optional[HeadersType] = None,
    params: Optional[ParamsType] = None,
    multipart: Optional[bool] = None,
    boundary: Optional[str] = None,
    proxy: Optional[Proxy] = None,
) -> Union[bytes, HeadersType]:
    """Prepare get data."""
    path = _get_path(url, proxy)
    if url.query:
        path += "?" + url.query
    http2conn = connection.h2conn

    if params:
        query = urlencode(params)
        path += f"{query}" if "?" in path else f"?{query}"
    uppercase_method = method.upper()
    get_base = f"{uppercase_method} {path} HTTP/1.1{_NEW_LINE}"

    port = url.port or (443 if url.scheme == "https" else 80)
    hostname = _get_hostname(url.hostname, port)

    headers_base = []
    if http2conn:
        http_parser.add_headers(
            headers_base,
            {
                ":method": method,
                ":authority": hostname.split(":")[0],
                ":scheme": "https",
                ":path": path,
                "user-agent": f"aiosonic/{VERSION}",
            },
        )
    else:
        http_parser.add_headers(
            headers_base,
            {
                "HOST": hostname,
                "Connection": "keep-alive",
                "User-Agent": f"aiosonic/{VERSION}",
            },
        )

    if proxy and proxy.auth and url.scheme == "http":
        http_parser.add_headers(
            headers_base,
            {
                "Proxy-Connection": "keep-alive",
                "Proxy-Authorization": f"Basic {proxy.auth.decode()}",
            },
        )

    if multipart:
        http_parser.add_header(
            headers_base,
            "Content-Type",
            f'multipart/form-data; boundary="{boundary}"',
        )

    if headers:
        http_parser.add_headers(headers_base, headers)

    if http2conn:
        return headers_base

    for key, data in http_parser.headers_iterator(headers_base):
        get_base += f"{key}: {data}{_NEW_LINE}"

    # log request headers
    if dlogger.level == logging.DEBUG:
        dlogger.debug(get_base + "---")
    return (get_base + _NEW_LINE).encode()


def _handle_chunk(chunk: bytes, connection: Connection):
    """Handle chunk sending in transfer-encoding chunked."""
    chunk_size = hex(len(chunk)).replace("0x", "") + _NEW_LINE

    if not connection.writer:
        raise MissingWriterException("missing writer in connection")

    connection.write(chunk_size.encode() + chunk + _NEW_LINE.encode())


async def _send_chunks(connection: Connection, body: BodyType):
    """Send chunks."""
    if isinstance(body, AsyncIterator):
        async for chunk in body:
            _handle_chunk(chunk, connection)
    elif isinstance(body, Iterator):
        for chunk in body:
            _handle_chunk(chunk, connection)
    else:
        raise ValueError("wrong body param.")

    if not connection.writer:
        raise MissingWriterException("missing writer in connection")
    connection.write(("0" + _NEW_LINE * 2).encode())


async def _send_multipart(
    data: Dict[str, str],
    boundary: str,
    headers: HeadersType,
    chunk_size: int = _CHUNK_SIZE,
) -> bytes:
    """Send multipart data by streaming."""
    # TODO: precalculate body size and stream request
    # precalculate file sizes by os.path.getsize

    to_send = b""
    for key, val in data.items():
        # write --boundary + field
        to_send += (f"--{boundary}{_NEW_LINE}").encode()

        if isinstance(val, IOBase):
            # TODO: Utility to accept files with multipart metadata
            # (Content-Type, custom filename, ...),

            # write Contet-Disposition
            to_write = (
                "Content-Disposition: form-data; "
                + 'name="%s"; filename="%s"%s%s'
                % (
                    key,
                    basename(val.name),
                    _NEW_LINE,
                    _NEW_LINE,
                )
            )
            to_send += to_write.encode()

            # read and write chunks
            loop = get_loop()
            while True:
                data = await loop.run_in_executor(None, val.read, chunk_size)
                if not data:
                    break
                to_send += data
            val.close()

        else:
            to_send += (
                f'Content-Disposition: form-data; name="{key}"{_NEW_LINE}{_NEW_LINE}'
            ).encode()
            to_send += val.encode() + _NEW_LINE.encode()

    # write --boundary-- for finish
    to_send += (f"--{boundary}--").encode()
    http_parser.add_header(headers, "Content-Length", str(len(to_send)))
    return to_send


async def _do_request(
    urlparsed: ParseResult,
    headers_data: Callable,
    connector: TCPConnector,
    body: Optional[ParsedBodyType],
    verify: bool,
    ssl: Optional[SSLContext],
    timeouts: Optional[Timeouts],
    http2: bool = False,
    proxy: Optional[Proxy] = None,
) -> HttpResponse:
    """Something."""
    timeouts = timeouts or connector.timeouts
    url_connect = urlparsed

    if proxy:
        url_connect = http_parser.get_url_parsed(proxy.host)

    connect_ssl = ssl if not proxy else None

    args = url_connect, verify, connect_ssl, timeouts, http2
    async with await connector.acquire(*args) as connection:

        if proxy and urlparsed.scheme == "https" and not connection.proxy_connected:
            await _proxy_connect(
                connection, proxy, urlparsed, ssl or get_default_ssl_context()
            )

        to_send = headers_data(connection=connection)

        if connection.h2conn:
            return await connection.http2_request(to_send, body)

        if not connection.writer or not connection.reader:
            raise ConnectionError("Not connection writer or reader")

        connection.write(to_send)

        if body:
            if isinstance(body, (AsyncIterator, Iterator)):
                await _send_chunks(connection, body)
            else:
                connection.write(body)

        response = HttpResponse(get_loop())
        response._set_request_meta(urlparsed)

        # get response code and version
        try:
            line = await wait_for(connection.readuntil(), timeouts.sock_read)
            if not line:
                raise HttpParsingError(f"response line parsing error: {line}")
            response._set_response_initial(line)
        except asyncio.IncompleteReadError as exc:
            connection.keep = False
            raise ConnectionDisconnected()
            # raise HttpParsingError(f"response line parsing error: {exc.partial}")
        except TimeoutException:
            raise ReadTimeout()

        # reading headers
        await response._set_response_headers(
            http_parser.parse_headers_iterator(connection)
        )

        size = response.headers.get("content-length")
        chunked = response.headers.get("transfer-encoding", "") == "chunked"
        keepalive = "close" not in response.headers.get("connection", "")
        response.compressed = response.headers.get("content-encoding", "")

        if size:
            response._set_body(await connection.readexactly(int(size)))

        if chunked:
            connection.block_until_read_chunks()
            response.chunked = True

        if keepalive:
            connection.keep_alive()
        else:
            connection.keep = False
        response._set_connection(connection)

        return response


class HTTPClient:
    """aiosonic.HTTPClient class.

    This class holds the client creation that will be used for requests.

    Params:
        * **connector**: TCPConnector to be used if provided
        * **handle_cookies**: Flag to indicate if keep response cookies in
            client and send them in next requests.
        * **verify_ssl**: Flag to indicate if verify ssl certificates.
    """

    def __init__(
        self,
        connector: Optional[TCPConnector] = None,
        handle_cookies: bool = False,
        verify_ssl: bool = True,
        proxy: Optional[Proxy] = None,
    ):
        """Initialize client options."""
        self.connector = connector or TCPConnector()
        self.handle_cookies = handle_cookies
        self.cookies_map: Dict[str, cookies.SimpleCookie] = {}
        self.verify_ssl = verify_ssl
        self.proxy = proxy

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, exc, _tb):  # type: ignore
        if exc:
            # Handle the exception appropriately, e.g., logging
            return False  # Returning False re-raises the exception
        return True

    async def get(
        self,
        url: str,
        headers: Optional[HeadersType] = None,
        params: Optional[ParamsType] = None,
        verify: bool = True,
        ssl: Optional[SSLContext] = None,
        timeouts: Optional[Timeouts] = None,
        follow: bool = False,
        http2: bool = False,
    ) -> HttpResponse:
        """Do get http request."""
        return await self.request(
            url=url,
            method="GET",
            headers=headers,
            params=params,
            verify=verify,
            ssl=ssl,
            follow=follow,
            timeouts=timeouts,
            http2=http2,
        )

    async def post(
        self,
        url: str,
        data: Optional[DataType] = None,
        headers: Optional[HeadersType] = None,
        json: Optional[Union[dict, list]] = None,
        params: Optional[ParamsType] = None,
        json_serializer=json_dumps,
        multipart: bool = False,
        verify: bool = True,
        ssl: Optional[SSLContext] = None,
        timeouts: Optional[Timeouts] = None,
        follow: bool = False,
        http2: bool = False,
    ) -> HttpResponse:
        """Do post http request."""
        return await self.request(
            url=url,
            method="POST",
            headers=headers,
            params=params,
            data=data,
            json=json,
            json_serializer=json_serializer,
            multipart=multipart,
            verify=verify,
            ssl=ssl,
            follow=follow,
            timeouts=timeouts,
            http2=http2,
        )

    async def put(
        self,
        url: str,
        data: Optional[DataType] = None,
        headers: Optional[HeadersType] = None,
        json: Optional[Union[dict, list]] = None,
        params: Optional[ParamsType] = None,
        json_serializer=json_dumps,
        multipart: bool = False,
        verify: bool = True,
        ssl: Optional[SSLContext] = None,
        timeouts: Optional[Timeouts] = None,
        follow: bool = False,
        http2: bool = False,
    ) -> HttpResponse:
        """Do put http request."""
        return await self.request(
            url=url,
            method="PUT",
            headers=headers,
            params=params,
            data=data,
            json=json,
            json_serializer=json_serializer,
            multipart=multipart,
            verify=verify,
            ssl=ssl,
            follow=follow,
            timeouts=timeouts,
            http2=http2,
        )

    async def patch(
        self,
        url: str,
        data: Optional[DataType] = None,
        headers: Optional[HeadersType] = None,
        json: Optional[Union[dict, list]] = None,
        params: Optional[ParamsType] = None,
        json_serializer=json_dumps,
        multipart: bool = False,
        verify: bool = True,
        ssl: Optional[SSLContext] = None,
        timeouts: Optional[Timeouts] = None,
        follow: bool = False,
        http2: bool = False,
    ) -> HttpResponse:
        """Do patch http request."""
        return await self.request(
            url=url,
            method="PATCH",
            headers=headers,
            params=params,
            data=data,
            json=json,
            json_serializer=json_serializer,
            multipart=multipart,
            verify=verify,
            ssl=ssl,
            follow=follow,
            timeouts=timeouts,
            http2=http2,
        )

    async def delete(
        self,
        url: str,
        data: DataType = b"",
        headers: Optional[HeadersType] = None,
        json: Optional[Union[dict, list]] = None,
        params: Optional[ParamsType] = None,
        json_serializer=json_dumps,
        multipart: bool = False,
        verify: bool = True,
        ssl: Optional[SSLContext] = None,
        timeouts: Optional[Timeouts] = None,
        follow: bool = False,
        http2: bool = False,
    ) -> HttpResponse:
        """Do delete http request."""
        return await self.request(
            url=url,
            method="DELETE",
            headers=headers,
            params=params,
            data=data,
            json=json,
            json_serializer=json_serializer,
            multipart=multipart,
            verify=verify,
            ssl=ssl,
            follow=follow,
            timeouts=timeouts,
            http2=http2,
        )

    async def request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[HeadersType] = None,
        params: Optional[ParamsType] = None,
        data: Optional[DataType] = None,
        json: Optional[Union[dict, list]] = None,
        json_serializer=json_dumps,
        multipart: bool = False,
        verify: bool = True,
        ssl: Optional[SSLContext] = None,
        timeouts: Optional[Timeouts] = None,
        follow: bool = False,
        http2: bool = False,
    ) -> HttpResponse:
        """Do http request.

        Params:
            * **url**: url of request
            * **method**: Http method of request
            * **headers**: headers to add in request
            * **params**: query params to add in request if not manually added
            * **data**: Data to be sent, this param is ignored for get
            * **json**: If provided, encodes the provided json structure and appends the corresponding header.
            * **json_serializer**: Use provided json serializer, default: json.dumps
            * **multipart**: Tell aiosonic if request is multipart
            * **verify**: parameter to indicate whether to verify ssl
            * **ssl**: this parameter allows to specify a custom ssl context
            * **timeouts**: parameter to indicate timeouts for request
            * **follow**: parameter to indicate whether to follow redirects
            * **http2**: flag to indicate whether to use http2 (experimental)
        """
        headers = deepcopy(headers) if headers else HttpHeaders()

        if json is not None:
            if data is not None and data != b"":
                raise TypeError("json and data arguments provided, use just one.")
            data = json_serializer(json)
            http_parser.add_header(headers, "Content-Type", "application/json")

        urlparsed = http_parser.get_url_parsed(url)

        boundary = None
        headers = HttpHeaders(deepcopy(headers)) if headers else []
        body: ParsedBodyType = b""

        if self.handle_cookies:
            self._add_cookies_to_request(str(urlparsed.hostname), headers)

        if method != "GET" and data and not multipart:
            body = http_parser.setup_body_request(data, headers)
        elif multipart:
            if not isinstance(data, dict):
                raise ValueError("data should be dict")
            boundary = "boundary-%d" % randint(*RANDOM_RANGE)
            body = await _send_multipart(data, boundary, headers)

        max_redirects = 30
        # if class or request method has false, it will be false
        verify_ssl = verify and self.verify_ssl
        reconnect_times = 3
        while reconnect_times > 0:
            headers_data = partial(
                _prepare_request_headers,
                url=urlparsed,
                method=method,
                headers=headers,
                params=params,
                multipart=multipart,
                boundary=boundary,
                proxy=self.proxy,
            )
            try:
                response = await wait_for(
                    _do_request(
                        urlparsed,
                        headers_data,
                        self.connector,
                        body,
                        verify_ssl,
                        ssl,
                        timeouts,
                        http2,
                        self.proxy,
                    ),
                    timeout=(timeouts or self.connector.timeouts).request_timeout,
                )

                if self.handle_cookies:
                    self._save_new_cookies(str(urlparsed.hostname), response)

                if follow and response.status_code in {301, 302}:
                    max_redirects -= 1

                    if max_redirects == 0:
                        raise MaxRedirects()

                    if self.handle_cookies:
                        self._add_cookies_to_request(str(urlparsed.hostname), headers)

                    parsed_full_url = http_parser.get_url_parsed(
                        response.headers["location"]
                    )

                    # if full url, will have scheme
                    if parsed_full_url.scheme:
                        urlparsed = parsed_full_url
                    else:
                        urlparsed = http_parser.get_url_parsed(
                            url.replace(urlparsed.path, response.headers["location"])
                        )
                else:
                    return response
            except ConnectionDisconnected:
                reconnect_times -= 1
            except ConnectTimeout:
                raise
            except TimeoutException:
                raise RequestTimeout()
        raise ConnectionDisconnected("retried 3 times unsuccessfully")

    async def wait_requests(self, timeout: int = 30):
        """Wait until all pending requests are done.

        If timeout, returns false.

        This is useful when doing safe shutdown of a process.
        """
        try:
            return await wait_for(self.connector.wait_free_pool(), timeout)
        except TimeoutException:
            return False

    def _add_cookies_to_request(self, host: str, headers: HeadersType):
        """Add cookies to request."""
        host_cookies = self.cookies_map.get(host)
        if host_cookies and not any(
            [header.lower() == "cookie" for header, _ in headers]
        ):
            cookies_str = host_cookies.output(header="Cookie:")
            for cookie_data in cookies_str.split("\r\n"):
                http_parser.add_header(headers, *cookie_data.split(": ", 1))

    def _save_new_cookies(self, host: str, response: HttpResponse):
        """Save new cookies in map."""
        if response.cookies:
            self.cookies_map[host] = response.cookies


async def _proxy_connect(
    connection: Connection, proxy: Proxy, desturl: ParseResult, ssl_context: SSLContext
):
    """Send CONNECT and upgrade connection."""

    port = desturl.port or (443 if desturl.scheme == "https" else 80)
    hostname = _get_hostname(desturl.hostname, port)
    to_send = f"CONNECT {hostname}:{port} HTTP/1.1{_NEW_LINE}"
    to_send += f"HOST: {hostname}:{port}{_NEW_LINE}"
    to_send += f"Proxy-Connection: keep-alive{_NEW_LINE}"
    if proxy.auth:
        to_send += f"Proxy-Authorization: Basic {proxy.auth.decode()}{_NEW_LINE}"
    to_send += _NEW_LINE

    assert connection.writer
    connection.write(to_send.encode())
    await connection.writer.drain()

    connect_response = await connection.read(4096)
    if b"200 Connection established" not in connect_response:
        connection.close()
        raise ConnectionError(
            f"Failed to establish connection through proxy: {connect_response}"
        )

    if sys.version_info >= (3, 11):
        await connection.upgrade(ssl_context)
    else:
        # Manually upgrade the connection to TLS for Python versions < 3.11
        await _update_transport(connection, ssl_context)

    connection.proxy_connected = True


async def _update_transport(connection: Connection, ssl_context):
    transport = connection.writer.transport
    protocol = transport.get_protocol()
    new_transport = await get_loop().start_tls(
        transport, protocol, ssl_context, server_side=False
    )

    writer = connection.writer
    reader = connection.reader
    assert writer

    writer._transport = new_transport
    reader._transport = new_transport

    protocol = new_transport.get_protocol()
    protocol._transport = new_transport
    protocol._over_ssl = True

    writer._protocol = protocol
