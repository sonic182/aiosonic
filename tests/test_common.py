
from aiosonic import HttpHeaders
from aiosonic import HttpResponse
from aiosonic import _add_header


def test_headers_retrival():
    """Test reading header with more than one ":" char ocurrence."""
    sample_header = b'Report-To: { "group": "wm_nel", "max_age": 86400, "endpoints": [{ "url": "https://intake-logging.wikimedia.org/v1/events?stream=w3c.reportingapi.network_error&schema_uri=/w3c/reportingapi/network_error/1.0.0" }] }\r\n'
    assert len(HttpHeaders._clear_line(sample_header)) == 2


def test_headers_retrival_common():
    """Test reading header with more than one ":" char ocurrence."""
    res = ['Authorization', 'Bearer foobar']
    sample_header = b': '.join([item.encode() for item in res]) + b'\r\n'
    assert HttpHeaders._clear_line(sample_header) == res


def test_headers_parsing():
    """Test parsing header with no value."""
    parsing = HttpResponse()
    parsing._set_header(*HttpHeaders._clear_line(b'Expires: \r\n'))
    assert parsing.raw_headers == [('Expires', '')]


def test_add_header():
    """Test add header method."""
    headers = HttpHeaders()
    _add_header(headers, 'content-type', 'application/json')
    assert headers == {'content-type': 'application/json'}


def test_add_header_list():
    """Test add header method into list."""
    headers = []
    _add_header(headers, 'content-type', 'application/json')
    assert headers == [('content-type', 'application/json')]


def test_add_header_list_replace():
    """Test add header method into list with replace True."""
    headers = []
    _add_header(headers, 'foo', 'bar')
    _add_header(headers, 'foo', 'baz', True)
    assert headers == [('foo', 'baz')]
