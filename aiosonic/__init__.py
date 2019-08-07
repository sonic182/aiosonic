"""Main module."""

import asyncio
import random
import re
from concurrent import futures
from json import dumps
from ssl import SSLContext
import gzip
import zlib

from io import IOBase
from os.path import basename
from urllib.parse import urlparse
from urllib.parse import urlencode
from urllib.parse import ParseResult

from typing import Union
from typing import Dict
from typing import Tuple
from typing import AsyncIterator
from typing import Iterator

from aiosonic_utils.structures import CaseInsensitiveDict
from aiosonic.version import VERSION
from aiosonic.connectors import TCPConnector
from aiosonic.connectors import Connection
from aiosonic.utils import cache_decorator
from aiosonic.exceptions import ConnectTimeout
from aiosonic.exceptions import RequestTimeout


# VARIABLES
HTTP_RESPONSE_STATUS_LINE = (r'HTTP/(?P<version>(\d.)?(\d)) (?P<code>\d+) '
                             r'(?P<reason>[\w]*)')
_CACHE = {}
_LRU_CACHE_SIZE = 512
_CHUNK_SIZE = 1024 * 4  # 4kilobytes
_NEW_LINE = '\r\n'
_COMPRESSED_OPTIONS = set([b'gzip', b'deflate'])


# TYPES
StringOrBytes = Union[str, bytes]
#: Headers
HeadersType = Dict[StringOrBytes, StringOrBytes]
ParamsType = Union[
    Dict[StringOrBytes, StringOrBytes],
    Tuple[StringOrBytes, StringOrBytes],
]
#: Data to be sent in requests, allowed types
DataType = Union[
    StringOrBytes,
    AsyncIterator[bytes],
    Iterator[bytes],
    dict,
    tuple,
]
BodyType = Union[
    bytes,
    AsyncIterator[bytes],
    Iterator[bytes],
]


# Functions with cache
@cache_decorator(_LRU_CACHE_SIZE)
def _get_url_parsed(url: str) -> ParseResult:
    """Get url parsed.

    With cache_decorator for the sake of speed.
    """
    return urlparse(url)


# Classes


class HttpHeaders(CaseInsensitiveDict):
    """Http headers dict."""

    @staticmethod
    def _clear_line(line: bytes):
        """Clear readed line."""
        return line.rstrip().split(b': ')


class HttpResponse:
    """HttpResponse.

    Class for handling response.
    """

    def __init__(self):
        self.headers = HttpHeaders()
        self.body = b''
        self.response_initial = None
        self.connection = None
        self.chunked = False
        self.compressed = b''
        self.chunks_readed = False

    def _set_response_initial(self, data: bytes):
        """Read first bytes from socket and set it in response."""
        res = re.match(HTTP_RESPONSE_STATUS_LINE, data.decode().rstrip())
        self.response_initial = res.groupdict()

    def _set_header(self, key: StringOrBytes, val: StringOrBytes):
        """Set header to response."""
        self.headers[key] = val

    def _set_connection(self, connection: Connection):
        """Set header to response."""
        self.connection = connection

    @property
    def status_code(self):
        """Get status code."""
        return int(self.response_initial['code'])

    def _set_body(self, data):
        """Set body."""
        if self.compressed == b'gzip':
            self.body += gzip.decompress(data)
        elif self.compressed == b'deflate':
            self.body += zlib.decompress(data)
        else:
            self.body += data

    async def content(self) -> bytes:
        """Read response body."""
        if self.chunked and not self.body:
            res = b''
            async for chunk in self.read_chunks():
                res += chunk
            self._set_body(res)
        return self.body

    async def text(self) -> str:
        """Read response body."""
        return (await self.content()).decode()

    async def read_chunks(self) -> AsyncIterator[bytes]:
        """Read chunks from chunked response."""
        while True and not self.chunks_readed:
            chunk_size = int((
                await self.connection.reader.readline()).rstrip(), 16)
            if not chunk_size:
                # read last CRLF
                await self.connection.reader.readline()
                # free connection
                await self.connection.release()
                break
            chunk = await self.connection.reader.readexactly(
                chunk_size + 2)
            yield chunk[:-2]
        self.chunks_readed = True


def _get_header_data(url: ParseResult, method: str,
                     headers: HeadersType = None, params: dict = None,
                     multipart: bool = None, boundary: str = None) -> bytes:
    """Prepare get data."""
    path = url.path or '/'
    if params:
        query = urlencode(params)
        path += '%s' % query if '?' in path else '?%s' % query
    get_base = '%s %s HTTP/1.1%s' % (method, path, _NEW_LINE)
    headers_base = {
        'HOST': url.hostname,
        'Connection': 'keep-alive',
        'User-Agent': 'aioload/%s' % VERSION
    }

    if multipart:
        headers_base[
            'Content-Type'] = 'multipart/form-data; boundary="%s"' % boundary

    if headers:
        headers_base.update(headers)

    for key, data in headers_base.items():
        get_base += '%s: %s%s' % (key, data, _NEW_LINE)
    return get_base + _NEW_LINE


def _setup_body_request(data: DataType, headers: HeadersType):
    """Get body to be sent."""
    if isinstance(data, (AsyncIterator, Iterator)):
        headers['Transfer-Encoding'] = 'chunked'
        return data
    body = data
    if 'content-type' not in headers:
        if isinstance(data, (Dict, Iterator)):
            body = urlencode(data)
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            body = data
            headers['Content-Type'] = 'text/plain'
    body = body.encode() if isinstance(body, str) else body
    headers['Content-Length'] = len(body)
    return body


def _handle_chunk(chunk: bytes, connection: TCPConnector):
    """Handle chunk sending in transfer-encoding chunked."""
    chunk_size = hex(len(chunk)).replace('0x', '') + _NEW_LINE
    connection.writer.write(
        chunk_size.encode() + chunk + _NEW_LINE.encode()
    )


async def _send_chunks(connection: TCPConnector, body: BodyType):
    """Send chunks."""
    if isinstance(body, AsyncIterator):
        async for chunk in body:
            _handle_chunk(chunk, connection)
    else:
        for chunk in body:
            _handle_chunk(chunk, connection)
    connection.writer.write(('0' + _NEW_LINE * 2).encode())


async def _send_multipart(data: DataType, boundary: str, headers: HeadersType,
                          chunk_size: int = _CHUNK_SIZE):
    """Send multipart data by streaming."""
    # TODO: precalculate body size and stream request, precalculate file sizes by os.path.getsize
    to_send = b''
    for key, val in data.items():
        # write --boundary + field
        to_send += ('--%s%s' % (boundary, _NEW_LINE)).encode()
        if isinstance(val, IOBase):
            # TODO: Utility to accept files with multipart metadata (Content-Type, custom filename, ...),
            # write Contet-Disposition
            to_write = 'Content-Disposition: form-data; ' + \
                'name="%s"; filename="%s"%s%s' % (
                    key, basename(val.name), _NEW_LINE, _NEW_LINE)
            to_send += to_write.encode()
            # read and write chunks
            loop = asyncio.get_event_loop()
            while True:
                data = await loop.run_in_executor(
                    None, val.read, chunk_size)
                if not data:
                    break
                to_send += data
            val.close()
        else:
            to_send += (
                'Content-Disposition: form-data; name="%s"%s%s' % (
                    key,
                    _NEW_LINE,
                    _NEW_LINE
                )
            ).encode()
            to_send += val.encode() + _NEW_LINE.encode()

    # write --boundary-- for finish
    to_send += ('--%s--' % boundary).encode()
    headers['Content-Length'] = len(to_send)
    return to_send


async def _do_request(urlparsed: ParseResult, headers_data: str,
                      connector: TCPConnector, body: BodyType, verify: bool,
                      ssl: SSLContext) -> HttpResponse:
    """Something."""
    async with (await connector.acquire(urlparsed)) as connection:
        await connection.connect(urlparsed, verify, ssl)

        to_send = headers_data.encode()

        connection.writer.write(to_send)

        if body:
            if isinstance(body, (AsyncIterator, Iterator)):
                await _send_chunks(connection, body)
            else:
                connection.writer.write(body)

        response = HttpResponse()

        # get response code and version
        response._set_response_initial(await connection.reader.readline())

        res_data = None
        # reading headers
        while True:
            res_data = await connection.reader.readline()
            if b': ' not in res_data:
                break
            response._set_header(*HttpHeaders._clear_line(res_data))

        size = response.headers.get(b'content-length')
        chunked = b'chunked' == response.headers.get(b'transfer-encoding', '')
        response.compressed = response.headers.get(b'content-encoding', '')

        if size:
            response._set_body(await connection.reader.read(int(size)))

        if chunked:
            connection.block_until_read_chunks()
            response.chunked = True

        keepalive = b'close' not in response.headers.get(b'connection', b'')

        if keepalive:
            connection.keep_alive()
            response._set_connection(connection)
        return response


# Module methods
async def get(url: str, headers: HeadersType = None,
              params: ParamsType = None,
              connector: TCPConnector = None, verify: bool = True,
              ssl: SSLContext = None) -> HttpResponse:
    """Do get http request. """
    return await request(url, 'GET', headers, params, connector=connector,
                         verify=verify, ssl=ssl)


async def _request_with_body(
        url: str, method: str, data: DataType = None,
        headers: HeadersType = None, json: dict = None,
        params: ParamsType = None, connector: TCPConnector = None,
        json_serializer=dumps, multipart: bool = False,
        verify: bool = True, ssl: SSLContext = None) -> HttpResponse:
    """Do post http request. """
    if not data and not json:
        TypeError('missing argument, either "json" or "data"')
    if json:
        data = json_serializer(json)
        headers = headers or HttpHeaders()
        headers.update({
            'Content-Type': 'application/json'
        })
    return await request(url, method, headers, params, data, connector,
                         multipart, verify=verify, ssl=ssl)


async def post(url: str, data: DataType = None, headers: HeadersType = None,
               json: dict = None, params: ParamsType = None,
               connector: TCPConnector = None, json_serializer=dumps,
               multipart: bool = False, verify: bool = True,
               ssl: SSLContext = None) -> HttpResponse:
    """Do post http request. """
    return await _request_with_body(
        url, 'POST', data, headers, json, params, connector, json_serializer,
        multipart, verify=verify, ssl=ssl)


async def put(url: str, data: DataType = None, headers: HeadersType = None,
              json: dict = None, params: ParamsType = None,
              connector: TCPConnector = None, json_serializer=dumps,
              multipart: bool = False, verify: bool = True,
              ssl: SSLContext = None) -> HttpResponse:
    """Do put http request. """
    return await _request_with_body(
        url, 'PUT', data, headers, json, params, connector, json_serializer,
        multipart, verify=verify, ssl=ssl)


async def patch(url: str, data: DataType = None, headers: HeadersType = None,
                json: dict = None, params: ParamsType = None,
                connector: TCPConnector = None, json_serializer=dumps,
                multipart: bool = False, verify: bool = True,
                ssl: SSLContext = None) -> HttpResponse:
    """Do patch http request. """
    return await _request_with_body(
        url, 'PATCH', data, headers, json, params, connector, json_serializer,
        multipart, verify=verify, ssl=ssl)


async def delete(url: str, data: DataType = b'', headers: HeadersType = None,
                 json: dict = None, params: ParamsType = None,
                 connector: TCPConnector = None, json_serializer=dumps,
                 multipart: bool = False, verify: bool = True,
                 ssl: SSLContext = None) -> HttpResponse:
    """Do delete http request. """
    return await _request_with_body(
        url, 'DELETE', data, headers, json, params, connector, json_serializer,
        multipart, verify=verify, ssl=ssl)


async def request(url: str, method: str = 'GET', headers: HeadersType = None,
                  params: ParamsType = None, data: DataType = None,
                  connector: TCPConnector = None, multipart: bool = False,
                  verify: bool = True,
                  ssl: SSLContext = None) -> HttpResponse:
    """Do http request.

    Steps:

    * Prepare request meta (headers)
    * Open connection
    * Send request data
    * Wait for response data
    """
    if not connector:
        key = 'connector_base'
        connector = _CACHE[key] = _CACHE.get(key) or TCPConnector()
    urlparsed = _get_url_parsed(url)

    body = None
    boundary = None
    headers = headers or {}

    if method != 'GET' and data and not multipart:
        body = _setup_body_request(data, headers)
    elif multipart:
        boundary = 'boundary-%d' % random.randint(10**8, 10**9)
        body = await _send_multipart(data, boundary, headers)

    headers_data = _get_header_data(
        urlparsed, method, headers, params, multipart, boundary)
    try:
        return await asyncio.wait_for(
            _do_request(
                urlparsed, headers_data, connector, body, verify, ssl),
            timeout=connector.request_timeout
        )
    except ConnectTimeout:
        raise
    except futures._base.TimeoutError:
        raise RequestTimeout()
