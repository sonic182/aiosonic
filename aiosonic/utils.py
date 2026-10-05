"""Utils."""

import logging
from urllib.parse import ParseResult

from onecache import CacheDecorator


@CacheDecorator()
def get_debug_logger():
    """Get debug logger."""
    logger = logging.getLogger("aiosonic")
    # logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())
    return logger


def connection_key(urlparsed: ParseResult) -> str:
    """Build the key that identifies a reusable connection.

    Args:
        urlparsed (ParseResult): The parsed target URL.

    Returns:
        str: ``scheme://hostname:port`` with the scheme's default port when the URL has none.
    """
    port = urlparsed.port or (443 if urlparsed.scheme in ("https", "wss") else 80)
    return f"{urlparsed.scheme}://{urlparsed.hostname}:{port}"
