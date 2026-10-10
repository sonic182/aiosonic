"""Proxy class to be used in client."""

from __future__ import annotations
from base64 import b64encode
from typing import Optional
from urllib.parse import ParseResult, unquote, urlparse
from urllib.request import getproxies_environment, proxy_bypass_environment

from aiosonic.utils import url_without_userinfo


class Proxy:
    """Proxy class.

    Args:
        * host (str): proxy server where to connect
        * auth (str): auth data in the format of `user:password`
    """

    def __init__(self, host: str, auth: Optional[str] = None):
        self.host = host
        self.auth = None
        if auth:
            self.auth = b64encode(auth.encode())

    @classmethod
    def from_url(cls, url: str) -> Proxy:
        """Build a proxy from its url.

        Args:
            url (str): Proxy url, ``http`` is assumed when it has no scheme. The credentials go in its
                ``user:password@`` part if needed.

        Returns:
            Proxy: The proxy, authenticated with the credentials of the url.
        """
        parsed = urlparse(url if "://" in url else f"http://{url}")
        auth = f"{unquote(parsed.username)}:{unquote(parsed.password or '')}" if parsed.username else None
        return cls(url_without_userinfo(parsed), auth=auth)


def proxy_from_environment(urlparsed: ParseResult) -> Optional[Proxy]:
    """Get the proxy that the environment sets for a url.

    ``HTTP_PROXY``, ``HTTPS_PROXY`` and ``ALL_PROXY`` are read, by the scheme of the url, and ``NO_PROXY``
    excludes hosts.

    Args:
        urlparsed (ParseResult): The parsed url of the request.

    Returns:
        Optional[Proxy]: The proxy to use, or None when the environment sets none for the url.

    Raises:
        ValueError: When the proxy of the url is not an ``http`` or ``https`` one (like ``socks5://``).
    """
    proxies = getproxies_environment()
    proxy_url = proxies.get(urlparsed.scheme) or proxies.get("all")
    if not proxy_url or not urlparsed.hostname:
        return None
    if proxy_bypass_environment(urlparsed.netloc.rpartition("@")[2], proxies):
        return None
    scheme, sep, _ = proxy_url.partition("://")
    if sep and scheme.lower() not in ("http", "https"):
        raise ValueError(f"unsupported proxy scheme {scheme!r} in the environment, only http and https are supported")
    return Proxy.from_url(proxy_url)
