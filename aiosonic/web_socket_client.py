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
from typing import Optional, Tuple, List, Dict

from aiosonic import TCPConnector, http_parser
from aiosonic.connection import Connection
from aiosonic.exceptions import ConnectionDisconnected, ReadTimeout
from aiosonic.pools import WsPool
from aiosonic.timeout import Timeouts


class WebSocketConnection:
    """
    Manages a WebSocket connection.

    This class provides methods to send and receive messages (text, binary, and JSON)
    over a WebSocket connection, as well as to handle ping/pong messages and to close
    the connection properly.

    Attributes:
        conn (Connection): The underlying connection.
        connected (bool): Flag indicating whether the connection is active.
        close_code (Optional[int]): The close code returned after a close frame is sent.
        subprotocol (Optional[str]): The negotiated subprotocol, if any.
    """

    # WebSocket OpCodes
    OPCODE_TEXT = 0x1
    OPCODE_BINARY = 0x2
    OPCODE_CLOSE = 0x8
    OPCODE_PING = 0x9
    OPCODE_PONG = 0xA

    def __init__(self, conn: Connection):
        """
        Initialize a new WebSocketConnection.

        :param conn: The underlying TCP connection.
        """
        self.conn = conn
        self.connected = True
        self.close_code: Optional[int] = None
        self.subprotocol: Optional[str] = None
        self._send_lock = asyncio.Lock()
        self._read_lock = asyncio.Lock()

    def _build_frame(self, opcode: int, payload: bytes) -> bytes:
        """
        Build a WebSocket frame with the given opcode and payload.
        The frame is masked, as required for client-to-server messages.

        :param opcode: The opcode for the frame.
        :param payload: The payload data as bytes.
        :return: The complete WebSocket frame.
        """
        # FIN bit (1) plus opcode
        fin_and_opcode = 0x80 | (opcode & 0x0F)
        header = bytearray([fin_and_opcode])
        mask_bit = 0x80  # Clients must mask frames

        payload_length = len(payload)
        if payload_length < 126:
            header.append(mask_bit | payload_length)
        elif payload_length < 65536:
            header.append(mask_bit | 126)
            header.extend(struct.pack(">H", payload_length))
        else:
            header.append(mask_bit | 127)
            header.extend(struct.pack(">Q", payload_length))

        # Append a random 4-byte masking key and mask the payload.
        masking_key = os.urandom(4)
        header.extend(masking_key)
        masked_payload = bytearray(payload)
        for i in range(len(masked_payload)):
            masked_payload[i] ^= masking_key[i % 4]

        return bytes(header) + bytes(masked_payload)

    async def _send_frame(self, opcode: int, payload: bytes):
        """
        Build and send a WebSocket frame with the specified opcode and payload.

        :param opcode: The opcode for the frame.
        :param payload: The payload data as bytes.
        """
        frame = self._build_frame(opcode, payload)
        async with self._send_lock:
            self.conn.write(frame)
            await self.conn.writer.drain()

    async def _read_frame(self) -> Tuple[int, bytes]:
        """
        Read a WebSocket frame from the connection.

        :return: A tuple (opcode, payload) where opcode is an integer and payload is bytes.
        :raises: asyncio.IncompleteReadError if the stream ends unexpectedly.
        """
        async with self._read_lock:
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

    async def send_text(self, message: str):
        """
        Send a text message over the WebSocket connection.

        :param message: The text message to send.
        """
        await self._send_frame(self.OPCODE_TEXT, message.encode("utf-8"))

    async def receive_text(self, timeout: Optional[float] = None) -> str:
        """
        Receive a text message from the WebSocket connection.

        If no frame is received within `timeout` seconds, a ReadTimeout is raised.
        If the connection is closed unexpectedly, a ConnectionDisconnected is raised.

        :param timeout: Optional timeout in seconds.
        :return: The received text message.
        :raises ReadTimeout: If the read operation times out.
        :raises ConnectionDisconnected: If the connection closes unexpectedly.
        :raises ValueError: If the received frame is not a text frame.
        """
        try:
            opcode, payload = await asyncio.wait_for(self._read_frame(), timeout=timeout)
        except asyncio.IncompleteReadError as exc:
            # Indicates that the stream ended unexpectedly.
            self.conn.keep = False  # Flag connection as unusable, if applicable.
            raise ConnectionDisconnected("Connection was closed unexpectedly") from exc
        except asyncio.TimeoutError as exc:
            raise ReadTimeout("Timed out while waiting for a frame") from exc

        if opcode != self.OPCODE_TEXT:
            raise ValueError(f"Expected text frame, got opcode {opcode}")
        return payload.decode("utf-8")

    async def send_bytes(self, data: bytes):
        """
        Send binary data as a WebSocket frame.

        :param data: The binary data to send.
        """
        await self._send_frame(self.OPCODE_BINARY, data)

    async def receive_bytes(self) -> bytes:
        """
        Receive a binary message from the WebSocket connection.

        :return: The binary data received.
        :raises ValueError: If the received frame is not a binary frame.
        """
        opcode, payload = await self._read_frame()
        if opcode != self.OPCODE_BINARY:
            raise ValueError(f"Expected binary frame, got opcode {opcode}")
        return payload

    async def send_json(self, data):
        """
        Serialize data to JSON and send it as a text frame.

        :param data: The data to serialize and send.
        """
        await self.send_text(json.dumps(data))

    async def receive_json(self):
        """
        Receive a text frame and deserialize it from JSON.

        :return: The deserialized JSON object.
        """
        return json.loads(await self.receive_text())

    async def ping(self, data: bytes = b''):
        """
        Send a ping frame with an optional payload.

        :param data: Optional payload data (must be <=125 bytes).
        :raises ValueError: If payload exceeds 125 bytes.
        """
        if len(data) > 125:
            raise ValueError("Ping payload must be 125 bytes or less")
        await self._send_frame(self.OPCODE_PING, data)

    async def receive_pong(self) -> bytes:
        """
        Receive a pong frame from the WebSocket connection.

        :return: The pong payload as bytes.
        :raises ValueError: If the received frame is not a pong frame.
        """
        opcode, payload = await self._read_frame()
        if opcode != self.OPCODE_PONG:
            raise ValueError(f"Expected pong frame, got opcode {opcode}")
        return payload

    async def close(self, code: int = 1000, reason: str = ""):
        """
        Send a WebSocket close frame with the given status code and reason,
        then close the underlying connection.

        :param code: The WebSocket close code.
        :param reason: The reason for closing the connection.
        :raises ValueError: If the close payload exceeds 125 bytes.
        """
        payload = struct.pack(">H", code) + reason.encode("utf-8")
        if len(payload) > 125:
            raise ValueError("Close payload must be 125 bytes or less")
        await self._send_frame(self.OPCODE_CLOSE, payload)
        self.close_code = code
        self.connected = False
        self.conn.close()

    async def __aenter__(self):
        """
        Enter the asynchronous context manager.

        :return: The WebSocketConnection instance.
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the asynchronous context manager, closing the connection if still active.
        """
        if self.connected:
            await self.close()


class WebSocketClient:
    """
    WebSocket Client.

    This class handles the HTTP upgrade process and establishes a WebSocket
    connection. It supports custom headers and subprotocol negotiation.

    Attributes:
        connector (TCPConnector): The TCP connector to use for the connection.
        timeouts (Timeouts): Timeout settings.
    """

    def __init__(self, connector: Optional[TCPConnector] = None):
        """
        Initialize a new WebSocketClient.

        :param connector: Optional custom TCPConnector.
        """
        self.connector = connector or TCPConnector(pool_cls=WsPool)
        self.timeouts = Timeouts()

    async def connect(
        self,
        url: str,
        verify: bool = True,
        ssl: Optional[bool] = None,
        headers: Optional[Dict[str, str]] = None,
        subprotocols: Optional[List[str]] = None,
    ) -> WebSocketConnection:
        """
        Connect to a WebSocket server.

        Performs the HTTP upgrade handshake to establish the WebSocket connection.
        Custom headers and subprotocols can be provided.

        :param url: The WebSocket URL.
        :param verify: Whether to verify the SSL certificate.
        :param ssl: Whether to use SSL (if None, inferred from the URL scheme).
        :param headers: Optional custom headers to include in the handshake.
        :param subprotocols: Optional list of subprotocols for negotiation.
        :return: An instance of WebSocketConnection.
        :raises ConnectionError: If the handshake fails.
        """
        urlparsed = http_parser.get_url_parsed(url)
        ssl = ssl or (urlparsed.scheme == "wss")

        # Generate the WebSocket key
        ws_key = base64.b64encode(os.urandom(16)).decode()

        # Prepare base headers for the upgrade request
        base_headers = {
            "Host": f"{urlparsed.hostname}:{urlparsed.port or (443 if ssl else 80)}",
            "Upgrade": "websocket",
            "Connection": "Upgrade",
            "Sec-WebSocket-Key": ws_key,
            "Sec-WebSocket-Version": "13",
        }

        # Add subprotocols if provided
        if subprotocols:
            base_headers["Sec-WebSocket-Protocol"] = ", ".join(subprotocols)

        # Merge custom headers if provided
        if headers:
            base_headers.update(headers)

        # Create upgrade request
        path = urlparsed.path or "/"
        if urlparsed.query:
            path = f"{path}?{urlparsed.query}"

        request = f"GET {path} HTTP/1.1\r\n"
        request += "\r\n".join(f"{k}: {v}" for k, v in base_headers.items())
        request += "\r\n\r\n"

        conn = await self.connector.acquire(urlparsed, verify, ssl, self.timeouts, False)

        # Send upgrade request
        conn.write(request.encode())
        await conn.writer.drain()

        # Read response status line
        status_line = await conn.readline()
        if not status_line.startswith(b"HTTP/1.1 101"):
            raise ConnectionError(f"WebSocket upgrade failed: {status_line.decode()}")

        # Prepare the expected accept key
        expected_key = base64.b64encode(
            hashlib.sha1(f"{ws_key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11".encode()).digest()
        ).decode()

        ws_protocol: Optional[str] = None
        # Read headers
        while True:
            line = await conn.readline()
            if line == b"\r\n":
                break
            if line.startswith(b"Sec-WebSocket-Accept: "):
                received_key = line.decode().split(":", 1)[1].strip()
                if received_key != expected_key:
                    raise ConnectionError("Invalid WebSocket Accept key")
            elif line.startswith(b"Sec-WebSocket-Protocol:"):
                ws_protocol = line.decode().split(":", 1)[1].strip()

        ws_conn = WebSocketConnection(conn)
        ws_conn.subprotocol = ws_protocol
        return ws_conn

    async def __aenter__(self):
        """
        Enter the asynchronous context manager.

        :return: The WebSocketClient instance.
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the asynchronous context manager.
        """
        # Optionally close the connector if needed.
        pass
