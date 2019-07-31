"""Fixtures and more."""

import ssl

from aiohttp import web
import pytest


async def hello(request):
    """Sample router."""
    headers = {'Connection': 'keep-alive'}
    if 'foo' in request.query:
        return web.Response(text=request.query['foo'], headers=headers)
    return web.Response(text='Hello, world', headers=headers)


async def hello_post(request):
    """Sample router."""
    post = await request.post()
    if post and 'foo' in post:
        return web.Response(text=post['foo'])
    return web.Response(text='Hello, world')


async def hello_post_json(request):
    """Sample router."""
    data = await request.json()
    if data and 'foo' in data:
        return web.Response(text=data['foo'])
    return web.Response(text='Hello, world')


@pytest.fixture
def app():
    """Sample aiohttp app."""
    application = web.Application()
    application.router.add_get('/', hello)
    application.router.add_post('/post', hello_post)
    application.router.add_post('/post_json', hello_post_json)
    return application


@pytest.fixture
def ssl_context():
    # context = ssl.create_default_context()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(
        'tests/files/certs/server.cert',
        'tests/files/certs/server.key'
    )
    return context
