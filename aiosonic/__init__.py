"""Main module."""

import json
import re

from functools import lru_cache
from urllib.parse import urlparse
from urllib.parse import urlencode
from urllib.parse import ParseResult

from typing import Union
from typing import Dict
from typing import Tuple

from aiosonic.structures import CaseInsensitiveDict
from aiosonic.version import VERSION
from aiosonic.connectors import TCPConnector


# VARIABLES
HTTP_RESPONSE_STATUS_LINE = (r'HTTP/(?P<version>(\d.)?(\d)) (?P<code>\d+) '
                             r'(?P<reason>[\w]*)')
_CACHE = {}
_LRU_CACHE_SIZE = 512


# TYPES
STRING_OR_BYTES = Union[str, bytes]
HEADERS_TYPE = Dict[STRING_OR_BYTES, STRING_OR_BYTES]
PARAMS_TYPE = Union[
    Dict[STRING_OR_BYTES, STRING_OR_BYTES],
    Tuple[STRING_OR_BYTES, STRING_OR_BYTES],
]
DATA_TYPE = Union[
    STRING_OR_BYTES,
    dict,
    tuple,
]


# Functions with cache
@lru_cache(_LRU_CACHE_SIZE)
def get_url_parsed(url: str):
    return urlparse(url)


# Classes


class HTTPHeaders(CaseInsensitiveDict):
    """Http headers dict."""

    @staticmethod
    def clear_line(line: bytes):
        """Clear readed line."""
        return line.rstrip().split(b': ')


class HTTPResponse:
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
        return int(self.response_initial['code'])


def _get_header_data(url: ParseResult, method: str,
                     headers: HEADERS_TYPE = None, params: dict = None):
    """Prepare get data."""
    path = url.path or '/'
    if params:
        query = urlencode(params)
        path += '%s' % query if '?' in path else '?%s' % query
    get_base = '%s %s HTTP/1.1\n' % (method, path)
    headers_base = {
        'HOST': url.hostname,
        'User-Agent': 'aioload/%s' % VERSION
    }

    if headers:
        headers_base.update(headers)

    for key, data in headers_base.items():
        get_base += '%s: %s\n' % (key, data)
    return get_base + '\n'


def _get_body(data: DATA_TYPE, headers: HEADERS_TYPE):
    """Get body to be sent."""
    body = data
    if 'content-type' not in headers:
        body = urlencode(data)
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    body = body.encode()
    headers['Content-Length'] = len(body)
    return body


# Module methods
async def get(url: str, headers: HEADERS_TYPE = None,
              params: PARAMS_TYPE = None, connector: TCPConnector = None):
    """Do get http request. """
    return await request(url, 'GET', headers, params, connector=connector)


async def post(url: str, data: DATA_TYPE = None, headers: HEADERS_TYPE = None,
               json: dict = None, params: PARAMS_TYPE = None,
               connector: TCPConnector = None, json_serialize=json.dumps):
    """Do post http request. """
    if not data and not json:
        TypeError('missing argument, either "json" or "data"')
    if json:
        data = json_serialize(json)
        headers = headers or HTTPHeaders()
        headers.update({
            'Content-Type': 'application/json'
        })
    return await request(url, 'POST', headers, params, data, connector)


async def request(url: str, method: str = 'GET', headers: HEADERS_TYPE = None,
                  params: PARAMS_TYPE = None, data: DATA_TYPE = None,
                  connector: TCPConnector = None):
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
    if method != 'GET' and data:
        headers = headers or {}
        body = _get_body(data, headers)

    headers_data = _get_header_data(urlparsed, method, headers, params)

    async with (await connector.acquire()) as connection:
        await connection.connect(urlparsed)

        connection.writer.write(headers_data.encode())

        if body:
            connection.writer.write(body)

        # print(headers_data.encode() + body)
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

        keepalive = b'keep-alive' in response.headers.get(b'connection', b'')

        if keepalive:
            connection.keep_alive()
        return response
