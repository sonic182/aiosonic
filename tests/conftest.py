

import pytest
from aiohttp import web


async def hello(request):
    """Sample router."""
    if 'foo' in request.query:
        return web.Response(text=request.query['foo'])
    return web.Response(text='Hello, world')


async def hello_post(_request):
    """Sample router."""
    print(_request.POST)
    return web.Response(text='Hello, world')


@pytest.fixture
def app():
    """Sample aiohttp app."""
    application = web.Application()
    application.router.add_get('/', hello)
    application.router.add_get('/post', hello_post)
    return application
