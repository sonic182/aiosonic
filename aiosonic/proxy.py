"""Proxy class to be used in client."""

from base64 import b64encode
from typing import Optional


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
