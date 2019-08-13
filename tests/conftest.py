"""Fixtures and more."""

import ssl

from aiohttp import web
import gzip
import zlib

import pytest


async def hello(request):
    """Sample router."""
    if 'foo' in request.query:
        return web.Response(text=request.query['foo'])
    return web.Response(text='Hello, world')


async def hello_gzip(request):
    """Sample router."""
    headers = {
        'Content-encoding': 'gzip'
    }
    return web.Response(
        body=gzip.compress(b'Hello, world'),
        headers=headers
    )


async def hello_deflate(request):
    """Sample router."""
    headers = {
        'Content-encoding': 'deflate'
    }
    return web.Response(
        body=zlib.compress(b'Hello, world'),
        headers=headers
    )


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


def get_app():
    """Get aiohttp app."""
    application = web.Application()
    application.router.add_get('/', hello)
    application.router.add_get('/gzip', hello_gzip)
    application.router.add_get('/deflate', hello_deflate)
    application.router.add_get('/chunked', chunked_response)
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
    context.load_cert_chain(
        'tests/files/certs/server.cert',
        'tests/files/certs/server.key'
    )
    return context
