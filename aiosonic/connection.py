"""Connection stuffs."""

import ssl
from asyncio import StreamReader, StreamWriter, open_connection, CancelledError
from asyncio import sleep as asyncio_sleep
from ssl import SSLContext
from typing import Dict, Optional
from urllib.parse import ParseResult

import h2.config
import h2.connection
import h2.events

from aiosonic.connectors import TCPConnector
from aiosonic.pools import CyclicQueuePool

# from concurrent import futures (unused)
from aiosonic.exceptions import HttpParsingError
from aiosonic.http2 import Http2Handler
from aiosonic.tcp_helpers import keepalive_flags
from aiosonic.types import ParsedBodyType


class Connection:
    """Connection class."""

    def __init__(self, connector: TCPConnector) -> None:
        self.connector = connector
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None
        self.keep = False  # keep alive flag
        self.key = None
        self.blocked = False
        self.temp_key: Optional[str] = None
        self.requests_count = 0
        self.cycled = False

        self.h2conn: Optional[h2.connection.H2Connection] = None
        self.h2handler: Optional[Http2Handler] = None

    def is_closing(self):
        if self.writer:
            return getattr(self.writer, "is_closing", self.writer._transport.is_closing)
        else:
            return False

    async def connect(
        self,
        urlparsed: ParseResult,
        dns_info: dict,
        verify: bool,
        ssl_context: SSLContext,
        http2: bool = False,
    ) -> None:
        """Connet with timeout."""
        await self._connect(urlparsed, verify, ssl_context, dns_info, http2)

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
                ssl_context = ssl_context or ssl.create_default_context(
                    ssl.Purpose.SERVER_AUTH,
                )

                # flag will be removed when fully http2 support
                if http2:  # pragma: no cover
                    ssl_context = _get_http2_ssl_context()
                if not verify:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
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

    async def __aenter__(self):
        """Get connection from pool."""
        return self

    async def __aexit__(self, exc_type: None, exc: None, tb: None) -> None:
        """Release connection."""
        try:
            if self.keep and not exc:
                self.key = self.temp_key
            else:
                self.key = None
                self.h2conn = None

            if (not self.keep or type(self.connector.pool) == CyclicQueuePool) and self.writer and not self.blocked:
                self.close()

            if not self.blocked and not self.cycled:
                await self.release()
                if self.h2handler:  # pragma: no cover
                    self.h2handler.cleanup()

            else:
                while self.blocked:
                    await asyncio_sleep(0.05)
                if self.cycled:
                    return None
                elif self.writer and not self.is_closing() and type(self.connector.pool) == CyclicQueuePool:
                    self.close()
                if not self.cycled:
                    await self.release()

        except CancelledError:
            if self.writer and type(self.connector.pool) == CyclicQueuePool:
                self.close(False, True)
            if not self.cycled:
                await self.release()
            raise

    async def release(self) -> None:
        """Release connection."""
        if self.cycled:
            return None
        self.cycled = True
        await self.connector.release(self)
        self.requests_count += 1
        # if keep False and blocked (by latest chunked response), close it.
        # server said to close it.
        if self.requests_count >= self.connector.conn_max_requests or (
            not self.keep and self.blocked
        ):
            self.blocked = False
            self.close()
        # ensure unblock conn object after read
        self.blocked = False

    def __del__(self) -> None:
        """Cleanup."""
        if not self.cycled:
            self.close(True, True)

    def close(self, back_to_queue: bool = False, abort_transport: bool = False) -> None:
        """Close connection if opened."""
        if self.writer and not self.is_closing():
            self.blocked = False
            self.writer.close()
        if self.writer and abort_transport:
            self.writer._transport.abort()
        if back_to_queue == True:
            if not self.cycled:
                self.cycled = True
                self.connector.pool.pool.put_nowait(self)

    async def http2_request(
        self, headers: Dict[str, str], body: Optional[ParsedBodyType]
    ):
        if self.h2handler:  # pragma: no cover
            return await self.h2handler.request(headers, body)


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
