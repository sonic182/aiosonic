from __future__ import annotations
from asyncio.exceptions import TimeoutError as TimeoutException  # noqa: F401
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiosonic.client import HttpResponse


class AiosonicError(Exception):
    """Base class of all aiosonic exceptions."""


# General
class MissingWriterException(AiosonicError):
    pass


class MissingReaderException(AiosonicError):
    pass


# timeouts
class BaseTimeout(AiosonicError):
    pass


class ConnectTimeout(BaseTimeout):
    pass


class ReadTimeout(BaseTimeout):
    pass


class RequestTimeout(BaseTimeout):
    pass


class ConnectionPoolAcquireTimeout(BaseTimeout):
    pass


# parsing
class HttpParsingError(AiosonicError):
    pass


# Redirects
class MaxRedirects(AiosonicError):
    pass


# Reconnect
class ConnectionDisconnected(AiosonicError):
    pass


# HTTP2
class MissingEvent(AiosonicError):
    pass


# SSE
class SSEConnectionError(AiosonicError):
    pass


class SSEParsingError(AiosonicError):
    pass


# Decompression
class DecompressionError(AiosonicError):
    pass


# Status
class HTTPStatusError(AiosonicError):
    """Raised by ``HttpResponse.raise_for_status`` for 4xx and 5xx responses.

    Attributes:
        response: The response that triggered the error.
    """

    def __init__(self, message: str, response: HttpResponse):
        super().__init__(message)
        self.response = response
