

class Timeouts():
    """Timeouts class wrapper."""

    def __init__(self, sock_connect: int = 5, sock_read: int = 60,
                 pool_acquire: int = 3, request_timeout: int = None):
        """Initialize."""
        self.sock_connect = sock_connect
        self.sock_read = sock_read
        self.pool_acquire = pool_acquire
        self.request_timeout = request_timeout
