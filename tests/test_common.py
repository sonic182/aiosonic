
from aiosonic import HttpHeaders


def test_headers_retrival():
    """Test reading header with more than one ":" char ocurrence."""
    sample_header = b'Report-To: { "group": "wm_nel", "max_age": 86400, "endpoints": [{ "url": "https://intake-logging.wikimedia.org/v1/events?stream=w3c.reportingapi.network_error&schema_uri=/w3c/reportingapi/network_error/1.0.0" }] }\r\n'
    assert len(HttpHeaders._clear_line(sample_header)) == 2


def test_headers_retrival_common():
    """Test reading header with more than one ":" char ocurrence."""
    res = ['Authorization', 'Bearer foobar']
    sample_header = b': '.join([item.encode() for item in res]) + b'\r\n'
    assert HttpHeaders._clear_line(sample_header) == res
