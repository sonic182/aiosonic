
import aiosonic


def test_get(http2_server):
    """Get http2."""
    assert http2_server
    uri = http2_server()
    assert uri
    assert False
