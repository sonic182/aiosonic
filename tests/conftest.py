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
from aiohttp import web

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def hello(request):
    """Sample router."""
    if "foo" in request.query:
        return web.Response(text=request.query["foo"])
    return web.Response(text="Hello, world")


def get_app():
    """Get aiohttp app."""
    application = web.Application()
    # Only the "/" route remains.
    application.router.add_get("/", hello)
    return application


@pytest.fixture
def app():
    """Sample aiohttp app."""
    return get_app()


@pytest.fixture
def ssl_context():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS)
    context.load_cert_chain(
        "tests/files/certs/server.cert", "tests/files/certs/server.key"
    )
    return context


@pytest.fixture(scope="session")
def http2_serv():
    """Sample aiohttp app."""
    port = __get_sample_port(3000, 4000)

    proc = subprocess.Popen(shlex.split(f"node tests/nodeapps/http2.js {port}"))
    url = f"https://localhost:{port}"

    check_port(port)
    yield url
    proc.terminate()


@pytest.fixture(scope="session")
def http_serv():
    """Sample http app."""
    port = __get_sample_port(3000, 4000)

    proc = subprocess.Popen(shlex.split(f"node tests/nodeapps/http1.mjs {port}"))
    url = f"http://localhost:{port}"

    check_port(port)
    yield url
    proc.terminate()


@pytest.fixture(scope="session")
def http_serv_new():
    """Sample http app."""
    port = __get_sample_port(3000, 4000)

    proc = subprocess.Popen(shlex.split(f"node tests/nodeapps/basic.js {port}"))
    url = f"http://localhost:{port}"

    check_port(port)
    yield url
    proc.terminate()


@pytest.fixture(scope="session")
def proxy_serv():
    """Sample aiohttp app."""
    port = __get_sample_port(8000, 9000)
    auth = "user:password"
    command = f"proxy --basic-auth {auth} --hostname 127.0.0.1 --port {port}"
    proc = subprocess.Popen(shlex.split(command))
    url = f"http://127.0.0.1:{port}"

    check_port(port, "127.0.0.1")
    yield (url, auth)
    proc.terminate()


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
    """Check port if it is listening something."""
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
