

# General
class MissingWriterException(Exception):
    pass


# timeouts
class BaseTimeout(Exception):
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
class HttpParsingError(Exception):
    pass


# Redirects
class MaxRedirects(Exception):
    pass


# HTTP2
class MissingEvent(Exception):
    pass
