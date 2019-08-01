"""Main module."""

import asyncio
import random
import re
from concurrent import futures
from json import dumps
from ssl import SSLContext

from functools import lru_cache
from io import IOBase
from os.path import basename
from urllib.parse import urlparse
from urllib.parse import urlencode
from urllib.parse import ParseResult

from typing import Union
from typing import Dict
from typing import Tuple

from aiosonic.structures import CaseInsensitiveDict
from aiosonic.version import VERSION
from aiosonic.connectors import TCPConnector
from aiosonic.exceptions import RequestTimeout
from aiosonic.exceptions import ConnectTimeout


# VARIABLES
HTTP_RESPONSE_STATUS_LINE = (r'HTTP/(?P<version>(\d.)?(\d)) (?P<code>\d+) '
                             r'(?P<reason>[\w]*)')
_CACHE = {}
_LRU_CACHE_SIZE = 512
_CHUNK_SIZE = 1024 * 4
_NEW_LINE = '\r\n'


# TYPES
StringOrBytes = Union[str, bytes]
HeadersType = Dict[StringOrBytes, StringOrBytes]
ParamsType = Union[
    Dict[StringOrBytes, StringOrBytes],
    Tuple[StringOrBytes, StringOrBytes],
]
DataType = Union[
    StringOrBytes,
    dict,
    tuple,
]


# Functions with cache
@lru_cache(_LRU_CACHE_SIZE)
def get_url_parsed(url: str) -> ParseResult:
    """Get url parsed.

    With lru_cache decorator for the sake of speed.
    """
    return urlparse(url)


# Classes


class HTTPHeaders(CaseInsensitiveDict):
    """Http headers dict."""

    @staticmethod
    def clear_line(line: bytes):
        """Clear readed line."""
        return line.rstrip().split(b': ')


class HTTPResponse:
    """HTTPResponse.

    Class for handling response.
    """

    def __init__(self):
        self.headers = HTTPHeaders()
        self.body = None
        self.response_initial = None

    def set_response_initial(self, data: str):
        """Read first bytes from socket and set it in response."""
        res = re.match(HTTP_RESPONSE_STATUS_LINE, data.decode().rstrip())
        self.response_initial = res.groupdict()

    def set_header(self, key, val):
        """Set header to response."""
        self.headers[key] = val

    @property
    def status_code(self):
        """Get status code."""
        return int(self.response_initial['code'])


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


def _get_body(data: DataType, headers: HeadersType):
    """Get body to be sent."""
    body = data
    if 'content-type' not in headers:
        body = urlencode(data)
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    body = body.encode()
    headers['Content-Length'] = len(body)
    return body


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
            to_send += b'Content-Disposition: form-data; name="%s"%s%s' % (
                key.encode(),
                _NEW_LINE,
                _NEW_LINE
            )

            to_send += val.encode() + b'\r\n'

    # write --boundary-- for finish
    to_send += ('--%s--' % boundary).encode()
    headers['Content-Length'] = len(to_send)
    return to_send


async def _do_request(urlparsed: ParseResult, headers_data: str,
                      connector: TCPConnector, body: bytes, verify: bool,
                      ssl: SSLContext) -> HTTPResponse:
    """Something."""
    async with (await connector.acquire()) as connection:
        await connection.connect(urlparsed, verify, ssl)

        to_send = headers_data.encode()

        connection.writer.write(to_send)

        if body:
            connection.writer.write(body)

        # print(headers_data, body)
        # print(to_send.decode(), end='')

        # await writer.drain()

        response = HTTPResponse()

        # get response code and version
        response.set_response_initial(await connection.reader.readline())

        res_data = None
        # reading headers
        while True:
            res_data = await connection.reader.readline()
            if b': ' not in res_data:
                break
            response.set_header(*HTTPHeaders.clear_line(res_data))

        size = response.headers.get(b'content-length')

        if size:
            response.body = await connection.reader.read(int(size))

        keepalive = b'close' not in response.headers.get(b'keep-alive', b'')

        if keepalive:
            connection.keep_alive()
        return response


# Module methods
async def get(url: str, headers: HeadersType = None,
              params: ParamsType = None,
              connector: TCPConnector = None, verify: bool = True,
              ssl: SSLContext = None) -> HTTPResponse:
    """Do get http request. """
    return await request(url, 'GET', headers, params, connector=connector,
                         verify=verify, ssl=ssl)


async def _request_with_body(
        url: str, method: str, data: DataType = None,
        headers: HeadersType = None, json: dict = None,
        params: ParamsType = None, connector: TCPConnector = None,
        json_serializer=dumps, multipart: bool = False,
        verify: bool = True, ssl: SSLContext = None) -> HTTPResponse:
    """Do post http request. """
    if not data and not json:
        TypeError('missing argument, either "json" or "data"')
    if json:
        data = json_serializer(json)
        headers = headers or HTTPHeaders()
        headers.update({
            'Content-Type': 'application/json'
        })
    return await request(url, method, headers, params, data, connector,
                         multipart, verify=verify, ssl=ssl)


async def post(url: str, data: DataType = None, headers: HeadersType = None,
               json: dict = None, params: ParamsType = None,
               connector: TCPConnector = None, json_serializer=dumps,
               multipart: bool = False, verify: bool = True,
               ssl: SSLContext = None) -> HTTPResponse:
    """Do post http request. """
    return await _request_with_body(
        url, 'POST', data, headers, json, params, connector, json_serializer,
        multipart, verify=verify, ssl=ssl)


async def put(url: str, data: DataType = None, headers: HeadersType = None,
              json: dict = None, params: ParamsType = None,
              connector: TCPConnector = None, json_serializer=dumps,
              multipart: bool = False, verify: bool = True,
              ssl: SSLContext = None) -> HTTPResponse:
    """Do put http request. """
    return await _request_with_body(
        url, 'PUT', data, headers, json, params, connector, json_serializer,
        multipart, verify=verify, ssl=ssl)


async def patch(url: str, data: DataType = None, headers: HeadersType = None,
                json: dict = None, params: ParamsType = None,
                connector: TCPConnector = None, json_serializer=dumps,
                multipart: bool = False, verify: bool = True,
                ssl: SSLContext = None) -> HTTPResponse:
    """Do put http request. """
    return await _request_with_body(
        url, 'PATCH', data, headers, json, params, connector, json_serializer,
        multipart, verify=verify, ssl=ssl)


async def delete(url: str, data: DataType = b'', headers: HeadersType = None,
                 json: dict = None, params: ParamsType = None,
                 connector: TCPConnector = None, json_serializer=dumps,
                 multipart: bool = False, verify: bool = True,
                 ssl: SSLContext = None) -> HTTPResponse:
    """Do put http request. """
    return await _request_with_body(
        url, 'DELETE', data, headers, json, params, connector, json_serializer,
        multipart, verify=verify, ssl=ssl)


async def request(url: str, method: str = 'GET', headers: HeadersType = None,
                  params: ParamsType = None, data: DataType = None,
                  connector: TCPConnector = None, multipart: bool = False,
                  verify: bool = True,
                  ssl: SSLContext = None) -> HTTPResponse:
    """Requests.

    Steps:
    * Prepare request data
    * Open connection
    * Send request data
    * Wait for response data
    """
    if not connector:
        key = 'connector_base'
        connector = _CACHE[key] = _CACHE.get(key) or TCPConnector()
    urlparsed = get_url_parsed(url)

    body = None
    boundary = None
    headers = headers or {}

    if method != 'GET' and data and not multipart:
        body = _get_body(data, headers)
    elif multipart:
        boundary = 'boundary-%d' % random.randint(1, 255)
        body = await _send_multipart(data, boundary, headers)

    headers_data = _get_header_data(
        urlparsed, method, headers, params, multipart, boundary)
    # return await _do_request(urlparsed, headers_data, connector, body)
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
