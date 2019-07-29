

import pytest
from aiohttp import web


async def hello(request):
    """Sample router."""
    if 'foo' in request.query:
        return web.Response(text=request.query['foo'])
    return web.Response(text='Hello, world')


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
