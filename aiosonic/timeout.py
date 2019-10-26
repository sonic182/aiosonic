

class Timeouts():
    """Timeouts class wrapper."""

    def __init__(self, sock_connect: float = 5, sock_read: float = 30,
                 pool_acquire: float = None, request_timeout: float = 60):
        """Timeouts.

        Arguments:
            * sock_connect(float): time for establish connection to server
            * sock_read(float): time until get first read
            * pool_acquire(float): time until get connection from
              connection's pool
            * request_timeout(float): time until complete request.
        """
        self.sock_connect = sock_connect
        self.sock_read = sock_read
        self.pool_acquire = pool_acquire
        self.request_timeout = request_timeout
