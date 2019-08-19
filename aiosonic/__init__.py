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

from typing import Any
from typing import AsyncIterator
from typing import Dict
from typing import Iterator
from typing import Union
from typing import Tuple
from typing import Optional
from typing import Sequence

from aiosonic_utils.structures import CaseInsensitiveDict
from aiosonic.version import VERSION
from aiosonic.connectors import TCPConnector
from aiosonic.connectors import Connection
from aiosonic.utils import cache_decorator
from aiosonic.exceptions import ConnectTimeout
from aiosonic.exceptions import RequestTimeout
from aiosonic.exceptions import HttpParsingError
from aiosonic.exceptions import MissingWriterException
from aiosonic.exceptions import MaxRedirects


# VARIABLES
HTTP_RESPONSE_STATUS_LINE = (r'HTTP/(?P<version>(\d.)?(\d)) (?P<code>\d+) '
                             r'(?P<reason>[\w]*)')
_CACHE: Dict[str, Any] = {}
_LRU_CACHE_SIZE = 512
_CHUNK_SIZE = 1024 * 4  # 4kilobytes
_NEW_LINE = '\r\n'
_COMPRESSED_OPTIONS = set([b'gzip', b'deflate'])


# TYPES
ParamsType = Union[
    Dict[str, str],
    Sequence[Tuple[str, str]],
]
#: Data to be sent in requests, allowed types
DataType = Union[
    str,
    bytes,
    dict,
    tuple,
    AsyncIterator[bytes],
    Iterator[bytes],
]
BodyType = Union[
    str,
    bytes,
    AsyncIterator[bytes],
    Iterator[bytes],
]
ParsedBodyType = Union[
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


#: Headers
HeadersType = Union[Dict[str, str], HttpHeaders]


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

    def set_response_initial(self, data: bytes):
        """Parse first bytes from http response."""
        res = re.match(HTTP_RESPONSE_STATUS_LINE, data.decode().rstrip())
        if not res:
            raise HttpParsingError('response line parsing error')
        self.response_initial = res.groupdict()

    def _set_header(self, key: str, val: str):
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
                     headers: HeadersType = None, params: ParamsType = None,
                     multipart: bool = None, boundary: str = None) -> str:
    """Prepare get data."""
    path = url.path or '/'
    if params:
        query = urlencode(params)
        path += '%s' % query if '?' in path else '?%s' % query
    get_base = '%s %s HTTP/1.1%s' % (method, path, _NEW_LINE)

    port = url.port or (
        443 if url.scheme == 'https' else 80)
    hostname = url.hostname

    if port != 80:
        hostname += ':' + str(port)

    headers_base = {
        'HOST': hostname,
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


def _setup_body_request(
        data: DataType, headers: HeadersType) -> ParsedBodyType:
    """Get body to be sent."""
    if isinstance(data, (AsyncIterator, Iterator)):
        headers['Transfer-Encoding'] = 'chunked'
        return data
    body: BodyType = b''
    content_type = None

    if isinstance(data, (Dict, tuple)):
        body = urlencode(data)
        content_type = 'application/x-www-form-urlencoded'
    else:
        body = data
        content_type = 'text/plain'

    if 'content-type' not in headers:
        headers['Content-Type'] = content_type

    body = body.encode() if isinstance(body, str) else body
    headers['Content-Length'] = str(len(body))
    return body


def _handle_chunk(chunk: bytes, connection: Connection):
    """Handle chunk sending in transfer-encoding chunked."""
    chunk_size = hex(len(chunk)).replace('0x', '') + _NEW_LINE

    if not connection.writer:
        raise MissingWriterException('missing writer in connection')

    connection.writer.write(
        chunk_size.encode() + chunk + _NEW_LINE.encode()
    )


async def _send_chunks(connection: Connection, body: BodyType):
    """Send chunks."""
    if isinstance(body, AsyncIterator):
        async for chunk in body:
            _handle_chunk(chunk, connection)
    elif isinstance(body, Iterator):
        for chunk in body:
            _handle_chunk(chunk, connection)
    else:
        raise ValueError('wrong body param.')

    if not connection.writer:
        raise MissingWriterException('missing writer in connection')
    connection.writer.write(('0' + _NEW_LINE * 2).encode())


async def _send_multipart(data: Dict[str, str], boundary: str,
                          headers: HeadersType,
                          chunk_size: int = _CHUNK_SIZE) -> bytes:
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
    headers['Content-Length'] = str(len(to_send))
    return to_send


async def _do_request(urlparsed: ParseResult, headers_data: str,
                      connector: TCPConnector, body: Optional[ParsedBodyType],
                      verify: bool, ssl: Optional[SSLContext],
                      follow: bool) -> HttpResponse:
    """Something."""
    async with (await connector.acquire(urlparsed)) as connection:
        await connection.connect(urlparsed, verify, ssl)
        to_send = headers_data.encode()

        if not connection.writer or not connection.reader:
            raise ConnectionError('Not connection writer or reader')
        connection.writer.write(to_send)

        if body:
            if isinstance(body, (AsyncIterator, Iterator)):
                await _send_chunks(connection, body)
            else:
                connection.writer.write(body)

        response = HttpResponse()

        # get response code and version
        response.set_response_initial(await connection.reader.readline())

        res_data = None
        # reading headers
        while True:
            res_data = await connection.reader.readline()
            if b': ' not in res_data:
                break
            response._set_header(*HttpHeaders._clear_line(res_data))

        size = response.headers.get(b'content-length')
        chunked = response.headers.get(b'transfer-encoding', '') == b'chunked'
        keepalive = b'close' not in response.headers.get(b'connection', b'')
        response.compressed = response.headers.get(b'content-encoding', '')

        if size:
            response._set_body(await connection.reader.read(int(size)))

        if chunked:
            connection.block_until_read_chunks()
            response.chunked = True

        if keepalive:
            connection.keep_alive()
            response._set_connection(connection)
        return response


# Module methods
async def get(url: str, headers: HeadersType = None,
              params: ParamsType = None,
              connector: TCPConnector = None, verify: bool = True,
              ssl: SSLContext = None,
              follow: bool = False) -> HttpResponse:
    """Do get http request. """
    return await request(url, 'GET', headers, params, connector=connector,
                         verify=verify, ssl=ssl, follow=follow)


async def _request_with_body(
        url: str, method: str, data: DataType = None,
        headers: HeadersType = None, json: dict = None,
        params: ParamsType = None, connector: TCPConnector = None,
        json_serializer=dumps, multipart: bool = False,
        verify: bool = True, ssl: SSLContext = None,
        follow: bool = False) -> HttpResponse:
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
                         multipart, verify=verify, ssl=ssl, follow=follow)


async def post(url: str, data: DataType = None, headers: HeadersType = None,
               json: dict = None, params: ParamsType = None,
               connector: TCPConnector = None, json_serializer=dumps,
               multipart: bool = False, verify: bool = True,
               ssl: SSLContext = None,
               follow: bool = False) -> HttpResponse:
    """Do post http request. """
    return await _request_with_body(
        url, 'POST', data, headers, json, params, connector, json_serializer,
        multipart, verify=verify, ssl=ssl, follow=follow)


async def put(url: str, data: DataType = None, headers: HeadersType = None,
              json: dict = None, params: ParamsType = None,
              connector: TCPConnector = None, json_serializer=dumps,
              multipart: bool = False, verify: bool = True,
              ssl: SSLContext = None,
              follow: bool = False) -> HttpResponse:
    """Do put http request. """
    return await _request_with_body(
        url, 'PUT', data, headers, json, params, connector, json_serializer,
        multipart, verify=verify, ssl=ssl, follow=follow)


async def patch(url: str, data: DataType = None, headers: HeadersType = None,
                json: dict = None, params: ParamsType = None,
                connector: TCPConnector = None, json_serializer=dumps,
                multipart: bool = False, verify: bool = True,
                ssl: SSLContext = None,
                follow: bool = False) -> HttpResponse:
    """Do patch http request. """
    return await _request_with_body(
        url, 'PATCH', data, headers, json, params, connector, json_serializer,
        multipart, verify=verify, ssl=ssl, follow=follow)


async def delete(url: str, data: DataType = b'', headers: HeadersType = None,
                 json: dict = None, params: ParamsType = None,
                 connector: TCPConnector = None, json_serializer=dumps,
                 multipart: bool = False, verify: bool = True,
                 ssl: SSLContext = None,
                 follow: bool = False) -> HttpResponse:
    """Do delete http request. """
    return await _request_with_body(
        url, 'DELETE', data, headers, json, params, connector, json_serializer,
        multipart, verify=verify, ssl=ssl, follow=follow)


async def request(url: str, method: str = 'GET', headers: HeadersType = None,
                  params: ParamsType = None, data: DataType = None,
                  connector: TCPConnector = None, multipart: bool = False,
                  verify: bool = True,
                  ssl: SSLContext = None,
                  follow: bool = False) -> HttpResponse:
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

    boundary = None
    headers = headers or {}
    body: ParsedBodyType = b''

    if method != 'GET' and data and not multipart:
        body = _setup_body_request(data, headers)
    elif multipart:
        if not isinstance(data, dict):
            raise ValueError('data should be dict')
        boundary = 'boundary-%d' % random.randint(10**8, 10**9)
        body = await _send_multipart(data, boundary, headers)

    max_redirects = 30
    while True:
        headers_data = _get_header_data(
            urlparsed, method, headers, params, multipart, boundary)
        try:
            response = await asyncio.wait_for(
                _do_request(
                    urlparsed, headers_data, connector, body, verify, ssl,
                    follow),
                timeout=connector.request_timeout
            )

            if follow and response.status_code in {301, 302}:
                max_redirects -= 1

                if max_redirects == 0:
                    raise MaxRedirects()

                parsed_full_url = _get_url_parsed(
                    response.headers[b'location'].decode())

                # if full url, will have scheme
                if parsed_full_url.scheme:
                    urlparsed = parsed_full_url
                else:
                    urlparsed = _get_url_parsed(url.replace(
                        urlparsed.path, response.headers[
                            b'location'].decode()))
            else:
                return response
        except ConnectTimeout:
            raise
        except futures._base.TimeoutError:
            raise RequestTimeout()
