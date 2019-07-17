"""Main module."""

import asyncio

import re
from urllib.parse import urlparse
from urllib.parse import ParseResult

from aiosonic.structures import CaseInsensitiveDict
from aiosonic.version import VERSION


HTTP_RESPONSE_STATUS_LINE = (r'HTTP/(?P<version>(\d.)?(\d)) (?P<code>\d+) '
                             r'(?P<reason>[\w]*)')


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


def get_header_data(url: ParseResult, headers=None):
    """Prepare get data."""
    path = url.path or '/'
    get_base = f'GET {path} HTTP/1.1\n'
    headers_base = {
        'HOST': url.hostname,
        'User-Agent': f'aioload/{VERSION}'
    }

    if headers:
        headers_base.update(headers)

    for key, data in headers_base.items():
        get_base += f'{key}: {data}\n'
    return get_base + '\n'


async def get(url: str):
    """Do get http request.

    Steps:
    * Prepare request data
    * Open connection
    * Send request data
    * Wait for response data
    """
    urlparsed = urlparse(url)

    headers_data = get_header_data(urlparsed)

    reader, writer = await asyncio.open_connection(
        urlparsed.hostname, urlparsed.port)

    writer.write(headers_data.encode())
    await writer.drain()

    response = HTTPResponse()

    # get response code and version
    response.set_response_initial(await reader.readline())

    data = None
    # reading headers
    while True:
        data = await reader.readline()
        if b': ' not in data:
            break
        response.set_header(*HTTPHeaders.clear_line(data))
    size = response.headers.get(b'content-length')
    if size:
        response.body = await reader.read(int(size))

    writer.close()
    await writer.wait_closed()
    return response
