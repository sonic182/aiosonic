"""Performance test."""

import asyncio
from concurrent import futures
from datetime import datetime
from datetime import timedelta
import json
import random
from time import sleep

from urllib.request import urlopen
from urllib.error import URLError

from multiprocessing import Process

from uvicorn.main import Server
from uvicorn.main import Config

import aiohttp
import httpx
import requests

import aiosonic
from aiosonic.connectors import TCPConnector
from aiosonic.pools import CyclicQueuePool

try:
    import uvloop
    uvloop.install()
except Exception:
    pass


async def app(scope, receive, send):
    assert scope['type'] == 'http'
    res = b'foo'
    await send({
        'type':
        'http.response.start',
        'status':
        200,
        'headers': [
            [b'content-type', b'text/plain'],
            [b'content-length', b'%d' % len(res)],
        ]
    })
    await send({
        'type': 'http.response.body',
        'body': res,
    })


async def start_dummy_server(loop, port):
    """Start dummy server."""
    host = '0.0.0.0'

    config = Config(app, host=host, port=port, workers=2, log_level='warning')
    server = Server(config=config)

    await server.serve()


async def timeit_coro(func, *args, **kwargs):
    """To time stuffs."""
    repeat = kwargs.pop('repeat', 1000)
    before = datetime.now()
    # Concurrent coroutines
    await asyncio.gather(*[func(*args, **kwargs) for _ in range(repeat)])
    after = datetime.now()
    return (after - before) / timedelta(milliseconds=1)


async def performance_aiohttp(url, concurrency):
    """Test aiohttp performance."""
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(
            limit=concurrency)) as session:
        return await timeit_coro(session.get, (url))


async def performance_aiosonic(url, concurrency, pool_cls=None, timeouts=None):
    """Test aiohttp performance."""
    client = aiosonic.HTTPClient(
        TCPConnector(pool_size=concurrency, pool_cls=pool_cls))
    return await timeit_coro(client.get,
                             url,
                             timeouts=timeouts)


async def performance_httpx(url, concurrency, pool_cls=None):
    """Test aiohttp performance."""
    async with httpx.AsyncClient() as client:
        return await timeit_coro(client.get, url)


def timeit_requests(url, concurrency, repeat=1000):
    """Timeit requests."""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=concurrency,
                                            pool_maxsize=concurrency)
    session.mount('http://', adapter)
    with futures.ThreadPoolExecutor(concurrency) as executor:
        to_wait = []
        before = datetime.now()
        for _ in range(repeat):
            to_wait.append(executor.submit(session.get, url))
        for fut in to_wait:
            fut.result()
        after = datetime.now()
    return (after - before) / timedelta(milliseconds=1)


def do_tests(url):
    """Start benchmark."""
    print('doing tests...')
    concurrency = 25
    loop = asyncio.get_event_loop()

    # aiohttp
    res1 = loop.run_until_complete(performance_aiohttp(url, concurrency))

    # aiosonic
    res2 = loop.run_until_complete(performance_aiosonic(url, concurrency))

    # requests
    res3 = timeit_requests(url, concurrency)

    # aiosonic cyclic
    res4 = loop.run_until_complete(
        performance_aiosonic(url, concurrency, pool_cls=CyclicQueuePool))

    # httpx
    httpx_exc = False
    res5 = None
    try:
        res5 = loop.run_until_complete(performance_httpx(url, concurrency))
    except Exception as exc:
        httpx_exc = exc
        print('httpx did break with: ' + str(exc))

    to_print = {
        'aiosonic': '1000 requests in %.2f ms' % res2,
        'aiosonic cyclic': '1000 requests in %.2f ms' % res4,
        'aiohttp': '1000 requests in %.2f ms' % res1,
        'requests': '1000 requests in %.2f ms' % res3,
    }

    if not httpx_exc:
        to_print.update({'httpx': '1000 requests in %.2f ms' % res5})

    print(json.dumps(to_print, indent=True))

    print('aiosonic is %.2f%% faster than aiohttp' %
          (((res1 / res2) - 1) * 100))
    print('aiosonic is %.2f%% faster than requests' %
          (((res3 / res2) - 1) * 100))
    print('aiosonic is %.2f%% faster than aiosonic cyclic' %
          (((res4 / res2) - 1) * 100))

    res = [
        ['aiohttp', res1],
        ['aiosonic', res2],
        ['requests', res3],
        ['aiosonic_cyclic', res4],
    ]

    if not httpx_exc:
        print('aiosonic is %.2f%% faster than httpx' %
              (((res5 / res2) - 1) * 100))
        res.append(['httpx', res5])

    return res


def start_server(port):
    """Start server."""
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_dummy_server(loop, port))


def main():
    """Start."""
    port = random.randint(1000, 9000)
    url = 'http://0.0.0.0:%d' % port
    process = Process(target=start_server, args=(port, ))
    process.start()

    max_wait = datetime.now() + timedelta(seconds=5)
    while True:
        try:
            with urlopen(url) as response:
                response.read()
                break
        except URLError:
            sleep(1)
            if datetime.now() > max_wait:
                raise
    try:
        res = do_tests(url)
        assert 'aiosonic' in sorted(res, key=lambda x: x[1])[0][0]
    finally:
        process.terminate()


if __name__ == '__main__':
    main()
