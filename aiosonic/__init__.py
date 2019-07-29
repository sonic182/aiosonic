"""Main module."""

import re

from functools import lru_cache
from urllib.parse import urlparse
from urllib.parse import ParseResult

from aiosonic.structures import CaseInsensitiveDict
from aiosonic.version import VERSION
from aiosonic.connectors import TCPConnector


HTTP_RESPONSE_STATUS_LINE = (r'HTTP/(?P<version>(\d.)?(\d)) (?P<code>\d+) '
                             r'(?P<reason>[\w]*)')
CACHE = {}


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


def get_header_data(url: ParseResult, method: str, headers: dict = None):
    """Prepare get data."""
    path = url.path or '/'
    get_base = 'GET %s HTTP/1.1\n' % path
    headers_base = {
        'HOST': url.hostname,
        'User-Agent': 'aioload/%s' % VERSION
    }

    if headers:
        headers_base.update(headers)

    for key, data in headers_base.items():
        get_base += '%s: %s\n' % (key, data)
    return get_base + '\n'


@lru_cache(512)
def get_url_parsed(url: str):
    return urlparse(url)


async def get(url: str, connector: TCPConnector = None):
    """Do get http request. """
    return await request(url, 'get')


async def post(url: str, connector: TCPConnector = None):
    """Do get http request. """
    return await request(url, 'post')


async def request(url: str, method: str = 'get',
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
        connector = CACHE[key] = CACHE.get(key) or TCPConnector()
    urlparsed = get_url_parsed(url)

    headers_data = get_header_data(urlparsed, method)

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
