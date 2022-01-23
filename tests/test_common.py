import pytest

import aiosonic
from aiosonic import HTTPClient, HttpHeaders, HttpResponse
from aiosonic.http_parser import add_header, add_headers
from aiosonic.exceptions import MissingWriterException


def test_headers_retrival():
    """Test reading header with more than one ":" char ocurrence."""
    sample_header = b'Report-To: { "group": "wm_nel", "max_age": 86400, "endpoints": [{ "url": "https://intake-logging.wikimedia.org/v1/events?stream=w3c.reportingapi.network_error&schema_uri=/w3c/reportingapi/network_error/1.0.0" }] }\r\n'
    assert len(HttpHeaders._clear_line(sample_header)) == 2


def test_headers_retrival_common():
    """Test reading header with more than one ":" char ocurrence."""
    res = ["Authorization", "Bearer foobar"]
    sample_header = b": ".join([item.encode() for item in res]) + b"\r\n"
    assert HttpHeaders._clear_line(sample_header) == res


def test_headers_parsing():
    """Test parsing header with no value."""
    parsing = HttpResponse()
    parsing._set_header(*HttpHeaders._clear_line(b"Expires: \r\n"))
    assert parsing.raw_headers == [("Expires", "")]


def test_add_header():
    """Test add header method."""
    headers = HttpHeaders()
    add_header(headers, "content-type", "application/json")
    assert headers == {"content-type": "application/json"}


def test_add_header_list():
    """Test add header method into list."""
    headers = []
    add_header(headers, "content-type", "application/json")
    assert headers == [("content-type", "application/json")]


def test_add_header_list_replace():
    """Test add header method into list with replace True."""
    headers = []
    add_header(headers, "foo", "bar")
    add_header(headers, "foo", "baz", True)
    assert headers == [("foo", "baz")]


def test_add_header_replace():
    """Test add header method into list with replace True."""
    headers = [("User-Agent", "aiosonic")]
    add_headers(headers, [("user-agent", "wathever")])
    assert headers == [("user-agent", "wathever")]


def test_encoding_from_header():
    """Test use encoder from header."""
    response = HttpResponse()
    response._set_response_initial(b"HTTP/1.1 200 OK\r\n")
    response._set_header("content-type", "text/html; charset=utf-8")
    response.body = b"foo"
    assert response._get_encoding() == "utf-8"

    response._set_header("content-type", "application/json")
    assert response._get_encoding() == "utf-8"

    response._set_header("content-type", "text/html; charset=weirdencoding")
    assert response._get_encoding() == "ascii"


def test_parse_response_line():
    """Test parsing response line"""
    response = HttpResponse()
    response._set_response_initial(b"HTTP/1.1 200 OK\r\n")
    assert response.status_code == 200


def test_parse_response_line_with_empty_reason():
    """Test parsing response line with empty reason-phrase"""
    response = HttpResponse()
    response._set_response_initial(b"HTTP/1.1 200 \r\n")
    assert response.status_code == 200


def test_handle_bad_chunk(mocker):
    """Test handling chunks in chunked request"""
    with pytest.raises(MissingWriterException):
        conn = mocker.MagicMock()
        conn.writer = None
        aiosonic._handle_chunk(b"foo", conn)


@pytest.mark.asyncio
async def test_json_parser(mocker):
    headers = HttpHeaders()
    add_header(headers, "Content-Type", "application/json")

    # python<=3.7 compatible mock
    async def mocked(*args, **kwargs):
        mock = mocker.MagicMock()
        mock(*args, **kwargs)
        return mock

    mocker.patch("aiosonic.HTTPClient.request", new=mocked)
    instance = HTTPClient()

    res = await instance.post("foo", json=[])
    res.assert_called_once_with(  # type: ignore
        instance,
        "foo",
        "POST",
        headers,
        None,
        "[]",
        False,
        verify=True,
        ssl=None,
        follow=False,
        timeouts=None,
        http2=False,
    )


def test_hostname_parse():
    """Test hostname encoding"""
    hostname = "gnosisespaña.es"
    port = 443
    assert aiosonic._get_hostname(hostname, port) == "xn--gnosisespaa-beb.es"
