"""Main module."""

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


HTTP_RESPONSE_STATUS_LINE = (r'HTTP/(?P<version>(\d.)?(\d)) (?P<code>\d+) '
                             r'(?P<reason>[\w]*)')
_CACHE = {}
_LRU_CACHE_SIZE = 512


STRING_OR_BYTES = Union[str, bytes]
PARAMS_TYPE = Union[
    Dict[STRING_OR_BYTES, STRING_OR_BYTES],
    Tuple[STRING_OR_BYTES, STRING_OR_BYTES],
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


def _get_header_data(url: ParseResult, method: str, params: dict = None,
                     headers: dict = None):
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


# Module methods


async def get(url: str, params: PARAMS_TYPE = None,
              connector: TCPConnector = None):
    """Do get http request. """
    return await request(url, 'GET', params)


async def post(url: str, params: PARAMS_TYPE = None,
               connector: TCPConnector = None):
    """Do get http request. """
    return await request(url, 'POST', params)


async def request(url: str, method: str = 'GET', params: PARAMS_TYPE = None,
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

    headers_data = _get_header_data(urlparsed, method, params)

    async with (await connector.acquire()) as connection:
        await connection.connect(urlparsed)

        connection.writer.write(headers_data.encode())
        # await writer.drain()

        response = HTTPResponse()

        # get response code and version
        response.set_response_initial(await connection.reader.readline())

        data = None
        # reading headers
        while True:
            data = await connection.reader.readline()
            if b': ' not in data:
                break
            response.set_header(*HTTPHeaders.clear_line(data))

        size = response.headers.get(b'content-length')

        if size:
            response.body = await connection.reader.read(int(size))

        keepalive = b'keep-alive' in response.headers.get(b'connection', b'')

        if keepalive:
            connection.keep_alive()
        return response
