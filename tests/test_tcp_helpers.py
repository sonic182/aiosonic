import socket
from unittest.mock import MagicMock

from aiosonic.tcp_helpers import tcp_keepalive, tcp_nodelay


def test_tcp_keepalive_none_sock():
    tcp_keepalive(None)  # type: ignore[arg-type]


def test_tcp_keepalive_real_sock():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        tcp_keepalive(sock)
    finally:
        sock.close()


def test_tcp_nodelay_none_sock():
    tcp_nodelay(None, True)  # type: ignore[arg-type]


def test_tcp_nodelay_unsupported_family():
    sock = MagicMock()
    sock.family = socket.AF_UNIX if hasattr(socket, "AF_UNIX") else 1
    tcp_nodelay(sock, True)
    sock.setsockopt.assert_not_called()


def test_tcp_nodelay_valid_sock():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        tcp_nodelay(sock, True)
        tcp_nodelay(sock, False)
    finally:
        sock.close()


def test_tcp_nodelay_oserror_suppressed():
    sock = MagicMock()
    sock.family = socket.AF_INET
    sock.setsockopt.side_effect = OSError("closed")
    tcp_nodelay(sock, True)
