"""Authentication helpers for requests."""

from __future__ import annotations
from base64 import b64encode
from typing import TYPE_CHECKING, Optional, Tuple, Union
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


def resolve_auth(auth: Optional[AuthType], urlparsed: ParseResult) -> Optional[Auth]:
    """Get the :class:`Auth` to use for a request.

    Args:
        auth (Optional[AuthType]): The auth given to the request or the client.
        urlparsed (ParseResult): The parsed url, whose ``user:password@`` part is used when ``auth`` is missing.

    Returns:
        Optional[Auth]: The auth to apply, or None when the request needs no authentication.
    """
    if isinstance(auth, tuple):
        return BasicAuth(*auth)
    if auth is not None:
        return auth
    if urlparsed.username is not None:
        return BasicAuth(unquote(urlparsed.username), unquote(urlparsed.password or ""))
    return None
