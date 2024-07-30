"""Connection stuffs."""

import ssl
from asyncio import StreamReader, StreamWriter, open_connection
from ssl import SSLContext
from typing import Dict, Optional
from urllib.parse import ParseResult

import h2.config
import h2.connection
import h2.events

from aiosonic.connectors import TCPConnector
from aiosonic.exceptions import (
    HttpParsingError,
    MissingReaderException,
    MissingWriterException,
)
from aiosonic.http2 import Http2Handler
from aiosonic.tcp_helpers import keepalive_flags
from aiosonic.types import ParsedBodyType


class Connection:
    """Connection class.

    This class represents a connection to a remote server, managing the communication
    through a socket. It is designed to handle both HTTP/1.1 and HTTP/2 protocols.

    Attributes:
        connector (TCPConnector): An instance of the TCPConnector class responsible
            for managing the connection pool.
        reader (Optional[StreamReader]): A StreamReader for reading data from the socket.
        writer (Optional[StreamWriter]): A StreamWriter for efficiently writing data
            to the socket.
        keep (bool): A flag indicating whether the connection should be kept alive.
        key (Optional[str]): A key identifying the connection based on the hostname and port.
        blocked (bool): A flag indicating whether the connection is currently blocked,
            meaning it is in use and should not be reinserted into the pool until all
            data has been read.
        temp_key (Optional[str]): A temporary key used during the connection setup process.
        requests_count (int): The count of requests made over the connection.
        h2conn (Optional[h2.connection.H2Connection]): An instance of the H2Connection
            class representing the HTTP/2 connection.
        h2handler (Optional[Http2Handler]): An instance of the Http2Handler class
            responsible for handling HTTP/2 requests.
    """

    def __init__(self, connector: TCPConnector) -> None:
        self.connector = connector
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None

        self.keep = False  # keep alive flag
        self.key = None
        self.blocked = False
        self.temp_key: Optional[str] = None
        self.requests_count = 0

        self.h2conn: Optional[h2.connection.H2Connection] = None
        self.h2handler: Optional[Http2Handler] = None

        self._verify = True
        self.proxy_connected = False

    @property
    def is_connected(self):
        return not self.writer is None

    async def connect(
        self,
        urlparsed: ParseResult,
        dns_info: dict,
        verify: bool,
        ssl_context: SSLContext,
        http2: bool = False,
    ) -> None:
        """Connet with timeout."""
        self._verify = verify
        await self._connect(urlparsed, verify, ssl_context, dns_info, http2)

    def write(self, data: bytes):
        """Write data in the socket."""
        if not self.writer:
            raise MissingWriterException("writer not set.")
        self.writer.write(data)

    async def readline(self):
        """Read data until line break"""
        if not self.reader:
            raise MissingReaderException("reader not set.")
        return await self.reader.readline()

    async def readexactly(self, size: int):
        """Read exactly size of bytes"""
        if not self.reader:
            raise MissingReaderException("reader not set.")
        return await self.reader.readexactly(size)

    async def read(self, size: int = -1):
        """Read up to size of bytes"""
        if not self.reader:
            raise MissingReaderException("reader not set.")
        return await self.reader.read(size)

    async def readuntil(self, separator: bytes = b"\n"):
        """Read until separator"""
        if not self.reader:
            raise MissingReaderException("reader not set.")
        return await self.reader.readuntil(separator)

    async def _connect(
        self,
        urlparsed: ParseResult,
        verify: bool,
        ssl_context: SSLContext,
        dns_info,
        http2: bool,
    ) -> None:
        """Get reader and writer."""
        if not urlparsed.hostname:
            raise HttpParsingError("missing hostname")

        key = f"{urlparsed.hostname}-{urlparsed.port}"

        def is_closing():
            return True  # noqa

        if self.writer:
            is_closing = self.writer.is_closing  # type: ignore

        dns_info_copy = dns_info.copy()
        dns_info_copy["server_hostname"] = dns_info_copy.pop("hostname")
        dns_info_copy["flags"] = dns_info_copy["flags"] | keepalive_flags()

        if not (self.key and key == self.key and not is_closing()):
            self.close()

            if urlparsed.scheme == "https":
                ssl_context = ssl_context or get_default_ssl_context(verify, http2)
            else:
                del dns_info_copy["server_hostname"]
            port = urlparsed.port or (443 if urlparsed.scheme == "https" else 80)
            dns_info_copy["port"] = port

            self.reader, self.writer = await open_connection(
                **dns_info_copy, ssl=ssl_context
            )

            self.temp_key = key
            await self._connection_made()

    async def _connection_made(self) -> None:
        tls_conn = self.writer.get_extra_info("ssl_object")
        if not tls_conn:
            return

        # Always prefer the result from ALPN to that from NPN.
        negotiated_protocol = tls_conn.selected_alpn_protocol()
        if negotiated_protocol is None:
            negotiated_protocol = tls_conn.selected_npn_protocol()

        if negotiated_protocol == "h2":  # pragma: no cover
            config = h2.config.H2Configuration()
            self.h2conn = h2.connection.H2Connection(config=config)
            self.h2handler = Http2Handler(self)

    def keep_alive(self) -> None:
        """Check if keep alive."""
        self.keep = True

    def block_until_read_chunks(self):
        """Check if keep alive."""
        self.blocked = True

    def release(self) -> None:
        """Release connection."""
        self.connector.release(self)
        self.requests_count += 1
        # if keep False and blocked (by latest chunked response), close it.
        # server said to close it.
        if self.requests_count >= self.connector.conn_max_requests or (
            not self.keep and self.blocked
        ):
            self.close()
        # ensure unblock conn object after read
        self.blocked = False

    def ensure_released(self):
        """Ensure the connection is released."""
        if self.blocked:
            if self.writer:
                self.writer._transport.abort()
            self.blocked = False
            self.release()

    def close(self, check_closing: bool = False) -> None:
        """Close connection if opened."""
        if self.writer:
            is_closing = getattr(
                self.writer, "is_closing", self.writer._transport.is_closing
            )
            if not check_closing or is_closing():
                self.writer.close()

            self.reader, self.writer = None, None
        self.proxy_connected = False

    async def upgrade(self, ssl_context: SSLContext = None):
        ssl_context = ssl_context or get_default_ssl_context(self._verify)
        if not self.writer:
            raise MissingWriterException()
        await self.writer.start_tls(ssl_context)

    async def http2_request(
        self, headers: Dict[str, str], body: Optional[ParsedBodyType]
    ):
        if self.h2handler:  # pragma: no cover
            return await self.h2handler.request(headers, body)

    def __del__(self) -> None:
        """Cleanup."""
        self.close(True)

    async def __aenter__(self):
        """Get connection from pool."""
        return self

    async def __aexit__(self, exc_type: None, exc: None, tb: None) -> None:
        """Release connection."""
        if self.keep and not exc:
            self.key = self.temp_key
        else:
            self.key = None
            self.h2conn = None
            if self.writer and not self.blocked:
                self.close()

        if not self.blocked:
            self.release()
            if self.h2handler:  # pragma: no cover
                self.h2handler.cleanup()


def get_default_ssl_context(verify=True, http2=False):
    if http2:  # pragma: no cover
        ssl_context = _get_http2_ssl_context()
    else:
        ssl_context = ssl.create_default_context(
            ssl.Purpose.SERVER_AUTH,
        )

    if not verify:
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
    return ssl_context


def _get_http2_ssl_context():
    """
    This function creates an SSLContext object that is suitably configured for
    HTTP/2. If you're working with Python TLS directly, you'll want to do the
    exact same setup as this function does.
    """
    # Get the basic context from the standard library.
    ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)

    # RFC 7540 Section 9.2: Implementations of HTTP/2 MUST use TLS version 1.2
    # or higher. Disable TLS 1.1 and lower.
    ctx.options |= (
        ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
    )

    # RFC 7540 Section 9.2.1: A deployment of HTTP/2 over TLS 1.2 MUST disable
    # compression.
    ctx.options |= ssl.OP_NO_COMPRESSION

    # RFC 7540 Section 9.2.2: "deployments of HTTP/2 that use TLS 1.2 MUST
    # support TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256". In practice, the
    # blocklist defined in this section allows only the AES GCM and ChaCha20
    # cipher suites with ephemeral key negotiation.
    ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20")

    # We want to negotiate using NPN and ALPN. ALPN is mandatory, but NPN may
    # be absent, so allow that. This setup allows for negotiation of HTTP/1.1.
    ctx.set_alpn_protocols(["h2", "http/1.1"])

    try:
        if hasattr(ctx, "_set_npn_protocols"):
            ctx.set_npn_protocols(["h2", "http/1.1"])
    except NotImplementedError:
        pass

    return ctx
