
from concurrent import futures


# General
class MissingWriterException(Exception):
    pass

# timeouts
class BaseTimeout(futures._base.TimeoutError):
    pass


class ConnectTimeout(BaseTimeout):
    pass


class RequestTimeout(BaseTimeout):
    pass


# parsing
class HttpParsingError(Exception):
    pass


# Redirects
class MaxRedirects(Exception):
    pass
