"""Authentication helpers for requests."""

from __future__ import annotations
from base64 import b64encode
from typing import TYPE_CHECKING, Dict, Optional, Tuple, Union
from urllib.parse import ParseResult, unquote

from aiosonic import http_parser

if TYPE_CHECKING:
    from aiosonic.client import HeadersType


class Auth:
    """Base class of authentication schemes.

    Subclass it and implement :meth:`apply` to add the credentials a request needs.
    """

    def apply(self, headers: HeadersType, method: str, url: str) -> None:
        """Add the authentication data to the request headers.

        Args:
            headers (HeadersType): The headers of the request, modified in place.
            method (str): The http method of the request.
            url (str): The url of the request.
        """
        raise NotImplementedError


class BasicAuth(Auth):
    """HTTP Basic authentication.

    Args:
        username (str): The user name.
        password (str): The password.
    """

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    def apply(self, headers: HeadersType, method: str, url: str) -> None:
        token = b64encode(f"{self.username}:{self.password}".encode()).decode()
        http_parser.add_header(headers, "Authorization", f"Basic {token}", replace=True)


class BearerAuth(Auth):
    """Bearer token authentication.

    Args:
        token (str): The token to send.
    """

    def __init__(self, token: str):
        self.token = token

    def apply(self, headers: HeadersType, method: str, url: str) -> None:
        http_parser.add_header(headers, "Authorization", f"Bearer {self.token}", replace=True)


#: Auth instance, or ``(username, password)`` tuple for basic authentication
AuthType = Union[Auth, Tuple[str, str]]


def _to_auth(value: AuthType) -> Auth:
    return BasicAuth(*value) if isinstance(value, tuple) else value


def resolve_auth(
    auth: Optional[AuthType], urlparsed: ParseResult, auths: Optional[Dict[str, AuthType]] = None
) -> Optional[Auth]:
    """Get the :class:`Auth` to use for a request.

    The first one found is used: the ``auth`` of the request, the ``user:password@`` part of the url, and the
    entry of ``auths`` for the host of the url (``host:port`` is looked up first when the url has a port).

    Args:
        auth (Optional[AuthType]): The auth given to the request.
        urlparsed (ParseResult): The parsed url of the request.
        auths (Optional[Dict[str, AuthType]]): Auths by lowercase host, or ``host:port``.

    Returns:
        Optional[Auth]: The auth to apply, or None when the request needs no authentication.
    """
    if auth is not None:
        return _to_auth(auth)
    if urlparsed.username is not None:
        return BasicAuth(unquote(urlparsed.username), unquote(urlparsed.password or ""))
    if auths and urlparsed.hostname:
        hostname = urlparsed.hostname.lower()
        keys = [f"{hostname}:{urlparsed.port}", hostname] if urlparsed.port else [hostname]
        for key in keys:
            if key in auths:
                return _to_auth(auths[key])
    return None
