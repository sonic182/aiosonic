

import pytest
from aiohttp import web


async def hello(_request):
    """Sample router."""
    return web.Response(text='Hello, world')


@pytest.fixture
def app():
    """Sample aiohttp app."""
    application = web.Application()
    application.router.add_get('/', hello)
    return application
