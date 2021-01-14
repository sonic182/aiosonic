"""Main module."""

import re
from asyncio import get_event_loop, wait_for
from codecs import lookup
from functools import partial
from gzip import decompress as gzip_decompress
from http import cookies
from io import IOBase
from json import dumps, loads
from os.path import basename
from random import randint
from ssl import SSLContext
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
    Union,
)
from urllib.parse import ParseResult, urlencode, urlparse
from zlib import decompress as zlib_decompress

import chardet
from aiosonic.connection import Connection
from aiosonic.connectors import TCPConnector
from aiosonic.exceptions import (
    ConnectTimeout,
    HttpParsingError,
    MaxRedirects,
    MissingWriterException,
    ReadTimeout,
    RequestTimeout,
    TimeoutException,
)
from aiosonic.timeout import Timeouts
from aiosonic.utils import cache_decorator
from aiosonic.version import VERSION
from aiosonic_utils.structures import CaseInsensitiveDict

# TYPES
from aiosonic.types import ParamsType
from aiosonic.types import DataType
from aiosonic.types import BodyType
from aiosonic.types import ParsedBodyType

try:
    import cchardet as chardet
except ImportError:
    pass

# VARIABLES
_HTTP_RESPONSE_STATUS_LINE = re.compile(
    r'HTTP/(?P<version>(\d.)?(\d)) (?P<code>\d+) (?P<reason>[\w]*)')
_CHARSET_RGX = re.compile(r'charset=(?P<charset>[\w-]*);?')
_CACHE: Dict[str, Any] = {}
_LRU_CACHE_SIZE = 512
_CHUNK_SIZE = 1024 * 4  # 4kilobytes
_NEW_LINE = '\r\n'
_COMPRESSED_OPTIONS = set([b'gzip', b'deflate'])


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
        decoded = line.rstrip().decode()
        pair = decoded.split(': ', 1)
        if len(pair) < 2:
            return decoded.split(':')
        return pair


#: Headers
HeadersType = Union[Dict[str, str], List[Tuple[str, str]], HttpHeaders]


def _headers_iterator(headers: HeadersType):
    iterator = headers if isinstance(headers, List) else headers.items()
    for key, data in iterator:
        yield key, data


def _add_headers(headers: HeadersType, headers_to_add: HeadersType):
    """Safe add multiple headers."""
    for key, data in _headers_iterator(headers_to_add):
        _add_header(headers, key, data)


def _add_header(headers: HeadersType, key: str, value: str, replace=False):
    """Safe add header method."""
    if isinstance(headers, List):
        if replace:
            included = [item for item in headers if item[0] == key]
            if included:
                headers.remove(included[0])
        headers.append((key, value))
    else:
        headers[key] = value


async def _parse_headers_iterator(connection: Connection):
    """Transform loop to iterator."""
    while True:
        res_data = await connection.reader.readline()
        if b': ' not in res_data and b':' not in res_data:
            break
        yield res_data


class HttpResponse:
    """Custom HttpResponse class for handling responses.

    Properties:
      * **status_code** (int): response status code
      * **headers** (:class:`aiosonic.HttpHeaders`): headers in case insensitive dict
      * **cookies** (:class:`http.cookies.SimpleCookie`): instance of SimpleCookies
        if cookies present in respone.
      * **raw_headers** (List[Tuple[bytes, bytes]]): headers as raw format
    """

    def __init__(self):
        self.headers = HttpHeaders()
        self.cookies = None
        self.raw_headers = []
        self.body = b''
        self.response_initial = None
        self.connection = None
        self.chunked = False
        self.compressed = b''
        self.chunks_readed = False

    def _set_response_initial(self, data: bytes):
        """Parse first bytes from http response."""
        res = re.match(_HTTP_RESPONSE_STATUS_LINE,
                       data.decode().rstrip('\r\n'))
        if not res:
            raise HttpParsingError('response line parsing error')
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
            if header_tuple[0].lower() == 'set-cookie':
                self._update_cookies(header_tuple)

    def _update_cookies(self, header_tuple):
        """Update jar of cookies."""
        self.cookies = self.cookies or cookies.SimpleCookie()
        self.cookies.load(header_tuple[1])

    def _set_connection(self, connection: Connection):
        """Set header to response."""
        self.connection = connection

    @property
    def status_code(self) -> int:
        """Get status code."""
        return int(self.response_initial['code'])

    def _set_body(self, data):
        """Set body."""
        if self.compressed == 'gzip':
            self.body += gzip_decompress(data)
        elif self.compressed == 'deflate':
            self.body += zlib_decompress(data)
        else:
            self.body += data

    def _get_encoding(self) -> str:
        ctype = self.headers.get('content-type', '').lower()
        res = re.findall(_CHARSET_RGX, ctype)
        encoding = ''

        if res:
            encoding = res[0]

        if encoding:
            try:
                lookup(encoding)
            except LookupError:
                encoding = ''

        if not encoding:
            if 'application' in ctype and 'json' in ctype:
                # RFC 7159 states that the default encoding is UTF-8.
                encoding = 'utf-8'
            else:
                encoding = chardet.detect(self.body)['encoding']
        if not encoding:
            encoding = 'utf-8'

        return encoding.lower()

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
        body = await self.content()
        encoding = self._get_encoding()
        return (body).decode(encoding)

    async def json(self, json_decoder=loads) -> dict:
        """Read response body."""
        assert 'application/json' in self.headers['content-type'].lower()
        body = await self.content()
        return json_decoder(body)

    async def read_chunks(self) -> AsyncIterator[bytes]:
        """Read chunks from chunked response."""
        while True and not self.chunks_readed:
            chunk_size = int((await
                              self.connection.reader.readline()).rstrip(), 16)
            if not chunk_size:
                # read last CRLF
                await self.connection.reader.readline()
                # free connection
                await self.connection.release()
                break
            chunk = await self.connection.reader.readexactly(chunk_size + 2)
            yield chunk[:-2]
        self.chunks_readed = True


def _get_header_data(url: ParseResult,
                     connection: Connection,
                     method: str,
                     headers: HeadersType = None,
                     params: ParamsType = None,
                     multipart: bool = None,
                     boundary: str = None) -> Union[bytes, HeadersType]:
    """Prepare get data."""
    path = url.path or '/'
    if url.query:
        path += '?' + url.query
    http2conn = connection.h2conn

    if params:
        query = urlencode(params)
        path += f'{query}' if '?' in path else f'?{query}'
    uppercase_method = method.upper()
    get_base = f'{uppercase_method} {path} HTTP/1.1{_NEW_LINE}'

    port = url.port or (443 if url.scheme == 'https' else 80)
    hostname = str(url.hostname)

    if port != 80:
        hostname += ':' + str(port)

    headers_base = []
    if http2conn:
        _add_headers(headers_base, {
            ':method': method,
            ':authority': hostname.split(':')[0],
            ':scheme': 'https',
            ':path': path,
            'user-agent': f'aioload/{VERSION}'
        })
    else:
        _add_headers(headers_base, {
            'HOST': hostname,
            'Connection': 'keep-alive',
            'User-Agent': f'aioload/{VERSION}'
        })

    if multipart:
        _add_header(headers_base, 'Content-Type',
                    f'multipart/form-data; boundary="{boundary}"')

    if headers:
        _add_headers(headers_base, headers)

    if http2conn:
        return headers_base

    for key, data in _headers_iterator(headers_base):
        get_base += f'{key}: {data}{_NEW_LINE}'
    return (get_base + _NEW_LINE).encode()


def _setup_body_request(data: DataType,
                        headers: HeadersType) -> ParsedBodyType:
    """Get body to be sent."""

    if isinstance(data, (AsyncIterator, Iterator)):
        _add_header(headers, 'Transfer-Encoding', 'chunked')
        return data
    else:
        body: BodyType = b''
        content_type = None

        if isinstance(data, (Dict, tuple)):
            body = urlencode(data)
            content_type = 'application/x-www-form-urlencoded'
        else:
            body = data
            content_type = 'text/plain'

        if 'content-type' not in headers:
            _add_header(headers, 'Content-Type', content_type)

        body = body.encode() if isinstance(body, str) else body
        _add_header(headers, 'Content-Length', str(len(body)))
        return body


def _handle_chunk(chunk: bytes, connection: Connection):
    """Handle chunk sending in transfer-encoding chunked."""
    chunk_size = hex(len(chunk)).replace('0x', '') + _NEW_LINE

    if not connection.writer:
        raise MissingWriterException('missing writer in connection')

    connection.writer.write(chunk_size.encode() + chunk + _NEW_LINE.encode())


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


async def _send_multipart(data: Dict[str, str],
                          boundary: str,
                          headers: HeadersType,
                          chunk_size: int = _CHUNK_SIZE) -> bytes:
    """Send multipart data by streaming."""
    # TODO: precalculate body size and stream request
    # precalculate file sizes by os.path.getsize

    to_send = b''
    for key, val in data.items():
        # write --boundary + field
        to_send += (f'--{boundary}{_NEW_LINE}').encode()

        if isinstance(val, IOBase):
            # TODO: Utility to accept files with multipart metadata
            # (Content-Type, custom filename, ...),

            # write Contet-Disposition
            to_write = 'Content-Disposition: form-data; ' + \
                'name="%s"; filename="%s"%s%s' % (
                    key, basename(val.name), _NEW_LINE, _NEW_LINE)
            to_send += to_write.encode()

            # read and write chunks
            loop = get_event_loop()
            while True:
                data = await loop.run_in_executor(None, val.read, chunk_size)
                if not data:
                    break
                to_send += data
            val.close()

        else:
            to_send += (
                f'Content-Disposition: form-data; name="{key}"{_NEW_LINE}{_NEW_LINE}').encode()
            to_send += val.encode() + _NEW_LINE.encode()

    # write --boundary-- for finish
    to_send += (f'--{boundary}--').encode()
    _add_header(headers, 'Content-Length', str(len(to_send)))
    return to_send


async def _do_request(urlparsed: ParseResult,
                      headers_data: Callable,
                      connector: TCPConnector,
                      body: Optional[ParsedBodyType],
                      verify: bool,
                      ssl: Optional[SSLContext],
                      timeouts: Optional[Timeouts],
                      http2: bool = False) -> HttpResponse:
    """Something."""
    async with (await connector.acquire(urlparsed)) as connection:
        await connection.connect(urlparsed, verify, ssl, timeouts, http2)
        to_send = headers_data(connection=connection)

        if connection.h2conn:
            return await connection.http2_request(to_send, body)

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
        try:
            response._set_response_initial(await wait_for(
                connection.reader.readline(),
                (timeouts or connector.timeouts).sock_read))
        except TimeoutException:
            raise ReadTimeout()

        res_data = None
        # reading headers

        await response._set_response_headers(_parse_headers_iterator(connection))

        size = response.headers.get('content-length')
        chunked = response.headers.get('transfer-encoding', '') == 'chunked'
        keepalive = 'close' not in response.headers.get('connection', '')
        response.compressed = response.headers.get('content-encoding', '')

        if size:
            response._set_body(await connection.reader.readexactly(int(size)))

        if chunked:
            connection.block_until_read_chunks()
            response.chunked = True

        if keepalive:
            connection.keep_alive()
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

    def __init__(self, connector: TCPConnector = None, handle_cookies=False,
                 verify_ssl=True):
        """Initialize client options."""
        self.connector = connector or TCPConnector()
        self.handle_cookies = handle_cookies
        self.cookies_map: Dict[str, cookies.SimpleCookie] = {}
        self.verify_ssl = verify_ssl

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args, **_kwargs):
        await self.shutdown()

    async def shutdown(self):
        """Cleanup connections, this method makes client unusable."""
        await self.connector.cleanup()

    async def _request_with_body(self,
                                 url: str,
                                 method: str,
                                 data: DataType = None,
                                 headers: HeadersType = None,
                                 json: dict = None,
                                 params: ParamsType = None,
                                 json_serializer=dumps,
                                 multipart: bool = False,
                                 verify: bool = True,
                                 ssl: SSLContext = None,
                                 timeouts: Timeouts = None,
                                 follow: bool = False,
                                 http2: bool = False) -> HttpResponse:
        """Do post http request. """
        if not data and not json:
            TypeError('missing argument, either "json" or "data"')
        if json:
            data = json_serializer(json)
            headers = headers or HttpHeaders()
            _add_header(headers, 'Content-Type', 'application/json')
        return await self.request(url,
                                  method,
                                  headers,
                                  params,
                                  data,
                                  multipart,
                                  verify=verify,
                                  ssl=ssl,
                                  follow=follow,
                                  timeouts=timeouts,
                                  http2=http2)

    async def get(self,
                  url: str,
                  headers: HeadersType = None,
                  params: ParamsType = None,
                  verify: bool = True,
                  ssl: SSLContext = None,
                  timeouts: Timeouts = None,
                  follow: bool = False,
                  http2: bool = False) -> HttpResponse:
        """Do get http request. """
        return await self.request(url,
                                  'GET',
                                  headers,
                                  params,
                                  verify=verify,
                                  ssl=ssl,
                                  follow=follow,
                                  timeouts=timeouts,
                                  http2=http2)

    async def post(self,
                   url: str,
                   data: DataType = None,
                   headers: HeadersType = None,
                   json: dict = None,
                   params: ParamsType = None,
                   json_serializer=dumps,
                   multipart: bool = False,
                   verify: bool = True,
                   ssl: SSLContext = None,
                   timeouts: Timeouts = None,
                   follow: bool = False,
                   http2: bool = False) -> HttpResponse:
        """Do post http request. """
        return await self._request_with_body(url,
                                             'POST',
                                             data,
                                             headers,
                                             json,
                                             params,
                                             json_serializer,
                                             multipart,
                                             verify=verify,
                                             ssl=ssl,
                                             follow=follow,
                                             timeouts=timeouts,
                                             http2=http2)

    async def put(self,
                  url: str,
                  data: DataType = None,
                  headers: HeadersType = None,
                  json: dict = None,
                  params: ParamsType = None,
                  json_serializer=dumps,
                  multipart: bool = False,
                  verify: bool = True,
                  ssl: SSLContext = None,
                  timeouts: Timeouts = None,
                  follow: bool = False,
                  http2: bool = False) -> HttpResponse:
        """Do put http request. """
        return await self._request_with_body(url,
                                             'PUT',
                                             data,
                                             headers,
                                             json,
                                             params,
                                             json_serializer,
                                             multipart,
                                             verify=verify,
                                             ssl=ssl,
                                             follow=follow,
                                             timeouts=timeouts,
                                             http2=http2)

    async def patch(self,
                    url: str,
                    data: DataType = None,
                    headers: HeadersType = None,
                    json: dict = None,
                    params: ParamsType = None,
                    json_serializer=dumps,
                    multipart: bool = False,
                    verify: bool = True,
                    ssl: SSLContext = None,
                    timeouts: Timeouts = None,
                    follow: bool = False,
                    http2: bool = False) -> HttpResponse:
        """Do patch http request. """
        return await self._request_with_body(url,
                                             'PATCH',
                                             data,
                                             headers,
                                             json,
                                             params,
                                             json_serializer,
                                             multipart,
                                             verify=verify,
                                             ssl=ssl,
                                             follow=follow,
                                             timeouts=timeouts,
                                             http2=http2)

    async def delete(self,
                     url: str,
                     data: DataType = b'',
                     headers: HeadersType = None,
                     json: dict = None,
                     params: ParamsType = None,
                     json_serializer=dumps,
                     multipart: bool = False,
                     verify: bool = True,
                     ssl: SSLContext = None,
                     timeouts: Timeouts = None,
                     follow: bool = False,
                     http2: bool = False) -> HttpResponse:
        """Do delete http request. """
        return await self._request_with_body(url,
                                             'DELETE',
                                             data,
                                             headers,
                                             json,
                                             params,
                                             json_serializer,
                                             multipart,
                                             verify=verify,
                                             ssl=ssl,
                                             follow=follow,
                                             timeouts=timeouts,
                                             http2=http2)

    async def request(self,
                      url: str,
                      method: str = 'GET',
                      headers: HeadersType = None,
                      params: ParamsType = None,
                      data: DataType = None,
                      multipart: bool = False,
                      verify: bool = True,
                      ssl: SSLContext = None,
                      timeouts: Timeouts = None,
                      follow: bool = False,
                      http2: bool = False) -> HttpResponse:
        """Do http request.

        Params:
            * **url**: url of request
            * **method**: Http method of request
            * **headers**: headers to add in request
            * **params**: query params to add in
              request if not manually added
            * **data**: Data to be sent, this param is ignored for get
              requests.
            * **multipart**: Tell aiosonic if request is multipart
            * **verify**: parameter to indicate whether to verify ssl
            * **ssl**: this parameter allows to specify a custom ssl context
            * **timeouts**: parameter to indicate timeouts for request
            * **follow**: parameter to indicate whether to follow redirects
            * **http2**: flag to indicate whether to use http2 (experimental)
        """
        urlparsed = _get_url_parsed(url)

        boundary = None
        headers = headers or []
        body: ParsedBodyType = b''

        if self.handle_cookies:
            self._add_cookies_to_request(urlparsed.hostname, headers)

        if method != 'GET' and data and not multipart:
            body = _setup_body_request(data, headers)
        elif multipart:
            if not isinstance(data, dict):
                raise ValueError('data should be dict')
            boundary = 'boundary-%d' % randint(10**8, 10**9)
            body = await _send_multipart(data, boundary, headers)

        max_redirects = 30
        # if class or request method has false, it will be false
        verify_ssl = verify and self.verify_ssl
        while True:
            headers_data = partial(_get_header_data,
                                   url=urlparsed,
                                   method=method,
                                   headers=headers,
                                   params=params,
                                   multipart=multipart,
                                   boundary=boundary)
            try:
                response = await wait_for(
                    _do_request(urlparsed, headers_data, self.connector, body,
                                verify_ssl, ssl, timeouts, http2),
                    timeout=(timeouts
                             or self.connector.timeouts).request_timeout)

                if self.handle_cookies:
                    self._save_new_cookies(urlparsed.hostname, response)

                if follow and response.status_code in {301, 302}:
                    max_redirects -= 1

                    if max_redirects == 0:
                        raise MaxRedirects()

                    if self.handle_cookies:
                        self._add_cookies_to_request(
                            urlparsed.hostname, headers)

                    parsed_full_url = _get_url_parsed(
                        response.headers['location'])

                    # if full url, will have scheme
                    if parsed_full_url.scheme:
                        urlparsed = parsed_full_url
                    else:
                        urlparsed = _get_url_parsed(
                            url.replace(
                                urlparsed.path,
                                response.headers['location']))
                else:
                    return response
            except ConnectTimeout:
                raise
            except TimeoutException:
                raise RequestTimeout()

    async def wait_requests(self, timeout: int = 30):
        """Wait until all pending requests are done.

        If timeout, returns false.

        This is useful when doing safe shutdown of a process.
        """
        try:
            return await wait_for(
                self.connector.wait_free_pool(), timeout)
        except TimeoutException:
            return False

    def _add_cookies_to_request(self, host: str, headers: HeadersType):
        """Add cookies to request."""
        host_cookies = self.cookies_map.get(host)
        if (host_cookies and
                not any([header.lower() == 'cookie'
                         for header, _ in headers])):
            cookies_str = host_cookies.output(header='Cookie:')
            for cookie_data in cookies_str.split('\r\n'):
                _add_header(headers, *cookie_data.split(': ', 1))

    def _save_new_cookies(self, host: str, response: HttpResponse):
        """Save new cookies in map."""
        if response.cookies:
            self.cookies_map[host] = response.cookies
