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


def default_port(urlparsed: ParseResult) -> int:
    """Return the URL's port, or its scheme's default when it has none.

    Args:
        urlparsed (ParseResult): The parsed target URL.

    Returns:
        int: The explicit port, 443 for ``https``/``wss``, or 80 otherwise.
    """
    return urlparsed.port or (443 if urlparsed.scheme in ("https", "wss") else 80)


def connection_key(urlparsed: ParseResult) -> str:
    """Build the key that identifies a reusable connection.

    Args:
        urlparsed (ParseResult): The parsed target URL.

    Returns:
        str: ``scheme://hostname:port`` with the scheme's default port when the URL has none.
    """
    return f"{urlparsed.scheme}://{urlparsed.hostname}:{default_port(urlparsed)}"
