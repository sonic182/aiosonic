import gzip
import zlib
from urllib.parse import urlparse

import pytest

import aiosonic
from aiosonic import HttpHeaders, HttpResponse
from aiosonic.exceptions import DecompressionError, MissingWriterException
from aiosonic.http_parser import add_header, add_headers


def test_headers_retrival():
    """Test reading header with more than one ":" char ocurrence."""
    sample_header = b'Report-To: { "group": "wm_nel", "max_age": 86400, "endpoints": [{ "url": "https://intake-logging.wikimedia.org/v1/events?stream=w3c.reportingapi.network_error&schema_uri=/w3c/reportingapi/network_error/1.0.0" }] }\r\n'  # noqa: E501
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


def test_add_header_rejects_crlf_in_value():
    """Test that CRLF in a header value is rejected."""
    with pytest.raises(ValueError):
        add_header({}, "X-Trace-Id", "abc\r\nX-Injected: pwned")


def test_add_header_rejects_bare_lf_and_cr():
    """Test that bare LF and bare CR in a header value are each rejected."""
    with pytest.raises(ValueError):
        add_header({}, "X-Trace-Id", "abc\ninjected")
    with pytest.raises(ValueError):
        add_header({}, "X-Trace-Id", "abc\rinjected")


def test_add_header_rejects_invalid_name():
    """Test that a header name with illegal token characters is rejected."""
    with pytest.raises(ValueError):
        add_header({}, "X Bad:Name", "value")


def test_add_header_allows_pseudo_header_names():
    """Test that HTTP/2 pseudo-header names (leading ':') are allowed."""
    headers = []
    add_header(headers, ":method", "GET")
    assert headers == [(":method", "GET")]


def test_add_header_allows_normal_values():
    """Test that ordinary header values, including HTAB, still pass."""
    headers = {}
    add_header(headers, "Authorization", "Bearer token")
    add_header(headers, "Content-Type", "text/html; charset=utf-8")
    add_header(headers, "X-Tabbed", "value\twith\ttab")
    assert headers == {
        "Authorization": "Bearer token",
        "Content-Type": "text/html; charset=utf-8",
        "X-Tabbed": "value\twith\ttab",
    }


def test_prepare_request_headers_rejects_crlf_injection(mocker):
    """Test that the real request-building path rejects CRLF-laden header values."""
    connection = mocker.MagicMock()
    connection.h2conn = None
    with pytest.raises(ValueError):
        aiosonic.client._prepare_request_headers(
            url=urlparse("http://127.0.0.1/"),
            connection=connection,
            method="GET",
            headers={"X-Trace-Id": "abc\r\nX-Injected: pwned"},
        )


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
        aiosonic.client._handle_chunk(b"foo", conn)


def test_hostname_parse():
    """Test hostname encoding"""
    hostname = "gnosisespaña.es"
    port = 443
    assert aiosonic.client._get_hostname(hostname, port) == "xn--gnosisespaa-beb.es"


def test_handle_redirect_strips_credentials_on_cross_host():
    """Test that Cookie/Authorization/Proxy-Authorization are dropped on cross-host redirect."""
    client = aiosonic.HTTPClient()
    response = HttpResponse()
    response._set_response_initial(b"HTTP/1.1 302 Found\r\n")
    response._set_header("location", "http://evil.example/steal")

    headers = {
        "Cookie": "session=SECRET",
        "Authorization": "Bearer SECRET",
        "Proxy-Authorization": "Basic SECRET",
        "X-Custom": "keep-me",
    }
    current = urlparse("http://origin.example/")

    client._handle_redirect(
        current_urlparsed=current,
        headers=headers,
        response=response,
        max_redirects=5,
        method="GET",
        body=b"",
        transfer_chunked=False,
    )

    assert "Cookie" not in headers
    assert "Authorization" not in headers
    assert "Proxy-Authorization" not in headers
    assert headers["X-Custom"] == "keep-me"


def test_handle_redirect_strips_credentials_on_https_downgrade():
    """Test that credentials are dropped when HTTPS redirects to HTTP on the same host."""
    client = aiosonic.HTTPClient()
    response = HttpResponse()
    response._set_response_initial(b"HTTP/1.1 302 Found\r\n")
    response._set_header("location", "http://origin.example/insecure")

    headers = {
        "Cookie": "session=SECRET",
        "Authorization": "Bearer SECRET",
        "Proxy-Authorization": "Basic SECRET",
        "X-Custom": "keep-me",
    }
    current = urlparse("https://origin.example/secure")

    new_urlparsed, *_ = client._handle_redirect(
        current_urlparsed=current,
        headers=headers,
        response=response,
        max_redirects=5,
        method="GET",
        body=b"",
        transfer_chunked=False,
    )

    assert new_urlparsed.scheme == "http"
    assert "Cookie" not in headers
    assert "Authorization" not in headers
    assert "Proxy-Authorization" not in headers
    assert headers["X-Custom"] == "keep-me"


def test_handle_redirect_keeps_credentials_on_same_host():
    """Test that Cookie is preserved when the redirect stays on the same host."""
    client = aiosonic.HTTPClient()
    response = HttpResponse()
    response._set_response_initial(b"HTTP/1.1 302 Found\r\n")
    response._set_header("location", "http://origin.example/other")

    headers = {"Cookie": "session=SECRET"}
    current = urlparse("http://origin.example/")

    client._handle_redirect(
        current_urlparsed=current,
        headers=headers,
        response=response,
        max_redirects=5,
        method="GET",
        body=b"",
        transfer_chunked=False,
    )

    assert headers["Cookie"] == "session=SECRET"


def test_decompress_bounded_gzip_ok():
    """Test that normal gzip data decompresses correctly under a generous limit."""
    payload = b"hello world" * 10
    compressed = gzip.compress(payload)
    result = aiosonic.client._decompress_bounded(compressed, aiosonic.client._GZIP_WBITS, 10_000)
    assert result == payload


def test_decompress_bounded_deflate_ok():
    """Test that normal deflate (zlib-wrapped) data decompresses correctly under a generous limit."""
    payload = b"hello world" * 10
    compressed = zlib.compress(payload)
    result = aiosonic.client._decompress_bounded(compressed, aiosonic.client._DEFLATE_WBITS, 10_000)
    assert result == payload


def test_decompress_bounded_gzip_rejects_bomb():
    """Test that a high-ratio gzip payload is rejected once it would exceed the size limit."""
    compressed = gzip.compress(b"\x00" * 1_000_000, compresslevel=9)
    with pytest.raises(DecompressionError):
        aiosonic.client._decompress_bounded(compressed, aiosonic.client._GZIP_WBITS, 1_000)


def test_decompress_bounded_deflate_rejects_bomb():
    """Test that a high-ratio deflate payload is rejected once it would exceed the size limit."""
    compressed = zlib.compress(b"\x00" * 1_000_000, level=9)
    with pytest.raises(DecompressionError):
        aiosonic.client._decompress_bounded(compressed, aiosonic.client._DEFLATE_WBITS, 1_000)


def test_set_body_enforces_max_decompressed_size():
    """Test that HttpResponse._set_body raises DecompressionError once the configured limit is hit."""
    response = HttpResponse()
    response.compressed = "gzip"
    response.max_decompressed_size = 1_000
    compressed = gzip.compress(b"\x00" * 1_000_000, compresslevel=9)
    with pytest.raises(DecompressionError):
        response._set_body(compressed)


def test_http_client_max_decompressed_size_configurable():
    """Test that HTTPClient exposes a sane default and honors a custom max_decompressed_size."""
    default_client = aiosonic.HTTPClient()
    assert default_client.max_decompressed_size == aiosonic.client._DEFAULT_MAX_DECOMPRESSED_SIZE

    custom_client = aiosonic.HTTPClient(max_decompressed_size=42)
    assert custom_client.max_decompressed_size == 42
