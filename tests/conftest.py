"""Fixtures and more."""

import asyncio
import datetime
import random
import shlex
import ssl
import subprocess
import sys
from time import sleep

import pytest

# On Windows, use the WindowsSelectorEventLoopPolicy.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def run_cmd(command: str):
    """
    Helper to run a command.
    On Windows, use shell=True so that commands like 'npm' or 'node' are resolved via PATH.
    On other systems, split the command.
    """
    if sys.platform == "win32":
        return subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    else:
        return subprocess.Popen(
            shlex.split(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )


@pytest.fixture
def ssl_context():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS)
    context.load_cert_chain(
        "tests/files/certs/server.cert", "tests/files/certs/server.key"
    )
    return context


@pytest.fixture(scope="session")
def http2_serv():
    """Sample HTTP/2 app."""
    port = __get_sample_port(3000, 4000)
    proc = run_cmd(f"node tests/nodeapps/http2.js {port}")
    url = f"https://localhost:{port}"
    check_port(port)
    yield url
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def http_serv():
    """Sample HTTP/1 app."""
    port = __get_sample_port(3000, 4000)
    proc = run_cmd(f"node tests/nodeapps/http1.mjs {port}")
    url = f"http://localhost:{port}"
    check_port(port)
    yield url
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def proxy_serv():
    """Sample proxy app."""
    port = __get_sample_port(8000, 9000)
    auth = "user:password"
    command = f"proxy --basic-auth {auth} --hostname 127.0.0.1 --port {port}"
    proc = run_cmd(command)
    url = f"http://127.0.0.1:{port}"
    check_port(port, "127.0.0.1")
    yield (url, auth)
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def sse_serv():
    """Sample SSE app."""
    port = __get_sample_port(3000, 4000)
    proc = run_cmd(f"node tests/nodeapps/sse-server.mjs {port} /sse")
    url = f"http://localhost:{port}/sse"
    check_port(port)
    yield url
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def sse_serv_reconnect():
    """Sample SSE app for reconnection tests."""
    port = __get_sample_port(3000, 4000)
    proc = run_cmd(f"node tests/nodeapps/sse-server.mjs {port} /sse-reconnect")
    url = f"http://localhost:{port}/sse-reconnect"
    check_port(port)
    yield url
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def sse_serv_malformed():
    """Sample SSE app for malformed events."""
    port = __get_sample_port(3000, 4000)
    proc = run_cmd(f"node tests/nodeapps/sse-server.mjs {port} /sse-malformed")
    url = f"http://localhost:{port}/sse-malformed"
    check_port(port)
    yield url
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def ws_serv():
    """Sample WebSocket app (non-SSL)."""
    port = __get_sample_port(3000, 4000)
    proc = run_cmd(f"node tests/nodeapps/ws-server.mjs {port}")
    url = f"ws://localhost:{port}"
    check_port(port)
    yield url
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def ws_serv_ssl():
    """Sample secure WebSocket app (SSL)."""
    port = __get_sample_port(3000, 4000)
    proc = run_cmd(f"node tests/nodeapps/ws-server.mjs {port} ssl")
    url = f"wss://localhost:{port}"
    check_port(port)
    yield url
    proc.terminate()
    proc.wait(timeout=5)


def __is_port_in_use(address, port):
    import socket

    s = socket.socket()
    try:
        s.connect((address, port))
        return True
    except socket.error:
        return False
    finally:
        s.close()


def __get_sample_port(_from, to):
    port = random.randint(_from, to)
    max_wait = utcnow() + datetime.timedelta(seconds=3)
    while __is_port_in_use("localhost", port):
        sleep(0.2)
        port = random.randint(_from, to)
        if utcnow() > max_wait:
            raise Exception("cannot find free port")
    return port


def check_port(port, hostname="localhost", timeout_seconds=10):
    """Check if a port is listening."""
    max_wait = utcnow() + datetime.timedelta(seconds=timeout_seconds)
    while not __is_port_in_use(hostname, port):
        sleep(0.2)
        if utcnow() > max_wait:
            raise Exception(f"port {port} never got active.")


def utcnow():
    if sys.version_info >= (3, 11):
        return datetime.datetime.now(datetime.UTC)
    else:
        return datetime.datetime.utcnow()
