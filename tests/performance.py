"""Performance test."""

import asyncio
import json
import random
import shlex
import subprocess
from concurrent import futures
from datetime import datetime, timedelta
from multiprocessing import Process
from shutil import which
from time import sleep
from urllib.error import URLError
from urllib.request import urlopen

import aiohttp
import httpx
import requests
from uvicorn.main import Config, Server

import aiosonic
from aiosonic.connectors import TCPConnector
from aiosonic.pools import CyclicQueuePool

try:
    import uvloop

    uvloop.install()
except ImportError:
    pass


def is_tool(name):
    """Check whether `name` is on PATH and marked as executable."""
    return which(name) is not None


async def app(scope, receive, send):
    """Simple ASGI app."""
    assert scope["type"] == "http"
    res = b"foo"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/plain"],
                [b"content-length", b"%d" % len(res)],
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": res,
        }
    )


async def start_dummy_server(port):
    """Start dummy server."""
    config = Config(app, host="0.0.0.0", port=port, workers=2, log_level="warning")
    server = Server(config=config)
    await server.serve()


async def timeit_coro(func, *args, repeat=1000, **kwargs):
    """Measure the time taken for repeated asynchronous tasks."""
    before = datetime.now()
    await asyncio.gather(*[func(*args, **kwargs) for _ in range(repeat)])
    after = datetime.now()
    return (after - before) / timedelta(milliseconds=1)


async def performance_aiohttp(url, concurrency):
    """Test aiohttp performance."""
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=concurrency)
    ) as session:
        return await timeit_coro(session.get, url)


async def performance_aiosonic(url, concurrency, pool_cls=None, timeouts=None):
    """Test aiosonic performance."""
    client = aiosonic.HTTPClient(TCPConnector(pool_size=concurrency, pool_cls=pool_cls))
    return await timeit_coro(client.get, url, timeouts=timeouts)


async def performance_httpx(url, concurrency):
    """Test httpx performance."""
    async with httpx.AsyncClient() as client:
        return await timeit_coro(client.get, url)


def timeit_requests(url, concurrency, repeat=1000):
    """Timeit requests."""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=concurrency, pool_maxsize=concurrency
    )
    session.mount("http://", adapter)
    with futures.ThreadPoolExecutor(concurrency) as executor:
        futures_list = [executor.submit(session.get, url) for _ in range(repeat)]
        before = datetime.now()
        for fut in futures.as_completed(futures_list):
            fut.result()
        after = datetime.now()
    return (after - before) / timedelta(milliseconds=1)


async def do_tests(url):
    """Start benchmark."""
    print("Running performance tests...")
    concurrency = 25

    results = {}

    results["aiohttp"] = await performance_aiohttp(url, concurrency)
    results["aiosonic"] = await performance_aiosonic(url, concurrency)
    results["requests"] = timeit_requests(url, concurrency)
    results["aiosonic_cyclic"] = await performance_aiosonic(
        url, concurrency, pool_cls=CyclicQueuePool
    )

    try:
        results["httpx"] = await performance_httpx(url, concurrency)
    except Exception as exc:
        # results["httpx_error"] = str(exc)
        print(f"httpx encountered an error: {exc}")

    print(
        json.dumps(
            {
                k: f"1000 requests in {v:.2f} ms"
                for k, v in results.items()
                if not k.endswith("_error")
            },
            indent=4,
        )
    )

    if "httpx" in results:
        print(
            f"aiosonic is {((results['httpx'] / results['aiosonic']) - 1) * 100:.2f}% faster than httpx"
        )

    print(
        f"aiosonic is {((results['aiohttp'] / results['aiosonic']) - 1) * 100:.2f}% faster than aiohttp"
    )
    print(
        f"aiosonic is {((results['requests'] / results['aiosonic']) - 1) * 100:.2f}% faster than requests"
    )
    print(
        f"aiosonic is {((results['aiosonic_cyclic'] / results['aiosonic']) - 1) * 100:.2f}% faster than aiosonic cyclic"
    )

    return results


def start_server(port):
    """Start server."""
    if is_tool("node"):
        asyncio.run(start_dummy_server(port))
    else:
        subprocess.Popen(shlex.split(f"node tests/app.js {port}"))


def main():
    """Start the performance test."""
    port = random.randint(1000, 9000)
    url = f"http://0.0.0.0:{port}"
    process = Process(target=start_server, args=(port,))
    process.start()

    max_wait = datetime.now() + timedelta(seconds=5)
    while datetime.now() < max_wait:
        try:
            with urlopen(url) as response:
                response.read()
                break
        except URLError:
            sleep(1)
    else:
        print("Server did not start in time.")
        process.terminate()
        return

    try:
        res = asyncio.run(do_tests(url))

        # Check if any results are valid and proceed
        fastest_client = sorted(res.items(), key=lambda x: x[1])[0][0]
        assert "aiosonic" in fastest_client

    finally:
        process.terminate()


if __name__ == "__main__":
    main()
