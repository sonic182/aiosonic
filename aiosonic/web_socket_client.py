"""
WebSocket Client Module
=======================

This module implements a WebSocket client for aiosonic, providing a
WebSocketConnection class for managing WebSocket connections and a
WebSocketClient class for performing the upgrade handshake and connecting
to a WebSocket server.

Classes:
    WebSocketConnection: Manages a WebSocket connection and provides methods
                         for sending and receiving text, binary, and JSON messages,
                         as well as handling ping/pong and closing the connection.
    WebSocketClient: Performs the HTTP upgrade request and establishes a
                     WebSocket connection with optional custom headers and
                     subprotocol negotiation.

Exceptions:
    ConnectionDisconnected: Raised when the connection is unexpectedly closed.
    ReadTimeout: Raised when a read operation times out.
"""

import asyncio
import base64
import hashlib
import json
import os
import struct
from abc import ABC, abstractmethod
from ssl import SSLContext
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from aiosonic import http_parser
from aiosonic.connectors import TCPConnector
from aiosonic.exceptions import ConnectionDisconnected, ReadTimeout
from aiosonic.pools import WsPool
from aiosonic.timeout import Timeouts

if TYPE_CHECKING:
    from aiosonic.connection import Connection

CRLF = "\r\n"
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


# --- Protocol Handler Definitions ---
class ProtocolHandler(ABC):
    """
    Base class for WebSocket subprotocol handlers.

    To implement a custom protocol (for example, using MessagePack), subclass
    this base class and implement the encode and decode methods. For example:

    .. code-block:: python

        import msgpack

        class MsgpackHandler(ProtocolHandler):
            @property
            def name(self) -> str:
                return "msgpack"
            
            def encode(self, data) -> bytes:
                return msgpack.packb(data, use_bin_type=True)
            
            def decode(self, data: bytes):
                return msgpack.unpackb(data, raw=False)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the protocol name used for negotiation."""
        pass

    @abstractmethod
    def encode(self, data) -> bytes:
        """Encode data into bytes."""
        pass

    @abstractmethod
    def decode(self, data: bytes):
        """Decode bytes into data."""
        pass


class WebSocketConnection:
    OPCODE_TEXT = 0x1
    OPCODE_BINARY = 0x2
    OPCODE_CLOSE = 0x8
    OPCODE_PING = 0x9
    OPCODE_PONG = 0xA

    def __init__(
        self,
        conn: "Connection",
        text_queue_maxsize: int = 100,
        binary_queue_maxsize: int = 100,
        drop_frames: bool = False,
        protocol_handler: Optional[ProtocolHandler] = None
    ):
        self.conn = conn
        self.connected = True
        self.close_code: Optional[int] = None
        self.subprotocol: Optional[str] = None
        self._send_lock = asyncio.Lock()
        # Queues for different frame types.
        self._text_queue = asyncio.Queue(maxsize=text_queue_maxsize)
        self._binary_queue = asyncio.Queue(maxsize=binary_queue_maxsize)
        self._pong_queue = asyncio.Queue()  # pong queue remains unlimited
        # Store drop settings.
        self._drop_frames = drop_frames
        self.protocol_handler = protocol_handler
        # Start the dispatcher loop.
        self._frame_dispatch_task = asyncio.create_task(self._frame_dispatch_loop())
        self._keep_alive_task = None

    async def _build_frame(self, opcode: int, payload: bytes) -> bytes:
        fin_and_opcode = 0x80 | (opcode & 0x0F)
        header = bytearray([fin_and_opcode])
        mask_bit = 0x80  # Clients must mask frames.
        payload_length = len(payload)
        if payload_length < 126:
            header.append(mask_bit | payload_length)
        elif payload_length < 65536:
            header.append(mask_bit | 126)
            header.extend(struct.pack(">H", payload_length))
        else:
            header.append(mask_bit | 127)
            header.extend(struct.pack(">Q", payload_length))
        masking_key = os.urandom(4)
        header.extend(masking_key)
        masked_payload = bytearray(payload)
        for i in range(len(masked_payload)):
            masked_payload[i] ^= masking_key[i % 4]
        return bytes(header) + bytes(masked_payload)

    async def _send_frame(self, opcode: int, payload: bytes):
        frame = await self._build_frame(opcode, payload)
        async with self._send_lock:
            self.conn.write(frame)
            await self.conn.writer.drain()

    async def _read_frame(self) -> Tuple[int, bytes]:
        header = await self.conn.readexactly(2)
        opcode = header[0] & 0x0F
        mask = (header[1] & 0x80) != 0
        payload_length = header[1] & 0x7F

        if payload_length == 126:
            ext = await self.conn.readexactly(2)
            payload_length = struct.unpack(">H", ext)[0]
        elif payload_length == 127:
            ext = await self.conn.readexactly(8)
            payload_length = struct.unpack(">Q", ext)[0]

        if mask:
            masking_key = await self.conn.readexactly(4)
            masked_payload = await self.conn.readexactly(payload_length)
            payload = bytearray(masked_payload)
            for i in range(payload_length):
                payload[i] ^= masking_key[i % 4]
            payload = bytes(payload)
        else:
            payload = await self.conn.readexactly(payload_length)
        return opcode, payload

    async def _enqueue(self, queue: asyncio.Queue, payload: bytes):
        """Helper to enqueue payload using blocking or dropping behavior."""
        if self._drop_frames:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Optionally log a dropped frame warning.
                pass
        else:
            await queue.put(payload)

    async def _frame_dispatch_loop(self):
        """
        Continuously read frames and enqueue them in their respective queues.
        Uses blocking puts by default (backpressure) unless drop mode is enabled.
        """
        try:
            while self.connected:
                try:
                    opcode, payload = await self._read_frame()
                except asyncio.IncompleteReadError:
                    self.connected = False
                    break
                if opcode == self.OPCODE_TEXT:
                    await self._enqueue(self._text_queue, payload)
                elif opcode == self.OPCODE_BINARY:
                    await self._enqueue(self._binary_queue, payload)
                elif opcode == self.OPCODE_PONG:
                    await self._pong_queue.put(payload)
                elif opcode == self.OPCODE_CLOSE:
                    self.connected = False
                    break
                # Optionally, handle OPCODE_PING if needed.
        except Exception:
            self.connected = False

    # --- Public API for Sending/Receiving Frames ---
    async def send_text(self, message: str):
        await self._send_frame(self.OPCODE_TEXT, message.encode("utf-8"))

    async def receive_text(self, timeout: Optional[float] = None) -> str:
        try:
            payload = await asyncio.wait_for(self._text_queue.get(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            if not self.connected:
                raise ConnectionDisconnected("Connection was closed unexpectedly") from exc
            raise ReadTimeout("Timed out while waiting for a text frame") from exc
        return payload.decode("utf-8")

    async def send_bytes(self, data: bytes):
        await self._send_frame(self.OPCODE_BINARY, data)

    async def receive_bytes(self, timeout: Optional[float] = None) -> bytes:
        try:
            payload = await asyncio.wait_for(self._binary_queue.get(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            if not self.connected:
                raise ConnectionDisconnected("Connection was closed unexpectedly") from exc
            raise ReadTimeout("Timed out while waiting for a binary frame") from exc
        return payload

    async def send_json(self, data):
        await self.send_text(json.dumps(data))

    async def receive_json(self, timeout: Optional[float] = None):
        return json.loads(await self.receive_text(timeout=timeout))

    async def ping(self, data: bytes = b""):
        if len(data) > 125:
            raise ValueError("Ping payload must be 125 bytes or less")
        await self._send_frame(self.OPCODE_PING, data)

    async def receive_pong(self, timeout: Optional[float] = None) -> bytes:
        try:
            payload = await asyncio.wait_for(self._pong_queue.get(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            if not self.connected:
                raise ConnectionDisconnected("Connection was closed unexpectedly") from exc
            raise ReadTimeout("Timed out while waiting for a pong frame") from exc
        return payload

    async def close(self, code: int = 1000, reason: str = ""):
        self.stop_keep_alive()
        payload = struct.pack(">H", code) + reason.encode("utf-8")
        if len(payload) > 125:
            raise ValueError("Close payload must be 125 bytes or less")
        await self._send_frame(self.OPCODE_CLOSE, payload)
        self.close_code = code
        self.connected = False
        self.conn.close()
        self._frame_dispatch_task.cancel()

    # --- Convenience Methods for Protocol Handlers ---
    async def send_protocol(self, data):
        """Send data using the configured protocol handler."""
        if not self.protocol_handler:
            raise RuntimeError("No protocol handler configured")
        encoded = self.protocol_handler.encode(data)
        await self._send_frame(self.OPCODE_BINARY, encoded)

    async def receive_protocol(self, timeout: Optional[float] = None):
        """Receive data using the configured protocol handler."""
        if not self.protocol_handler:
            raise RuntimeError("No protocol handler configured")
        data = await self.receive_bytes(timeout=timeout)
        return self.protocol_handler.decode(data)

    # --- Keep-Alive Task Implementation ---
    def start_keep_alive(self, interval: float = 30.0):
        if self._keep_alive_task is None:
            self._keep_alive_task = asyncio.create_task(self._keep_alive_loop(interval))

    def stop_keep_alive(self):
        if self._keep_alive_task is not None:
            self._keep_alive_task.cancel()
            self._keep_alive_task = None

    async def _keep_alive_loop(self, interval: float):
        try:
            while self.connected:
                await self.ping()
                try:
                    await asyncio.wait_for(self.receive_pong(), timeout=interval)
                except asyncio.TimeoutError:
                    # Optionally, log a warning or take action.
                    pass
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return

    # --- Context Manager Support ---
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.connected:
            await self.close()


class WebSocketClient:
    """
    WebSocket Client.

    This class handles the HTTP upgrade process and establishes a WebSocket
    connection. It supports custom headers, subprotocol negotiation, and
    optional keep-alive functionality.
    """

    def __init__(self, connector: Optional[TCPConnector] = None):
        self.connector = connector or TCPConnector(pool_cls=WsPool)
        self.timeouts = Timeouts()

    async def connect(
        self,
        url: str,
        verify: bool = True,
        ssl: Optional[SSLContext] = None,
        headers: Optional[Dict[str, str]] = None,
        subprotocols: Optional[List[str]] = None,
        start_keepalive: bool = True,
        keepalive_interval: float = 30.0,
        conn_opts: Optional[dict] = None
    ) -> "WebSocketConnection":
        """
        Connect to a WebSocket server, optionally starting the keep-alive task.

        :param url: The WebSocket URL.
        :param verify: Whether to verify the SSL certificate.
        :param ssl: Custom SSL context if needed.
        :param headers: Optional custom headers.
        :param subprotocols: Optional list of subprotocols.
        :param start_keepalive: Whether to start the keep-alive ping task.
        :param keepalive_interval: Interval in seconds between pings.
        :param conn_opts: Options to override default options for WebSocketConnection.
        :return: An instance of WebSocketConnection.
        :raises ConnectionError: If the upgrade handshake fails.
        """
        conn_opts = conn_opts or {}
        urlparsed = http_parser.get_url_parsed(url)
        secured = ssl or (urlparsed.scheme == "wss")

        # Generate the WebSocket key.
        ws_key = base64.b64encode(os.urandom(16)).decode()

        base_headers = {
            "Host": f"{urlparsed.hostname}:{urlparsed.port or (443 if secured else 80)}",
            "Upgrade": "websocket",
            "Connection": "Upgrade",
            "Sec-WebSocket-Key": ws_key,
            "Sec-WebSocket-Version": "13",
        }

        if subprotocols:
            base_headers["Sec-WebSocket-Protocol"] = ", ".join(subprotocols)

        if headers:
            base_headers.update(headers)

        path = urlparsed.path or "/"
        if urlparsed.query:
            path = f"{path}?{urlparsed.query}"

        request = f"GET {path} HTTP/1.1{CRLF}"
        request += CRLF.join(f"{k}: {v}" for k, v in base_headers.items())
        request += CRLF * 2

        conn = await self.connector.acquire(urlparsed, verify, ssl, self.timeouts, False)

        # Send the upgrade request.
        conn.write(request.encode())
        await conn.writer.drain()

        # Read the response status line.
        status_line = await conn.readline()
        if not status_line.startswith(b"HTTP/1.1 101"):
            raise ConnectionError(f"WebSocket upgrade failed: {status_line.decode()}")

        expected_key = base64.b64encode(
            hashlib.sha1(f"{ws_key}{WEBSOCKET_GUID}".encode()).digest()
        ).decode()

        ws_protocol: Optional[str] = None
        # Read headers.
        while True:
            line = await conn.readline()
            if line == CRLF.encode():
                break
            if line.startswith(b"Sec-WebSocket-Accept: "):
                received_key = line.decode().split(":", 1)[1].strip()
                if received_key != expected_key:
                    raise ConnectionError("Invalid WebSocket Accept key")
            elif line.startswith(b"Sec-WebSocket-Protocol:"):
                ws_protocol = line.decode().split(":", 1)[1].strip()

        ws_conn = WebSocketConnection(conn, **conn_opts)
        ws_conn.subprotocol = ws_protocol

        # Start keep-alive by default, unless explicitly disabled.
        if start_keepalive:
            ws_conn.start_keep_alive(interval=keepalive_interval)

        return ws_conn

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Optionally, clean up the connector here if necessary.
        pass
