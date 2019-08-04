
from concurrent import futures


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
