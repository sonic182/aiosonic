"""Fixtures and more."""

import asyncio
import datetime
import gzip
import random
import shlex
import ssl
import subprocess
import sys
import zlib
from time import sleep

import aiohttp
import pytest
from aiohttp import web

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
        return subprocess.Popen(command, shell=True)
    else:
        return subprocess.Popen(shlex.split(command))


async def hello(request):
    """Sample router."""
    if "foo" in request.query:
        return web.Response(text=request.query["foo"])
    return web.Response(text="Hello, world")


async def hello_cookies(request):
    """Sample hello cookies."""
    res = "Got cookies" if request.cookies else "Hello, world"
    return web.Response(
        text=res,
        headers={
            "set-cookie": "csrftoken=sometoken; expires=Sat, "
            "04-Dec-2021 11:33:13 GMT; Max-Age=31449600; Path=/"
        },
    )


async def hello_gzip(request):
    """Sample router."""
    headers = {"Content-encoding": "gzip"}
    return web.Response(body=gzip.compress(b"Hello, world"), headers=headers)


async def hello_deflate(request):
    """Sample router."""
    headers = {"Content-encoding": "deflate"}
    return web.Response(body=zlib.compress(b"Hello, world"), headers=headers)


async def hello_post(request):
    """Sample router."""
    post = await request.post()
    if post and "foo" in post:
        return web.Response(text=post["foo"])

    # read request body, chunked requests too
    data = await request.text()

    if data and "close" in data:
        res = web.Response(text=data)
        res.force_close()
        return res
    if data:
        return web.Response(text=data)
    return web.Response(text="Hello, world")


async def hello_post_json(request):
    """Sample router."""
    data = await request.json()
    if data and "foo" in data:
        return web.Response(text=data["foo"])
    return web.Response(text="Hello, world")


async def delete_handler(request):
    """Sample delete method."""
    return web.Response(text="deleted")


async def put_patch_handler(request):
    """Sample put/patch method."""
    return web.Response(text="put_patch")


async def chunked_response(request):
    """Chunked transfer-encoding."""
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={"Content-Type": "text/plain"},
    )
    await response.prepare(request)
    await response.write(b"foo")
    await response.write(b"bar")
    await response.write_eof()
    return response


async def do_redirect(request):
    """Sample router."""
    raise web.HTTPFound("/")


async def do_redirect_full_url(request: aiohttp.web.Request):
    """Sample router."""
    url = "{}://{}/".format(request.scheme, request.host)
    raise web.HTTPFound(url)


async def max_redirects(request):
    """Sample router."""
    raise web.HTTPFound("/max_redirects")


async def slow_request(request):
    """Sample router."""
    await asyncio.sleep(1)
    return web.Response(text="foo")


def get_app():
    """Get aiohttp app."""
    application = web.Application()
    application.router.add_get("/", hello)
    application.router.add_get("/cookies", hello_cookies)
    application.router.add_get("/get_redirect", do_redirect)
    application.router.add_get("/get_redirect_full", do_redirect_full_url)
    application.router.add_get("/max_redirects", max_redirects)
    application.router.add_get("/gzip", hello_gzip)
    application.router.add_get("/deflate", hello_deflate)
    application.router.add_get("/chunked", chunked_response)
    application.router.add_get("/slow_request", slow_request)
    application.router.add_post("/post", hello_post)
    application.router.add_post("/post_json", hello_post_json)
    application.router.add_put("/put_patch", put_patch_handler)
    application.router.add_patch("/put_patch", put_patch_handler)
    application.router.add_delete("/delete", delete_handler)
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
    """Sample HTTP/2 app."""
    port = __get_sample_port(3000, 4000)
    proc = run_cmd(f"node tests/nodeapps/http2.js {port}")
    url = f"https://localhost:{port}"
    check_port(port)
    yield url
    proc.terminate()


@pytest.fixture(scope="session")
def http_serv():
    """Sample HTTP/1 app."""
    port = __get_sample_port(3000, 4000)
    proc = run_cmd(f"node tests/nodeapps/http1.mjs {port}")
    url = f"http://localhost:{port}"
    check_port(port)
    yield url
    proc.terminate()


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


@pytest.fixture(scope="session")
def ws_serv():
    """Sample WebSocket app (non-SSL)."""
    port = __get_sample_port(3000, 4000)
    proc = run_cmd(f"node tests/nodeapps/ws-server.mjs {port}")
    url = f"ws://localhost:{port}"
    check_port(port)
    yield url
    proc.terminate()


@pytest.fixture(scope="session")
def ws_serv_ssl():
    """Sample secure WebSocket app (SSL)."""
    port = __get_sample_port(3000, 4000)
    proc = run_cmd(f"node tests/nodeapps/ws-server.mjs {port} ssl")
    url = f"wss://localhost:{port}"
    check_port(port)
    yield url
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
