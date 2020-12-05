"""Fixtures and more."""

import asyncio
from datetime import datetime
from datetime import timedelta
import random
import gzip
from urllib.error import URLError
from urllib.request import urlopen
from http.client import RemoteDisconnected
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


async def hello_cookies(request):
    """Sample hello cookies."""
    res = 'Got cookies' if request.cookies else 'Hello, world'
    return web.Response(text=res, headers={
        'set-cookie': 'csrftoken=sometoken; expires=Sat, '
                       '04-Dec-2021 11:33:13 GMT; '
                       'Max-Age=31449600; Path=/'
    })


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
    if data:
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
    application.router.add_get('/cookies', hello_cookies)
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


@pytest.fixture(scope="session")
def http2_serv():
    """Sample aiohttp app."""
    port = __get_sample_port(3000, 4000)

    proc = subprocess.Popen(
        f"node tests/app.js {port}",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        shell=True
    )
    url = f'https://localhost:{port}/'

    __check_server(port)
    yield url
    proc.terminate()


def __is_port_in_use(port):
    try:
        urlopen(f'http://localhost:{port}/').getcode()
        return True
    except URLError as err:
        if isinstance(err.reason, ConnectionRefusedError):
            return False
    except RemoteDisconnected:
        return True


def __get_sample_port(_from, to):
    port = random.randint(_from, to)
    max_wait = datetime.utcnow() + timedelta(seconds=3)
    while __is_port_in_use(port):
        sleep(0.2)
        port = random.randint(_from, to)
        if datetime.utcnow() > max_wait:
            raise Exception('cannot find free port')
    return port


def __check_server(port):
    max_wait = datetime.utcnow() + timedelta(seconds=10)
    while not __is_port_in_use(port):
        sleep(0.2)
        if datetime.utcnow() > max_wait:
            raise Exception('cannot run node http2 server')
