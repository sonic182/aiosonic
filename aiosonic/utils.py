"""Utils."""

import logging
from typing import Optional
from urllib.parse import ParseResult

from onecache import CacheDecorator

from aiosonic.types import ParamsType


@CacheDecorator()
def get_debug_logger():
    """Get debug logger."""
    logger = logging.getLogger("aiosonic")
    # logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())
    return logger


def join_url(base_url: str, url: str) -> str:
    """Prepend ``base_url`` to ``url`` unless ``url`` is already absolute.

    Args:
        base_url (str): The base URL to prepend.
        url (str): An absolute URL or a path relative to ``base_url``.

    Returns:
        str: ``url`` when it starts with ``http://`` or ``https://``, otherwise ``base_url`` and ``url`` joined
        by one slash.
    """
    if url.startswith(("http://", "https://")):
        return url
    return base_url.rstrip("/") + "/" + url.lstrip("/")


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


def url_without_userinfo(urlparsed: ParseResult) -> str:
    """Build the URL without its ``user:password@`` part.

    Args:
        urlparsed (ParseResult): The parsed URL.

    Returns:
        str: The URL as a string with the credentials removed.
    """
    return urlparsed._replace(netloc=urlparsed.netloc.rpartition("@")[2]).geturl()


def merge_params(base: Optional[ParamsType], extra: Optional[ParamsType]) -> Optional[ParamsType]:
    """Merge two sets of query params, giving precedence to ``extra``.

    Args:
        base (Optional[ParamsType]): The default params.
        extra (Optional[ParamsType]): The params that override the default ones with the same name.

    Returns:
        Optional[ParamsType]: The merged params, or the only one given when the other is empty.
    """
    if not base:
        return extra
    if not extra:
        return base
    base_pairs = list(base.items()) if isinstance(base, dict) else list(base)
    extra_pairs = list(extra.items()) if isinstance(extra, dict) else list(extra)
    overridden = {key for key, _ in extra_pairs}
    return [pair for pair in base_pairs if pair[0] not in overridden] + extra_pairs
