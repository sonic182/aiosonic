"""Fixtures and more."""

import asyncio
from datetime import datetime
from datetime import timedelta
import random
import gzip
import socket
import signal
import ssl
import subprocess
from time import sleep
import zlib

import aiohttp
from aiohttp import web
import pytest


async def hello(request):
    """Sample router."""
    if 'foo' in request.query:
        return web.Response(text=request.query['foo'])
    return web.Response(text='Hello, world')


async def hello_gzip(request):
    """Sample router."""
    headers = {'Content-encoding': 'gzip'}
    return web.Response(body=gzip.compress(b'Hello, world'), headers=headers)


async def hello_deflate(request):
    """Sample router."""
    headers = {'Content-encoding': 'deflate'}
    return web.Response(body=zlib.compress(b'Hello, world'), headers=headers)


async def hello_post(request):
    """Sample router."""
    post = await request.post()
    if post and 'foo' in post:
        return web.Response(text=post['foo'])

    # read request body, chunked requests too
    data = await request.text()

    if data and 'close' in data:
        res = web.Response(text=data)
        res.force_close()
        return res
    elif data:
        return web.Response(text=data)
    return web.Response(text='Hello, world')


async def hello_post_json(request):
    """Sample router."""
    data = await request.json()
    if data and 'foo' in data:
        return web.Response(text=data['foo'])
    return web.Response(text='Hello, world')


async def delete_handler(request):
    """Sample delete method."""
    return web.Response(text='deleted')


async def put_patch_handler(request):
    """Sample delete method."""
    return web.Response(text='put_patch')


async def chunked_response(request):
    """Chunked transfer-encoding."""
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={'Content-Type': 'text/plain'},
    )
    # response.enable_chunked_encoding()
    await response.prepare(request)
    await response.write(b'foo')
    await response.write(b'bar')

    await response.write_eof()
    return response


async def do_redirect(request):
    """Sample router."""
    raise web.HTTPFound('/')


async def do_redirect_full_url(request: aiohttp.web.Request):
    """Sample router."""
    url = '{}://{}/'.format(request.scheme, request.host)
    raise web.HTTPFound(url)


async def max_redirects(request):
    """Sample router."""
    raise web.HTTPFound('/max_redirects')


async def slow_request(request):
    """Sample router."""
    await asyncio.sleep(1)
    return web.Response(text='foo')


def get_app():
    """Get aiohttp app."""
    application = web.Application()
    application.router.add_get('/', hello)
    application.router.add_get('/get_redirect', do_redirect)
    application.router.add_get('/get_redirect_full', do_redirect_full_url)
    application.router.add_get('/max_redirects', max_redirects)
    application.router.add_get('/gzip', hello_gzip)
    application.router.add_get('/deflate', hello_deflate)
    application.router.add_get('/chunked', chunked_response)
    application.router.add_get('/slow_request', slow_request)
    application.router.add_post('/post', hello_post)
    application.router.add_post('/post_json', hello_post_json)
    application.router.add_put('/put_patch', put_patch_handler)
    application.router.add_patch('/put_patch', put_patch_handler)
    application.router.add_delete('/delete', delete_handler)
    return application


@pytest.fixture
def app():
    """Sample aiohttp app."""
    return get_app()


@pytest.fixture
def ssl_context():
    # python 3.5 compatibility
    context = ssl.SSLContext(
        getattr(ssl, 'PROTOCOL_TLS_SERVER', ssl.PROTOCOL_TLS))
    context.load_cert_chain('tests/files/certs/server.cert',
                            'tests/files/certs/server.key')
    return context


@pytest.fixture
def http2_serv():
    """Sample aiohttp app."""
    port = random.randint(3000, 4000)

    kwargs = dict(
        stdin=subprocess.PIPE,
        shell=True)

    proc = subprocess.Popen(f"node tests/app.js {port}", **kwargs)
    url = f'https://localhost:{port}/'

    # This restores the same behavior as before.
    max_wait = datetime.utcnow() + timedelta(seconds=3)
    while not __is_port_in_use(port):
        sleep(0.2)
        if datetime.utcnow() > max_wait:
            raise Exception('cannot run node http2 server')
    yield url
    proc.send_signal(signal.SIGINT)
    proc.terminate()


def __is_port_in_use(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result_of_check = sock.connect_ex(("localhost", port))
    return result_of_check == 0
