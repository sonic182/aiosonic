"""
WebSocket Client Module
=======================

This module implements a WebSocket client for aiosonic. It provides a
WebSocketConnection class for managing WebSocket connections (including
sending/receiving text, binary, and JSON messages, ping/pong keep-alive,
and graceful closing) and a WebSocketClient class for performing the HTTP
upgrade handshake and connecting to a WebSocket server.

Classes:
    Message
        Represents a WebSocket message.

    ProtocolHandler
        Base class for custom protocol encoding/decoding.

    WebSocketConnection
        Manages a WebSocket connection, including an async iterator to
        receive normal messages.

    WebSocketClient
        Establishes a WebSocket connection.

Exceptions:
    ConnectionDisconnected
        Raised when the connection is unexpectedly closed.

    WebSocketMessageTooBig
        Raised when a received message is bigger than ``max_msg_size``.

    ReadTimeout
        Raised when a read operation times out.
"""

from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import os
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from ssl import SSLContext
from typing import Dict, List, Optional, Tuple, Union

from aiosonic import http_parser
from aiosonic.connectors import TCPConnector
from aiosonic.exceptions import ConnectionDisconnected, ReadTimeout, WebSocketMessageTooBig
from aiosonic.pools import WsPool
from aiosonic.timeout import Timeouts
from aiosonic.utils import get_debug_logger

dlogger = get_debug_logger()

CRLF = "\r\n"
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
DEFAULT_MAX_MSG_SIZE = 4 * 1024 * 1024
_CLOSE_MESSAGE_TOO_BIG = 1009
_MAX_CONTROL_FRAME_SIZE = 125


class MessageType(Enum):
    TEXT = "text"
    BINARY = "binary"
    PING = "ping"
    PONG = "pong"
    CLOSE = "close"


@dataclass
class Message:
    type: MessageType
    data: Union[str, bytes]
    raw_data: bytes
    opcode: int

    @classmethod
    def create_text(cls, data: str) -> Message:
        return cls(
            type=MessageType.TEXT,
            data=data,
            raw_data=data.encode("utf-8"),
            opcode=0x1,
        )

    @classmethod
    def create_binary(cls, data: bytes) -> Message:
        return cls(
            type=MessageType.BINARY,
            data=data,
            raw_data=data,
            opcode=0x2,
        )


class ProtocolHandler(ABC):
    """
    Base class for WebSocket subprotocol handlers.

    To implement a custom protocol (e.g. MessagePack), subclass this base class
    and implement the encode and decode methods.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def encode(self, data) -> bytes:
        pass

    @abstractmethod
    def decode(self, data: bytes):
        pass


class WebSocketConnection:
    """Manages an active WebSocket connection.

    This class handles the WebSocket protocol details including:
    - Sending/receiving text and binary messages
    - Frame masking and unmasking
    - Ping/pong for connection keep-alive
    - Protocol handlers for custom message formats
    - Connection lifecycle management

    Args:
        conn: The underlying network connection
        queue_maxsize (int): Maximum size of the message queue (default: 100)
        drop_frames (bool): Whether to drop frames when queue is full (default: False)
        protocol_handler (ProtocolHandler): Optional handler for custom protocols
        max_msg_size (Optional[int]): Maximum size in bytes of a received frame, ``None`` for no limit
            (default: 4 MiB). A bigger frame is not read: the connection is closed with code 1009, and receiving
            raises :class:`aiosonic.exceptions.WebSocketMessageTooBig`. Up to ``queue_maxsize`` received messages
            are kept until they are read, so the memory used can reach about ``queue_maxsize * max_msg_size``
            bytes. A control frame bigger than 125 bytes is handled the same way.

    Attributes:
        connected (bool): Whether the connection is currently active
        close_code (Optional[int]): The close code if connection was closed
        subprotocol (Optional[str]): The negotiated subprotocol if any

    Example:

        .. code-block:: python

          async with WebSocketClient() as client:
              # Connect to a WebSocket server
              conn = await client.connect('ws://example.com/ws')

              # Start reading messages in a loop
              async for msg in conn:
                  if msg.type == MessageType.TEXT:
                      print(f"Received text: {msg.data}")
                  elif msg.type == MessageType.BINARY:
                      print(f"Received binary data of length: {len(msg.data)}")

                  # Connection will auto-close after loop ends or when
                  # server disconnects
    """

    OPCODE_TEXT = 0x1
    OPCODE_BINARY = 0x2
    OPCODE_CLOSE = 0x8
    OPCODE_PING = 0x9
    OPCODE_PONG = 0xA

    def __init__(
        self,
        conn,
        queue_maxsize: int = 100,
        drop_frames: bool = False,
        protocol_handler: Optional[ProtocolHandler] = None,
        max_msg_size: Optional[int] = DEFAULT_MAX_MSG_SIZE,
    ):
        self.conn = conn
        self.connected = True
        self.close_code: Optional[int] = None
        self.max_msg_size = max_msg_size
        self._too_big_reason: Optional[str] = None
        self._receivers_woken = False
        self.subprotocol: Optional[str] = None
        self._send_lock = asyncio.Lock()
        # Unified message queue for normal (text/binary) messages.
        self._msg_queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=queue_maxsize)
        # Separate queue for ping/pong messages.
        self._pong_queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=queue_maxsize)
        self._drop_frames = drop_frames
        self.protocol_handler = protocol_handler
        self._frame_dispatch_task = asyncio.create_task(self._frame_dispatch_loop())
        self._keep_alive_task = None
        dlogger.debug("WebSocketConnection created, dispatch task: %s", id(self))

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

    async def _send_frame(self, opcode: int, payload: bytes) -> None:
        dlogger.debug("_send_frame opcode=%s len=%s", opcode, len(payload))
        frame = await self._build_frame(opcode, payload)
        async with self._send_lock:
            if self.conn.writer is None or (
                opcode != self.OPCODE_CLOSE and (not self.connected or self.close_code is not None)
            ):
                raise self._disconnected_error()
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

        dlogger.debug("_read_frame opcode=%s mask=%s payload_length=%s", opcode, mask, payload_length)

        if opcode & 0x8 and payload_length > _MAX_CONTROL_FRAME_SIZE:
            raise WebSocketMessageTooBig(
                f"control frame of {payload_length} bytes is bigger than {_MAX_CONTROL_FRAME_SIZE} bytes"
            )
        if self.max_msg_size is not None and payload_length > self.max_msg_size:
            raise WebSocketMessageTooBig(
                f"message of {payload_length} bytes is bigger than max_msg_size ({self.max_msg_size} bytes)"
            )

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

    async def _enqueue(self, queue: asyncio.Queue, message: Message):
        if self._drop_frames:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Optionally log a dropped frame.
                pass
        else:
            await queue.put(message)

    async def _frame_dispatch_loop(self):
        try:
            while self.connected:
                try:
                    opcode, payload = await self._read_frame()
                except asyncio.IncompleteReadError:
                    dlogger.debug("_frame_dispatch_loop: IncompleteReadError, disconnecting")
                    self.connected = False
                    break
                except WebSocketMessageTooBig as exc:
                    await self._close_message_too_big(str(exc))
                    break

                dlogger.debug("_frame_dispatch_loop: received opcode=%s payload_len=%s", opcode, len(payload))
                if opcode == self.OPCODE_TEXT:
                    msg = Message.create_text(payload.decode("utf-8"))
                    await self._enqueue(self._msg_queue, msg)
                elif opcode == self.OPCODE_BINARY:
                    msg = Message.create_binary(payload)
                    await self._enqueue(self._msg_queue, msg)
                elif opcode == self.OPCODE_PONG:
                    msg = Message(
                        type=MessageType.PONG,
                        data=payload,
                        raw_data=payload,
                        opcode=self.OPCODE_PONG,
                    )
                    try:
                        self._pong_queue.put_nowait(msg)
                    except asyncio.QueueFull:
                        pass
                elif opcode == self.OPCODE_CLOSE:
                    self.connected = False
                    break
                # Optionally handle OPCODE_PING if desired.
        except Exception:
            dlogger.debug("_frame_dispatch_loop: exception, disconnecting", exc_info=True)
            self.connected = False
        finally:
            self.connected = False
            self._wake_receivers()

    def _wake_receivers(self) -> None:
        if self._receivers_woken:
            return
        self._receivers_woken = True
        for queue in (self._msg_queue, self._pong_queue):
            try:
                queue.put_nowait(Message(MessageType.CLOSE, b"", b"", self.OPCODE_CLOSE))
            except asyncio.QueueFull:
                pass

    async def _close_message_too_big(self, reason: str) -> None:
        dlogger.debug("_frame_dispatch_loop: %s, closing", reason)
        self._too_big_reason = reason
        self.connected = False
        self.stop_keep_alive()
        sent = False
        if self.close_code is None and self.conn.writer is not None:
            self.close_code = _CLOSE_MESSAGE_TOO_BIG
            frame = await self._build_frame(self.OPCODE_CLOSE, struct.pack(">H", _CLOSE_MESSAGE_TOO_BIG))
            self.conn.write(frame)
            sent = True
        self._wake_receivers()
        if sent:
            try:
                await asyncio.wait_for(self.conn.writer.drain(), timeout=1)
            except Exception:
                dlogger.debug("_close_message_too_big: could not send the close frame", exc_info=True)
        self.conn.close()

    def _disconnected_error(self) -> ConnectionDisconnected:
        if self._too_big_reason:
            return WebSocketMessageTooBig(self._too_big_reason)
        return ConnectionDisconnected("Connection is closed")

    async def send_text(self, message: str):
        await self._send_frame(self.OPCODE_TEXT, message.encode("utf-8"))

    async def receive_text(self, timeout: Optional[float] = None) -> str:
        msg = await self._get_message(timeout=timeout)
        if msg.type != MessageType.TEXT:
            raise ValueError("Expected a text message")
        return msg.data  # type: ignore

    async def send_bytes(self, data: bytes):
        await self._send_frame(self.OPCODE_BINARY, data)

    async def receive_bytes(self, timeout: Optional[float] = None) -> bytes:
        msg = await self._get_message(timeout=timeout)
        if msg.type != MessageType.BINARY:
            raise ValueError("Expected a binary message")
        return msg.raw_data

    async def send_json(self, data):
        await self.send_text(json.dumps(data))

    async def receive_json(self, timeout: Optional[float] = None):
        return json.loads(await self.receive_text(timeout=timeout))

    async def ping(self, data: bytes = b""):
        if len(data) > 125:
            raise ValueError("Ping payload must be 125 bytes or less")
        await self._send_frame(self.OPCODE_PING, data)

    async def receive_pong(self, timeout: Optional[float] = None) -> bytes:
        if not self.connected and self._pong_queue.empty():
            raise self._disconnected_error()
        try:
            msg = await asyncio.wait_for(self._pong_queue.get(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            if not self.connected:
                raise self._disconnected_error() from exc
            raise ReadTimeout("Timed out while waiting for a pong frame") from exc
        if msg.type == MessageType.CLOSE:
            self._pong_queue.put_nowait(msg)
            raise self._disconnected_error()
        if msg.type != MessageType.PONG:
            raise ValueError("Expected a pong message")
        return msg.raw_data

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the connection.

        At most one Close frame is sent. After the server closed the connection, the Close frame answers it and a
        failure to send it is ignored. After ``close()`` or a message over ``max_msg_size``, no frame is sent and
        ``close_code`` is kept. The socket is closed in every case.

        Args:
            code (int): The close code to send.
            reason (str): The close reason to send.

        Raises:
            ValueError: If the close payload is bigger than 125 bytes.
        """
        dlogger.debug("close code=%s reason=%s", code, reason)
        self.stop_keep_alive()
        payload = struct.pack(">H", code) + reason.encode("utf-8")
        if len(payload) > _MAX_CONTROL_FRAME_SIZE:
            raise ValueError("Close payload must be 125 bytes or less")
        try:
            if self.close_code is None and self.conn.writer is not None:
                self.close_code = code
                was_connected = self.connected
                try:
                    await self._send_frame(self.OPCODE_CLOSE, payload)
                except (OSError, ConnectionDisconnected):
                    if was_connected:
                        raise
                    dlogger.debug("close: could not answer the server close", exc_info=True)
        finally:
            self.connected = False
            self.conn.close()
            self._frame_dispatch_task.cancel()

    async def send_protocol(self, data):
        if not self.protocol_handler:
            raise RuntimeError("No protocol handler configured")
        encoded = self.protocol_handler.encode(data)
        await self._send_frame(self.OPCODE_BINARY, encoded)

    async def receive_protocol(self, timeout: Optional[float] = None):
        if not self.protocol_handler:
            raise RuntimeError("No protocol handler configured")
        msg = await self._get_message(timeout=timeout)
        return self.protocol_handler.decode(msg.raw_data)

    async def _get_message(self, timeout: Optional[float] = None) -> Message:
        if not self.connected and self._msg_queue.empty():
            raise self._disconnected_error()
        try:
            msg = await asyncio.wait_for(self._msg_queue.get(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            if not self.connected:
                raise self._disconnected_error() from exc
            raise ReadTimeout("Timed out while waiting for a message") from exc
        if msg.type == MessageType.CLOSE:
            self._msg_queue.put_nowait(msg)
            raise self._disconnected_error()
        return msg

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
                    # Optionally log a warning.
                    pass
                await asyncio.sleep(interval)
        except (asyncio.CancelledError, ConnectionDisconnected):
            return

    async def __aiter__(self):
        while self.connected or not self._msg_queue.empty():
            try:
                msg = await self._get_message()
            except WebSocketMessageTooBig:
                raise
            except (ReadTimeout, ConnectionDisconnected):
                break
            yield msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.connected:
            await self.close()


class WebSocketClient:
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
        conn_opts: Optional[dict] = None,
        max_msg_size: Optional[int] = DEFAULT_MAX_MSG_SIZE,
    ) -> WebSocketConnection:
        """Open a WebSocket connection with the HTTP upgrade handshake.

        Args:
            url (str): The ``ws://`` or ``wss://`` url to connect to.
            verify (bool): Whether to verify the ssl certificate.
            ssl (Optional[SSLContext]): A custom ssl context.
            headers (Optional[Dict[str, str]]): Extra headers for the handshake request.
            subprotocols (Optional[List[str]]): Subprotocols to offer in ``Sec-WebSocket-Protocol``.
            start_keepalive (bool): Whether to send pings periodically.
            keepalive_interval (float): Seconds between keep-alive pings.
            conn_opts (Optional[dict]): Extra arguments for :class:`WebSocketConnection`. A ``max_msg_size`` key
                here is ignored: use the ``max_msg_size`` argument.
            max_msg_size (Optional[int]): Maximum size in bytes of a received frame, ``None`` for no limit
                (default: 4 MiB). A bigger frame is not read: the connection is closed with code 1009, and
                receiving raises :class:`aiosonic.exceptions.WebSocketMessageTooBig`. Up to ``queue_maxsize``
                received messages are kept until they are read, so the memory used can reach about
                ``queue_maxsize * max_msg_size`` bytes.

        Returns:
            WebSocketConnection: The open connection.

        Raises:
            ConnectionError: If the server refuses the upgrade or closes the connection during the handshake.
        """
        conn_opts = {**(conn_opts or {}), "max_msg_size": max_msg_size}
        urlparsed = http_parser.get_url_parsed(url)
        secured = ssl or (urlparsed.scheme == "wss")

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

        for k, v in base_headers.items():
            http_parser.validate_header(k, v)

        path = urlparsed.path or "/"
        if urlparsed.query:
            path = f"{path}?{urlparsed.query}"

        request = f"GET {path} HTTP/1.1{CRLF}"
        request += CRLF.join(f"{k}: {v}" for k, v in base_headers.items())
        request += CRLF * 2

        conn = await self.connector.acquire(urlparsed, verify, ssl, self.timeouts, False)
        conn.write(request.encode())
        await conn.writer.drain()

        try:
            ws_protocol = await self._read_handshake_response(conn, ws_key)
        except BaseException:
            conn.close()
            raise

        ws_conn = WebSocketConnection(conn, **conn_opts)
        ws_conn.subprotocol = ws_protocol

        if start_keepalive:
            ws_conn.start_keep_alive(interval=keepalive_interval)

        return ws_conn

    async def _read_handshake_response(self, conn, ws_key: str) -> Optional[str]:
        status_line = await conn.readline()
        if not status_line.startswith(b"HTTP/1.1 101"):
            raise ConnectionError(f"WebSocket upgrade failed: {status_line.decode()}")

        expected_key = base64.b64encode(hashlib.sha1(f"{ws_key}{WEBSOCKET_GUID}".encode()).digest()).decode()

        ws_protocol: Optional[str] = None
        while True:
            line = await conn.readline()
            if not line:
                raise ConnectionError("WebSocket upgrade failed: connection closed during the handshake")
            if line == CRLF.encode():
                break
            if line.startswith(b"Sec-WebSocket-Accept: "):
                received_key = line.decode().split(":", 1)[1].strip()
                if received_key != expected_key:
                    raise ConnectionError("Invalid WebSocket Accept key")
            elif line.startswith(b"Sec-WebSocket-Protocol:"):
                ws_protocol = line.decode().split(":", 1)[1].strip()
        return ws_protocol

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
