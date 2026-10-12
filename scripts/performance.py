"""Performance test."""

import argparse
import asyncio
import json
import logging
import random
import time
from concurrent import futures
from multiprocessing import Process
from shutil import which
from urllib.error import URLError
from urllib.request import urlopen

import aiohttp
import httpx
import requests
from uvicorn.main import Config, Server

import aiosonic
from aiosonic.connectors import TCPConnector
from aiosonic.httpx_client import AsyncClient
from aiosonic.pools import CyclicQueuePool, PoolConfig

try:
    import uvloop

    uvloop.install()
except ImportError:
    pass

# Configure logging to output to console.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


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
                [b"content-length", f"{len(res)}".encode()],
            ],
        }
    )
    await send({"type": "http.response.body", "body": res})


async def start_dummy_server(port):
    """Start dummy server."""
    config = Config(app, host="0.0.0.0", port=port, workers=2, log_level="warning")
    server = Server(config=config)
    await server.serve()


async def timeit_coro(func, *args, repeat=3000, warmup=100, **kwargs):
    """Measure the time taken for repeated asynchronous tasks.

    First, run a few warmup iterations to ensure connections/pools are ready.
    """
    logger.info(f"Warmup: Running {warmup} iterations for {func.__name__}")
    for _ in range(warmup):
        await func(*args, **kwargs)

    start = time.perf_counter()
    await asyncio.gather(*[func(*args, **kwargs) for _ in range(repeat)])
    end = time.perf_counter()
    elapsed = (end - start) * 1000  # Convert seconds to milliseconds
    logger.info(f"Finished {repeat} iterations for {func.__name__} in {elapsed:.2f} ms")
    return elapsed


async def performance_aiohttp(url, concurrency, repeat, warmup):
    """Test aiohttp performance."""
    logger.info(f"Starting aiohttp test with concurrency={concurrency}, repeat={repeat}, warmup={warmup}")
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=concurrency)) as session:
        return await timeit_coro(session.get, url, repeat=repeat, warmup=warmup)


async def performance_aiosonic(url, concurrency, pool_cls, timeouts, repeat, warmup):
    """Test aiosonic performance."""
    logger.info(f"Starting aiosonic test with concurrency={concurrency}, repeat={repeat}, warmup={warmup}")
    client = aiosonic.HTTPClient(
        TCPConnector(pool_configs={":default": PoolConfig(size=concurrency)}, pool_cls=pool_cls)
    )
    try:
        return await timeit_coro(client.get, url, timeouts=timeouts, repeat=repeat, warmup=warmup)
    finally:
        await client.aclose()


async def performance_aiosonic_httpx(url: str, concurrency: int, repeat: int, warmup: int) -> float:
    """Benchmark the HTTPX-compatible client with the same pool size as the native client."""
    connector = TCPConnector(pool_configs={":default": PoolConfig(size=concurrency)})
    native_client = aiosonic.HTTPClient(connector)
    try:
        async with AsyncClient(http_client=native_client) as client:
            return await timeit_coro(client.get, url, repeat=repeat, warmup=warmup)
    finally:
        await native_client.aclose()


async def performance_httpx(url, concurrency, repeat, warmup):
    """Test httpx performance."""
    logger.info(f"Starting httpx test with concurrency={concurrency}, repeat={repeat}, warmup={warmup}")
    async with httpx.AsyncClient() as client:
        return await timeit_coro(client.get, url, repeat=repeat, warmup=warmup)


def timeit_requests(url, concurrency, repeat, warmup):
    """Timeit requests using threads, with warmup iterations."""
    logger.info(f"Starting requests test with concurrency={concurrency}, repeat={repeat}, warmup={warmup}")
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=concurrency, pool_maxsize=concurrency)
    session.mount("http://", adapter)

    for _ in range(warmup):
        session.get(url)

    start = time.perf_counter()
    with futures.ThreadPoolExecutor(concurrency) as executor:
        tasks = [executor.submit(session.get, url) for _ in range(repeat)]
        for task in futures.as_completed(tasks):
            task.result()
    end = time.perf_counter()
    elapsed = (end - start) * 1000  # milliseconds
    logger.info(f"Finished {repeat} iterations for requests in {elapsed:.2f} ms")
    return elapsed


CLIENTS = ("aiohttp", "aiosonic", "aiosonic_httpx", "requests", "aiosonic_cyclic", "httpx")


async def do_tests(url, repeat, warmup, concurrency, clients=CLIENTS):
    """Start benchmark."""
    logger.info("Running performance tests...")
    runners = {
        "aiohttp": lambda: performance_aiohttp(url, concurrency, repeat, warmup),
        "aiosonic": lambda: performance_aiosonic(url, concurrency, None, None, repeat, warmup),
        "aiosonic_httpx": lambda: performance_aiosonic_httpx(url, concurrency, repeat, warmup),
        "aiosonic_cyclic": lambda: performance_aiosonic(url, concurrency, CyclicQueuePool, None, repeat, warmup),
        "httpx": lambda: performance_httpx(url, concurrency, repeat, warmup),
    }
    results = {}
    for name in clients:
        if name == "requests":
            results[name] = timeit_requests(url, concurrency, repeat, warmup)
            continue
        try:
            results[name] = await runners[name]()
        except Exception as exc:
            if name != "httpx":
                raise
            results["httpx_error"] = str(exc)
            logger.error(f"httpx encountered an error: {exc}")

    logger.info(
        json.dumps(
            {k: f"{repeat} requests in {v:.2f} ms" for k, v in results.items() if not k.endswith("_error")},
            indent=4,
        )
    )

    if "aiosonic" not in results:
        return results
    if "aiosonic_httpx" in results:
        logger.info(
            "HTTPX-compatible aiosonic client takes %.2f%% more time than native aiosonic",
            ((results["aiosonic_httpx"] / results["aiosonic"]) - 1) * 100,
        )
    for name, label in (
        ("httpx", "httpx"),
        ("aiohttp", "aiohttp"),
        ("requests", "requests"),
        ("aiosonic_cyclic", "aiosonic cyclic"),
    ):
        if name in results:
            logger.info(f"aiosonic is {((results[name] / results['aiosonic']) - 1) * 100:.2f}% faster than {label}")

    return results


def start_server(port):
    """Start server."""
    asyncio.run(start_dummy_server(port))


class ServerProcess:
    """Context manager to start and stop the server process."""

    def __init__(self, port):
        self.port = port
        self.process = None

    def __enter__(self):
        logger.info(f"Starting server on port {self.port}")
        self.process = Process(target=start_server, args=(self.port,))
        self.process.start()
        timeout = time.perf_counter() + 5
        url = f"http://127.0.0.1:{self.port}"
        while time.perf_counter() < timeout:
            try:
                with urlopen(url) as response:
                    response.read()
                    logger.info("Server is up and running")
                    return self
            except URLError:
                time.sleep(0.5)
        raise RuntimeError("Server did not start in time.")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.process:
            logger.info("Stopping server")
            self.process.terminate()
            self.process.join()


def main():
    """Start the performance test."""
    parser = argparse.ArgumentParser(description="Run performance tests for HTTP clients.")
    parser.add_argument(
        "--warmup",
        type=int,
        default=100,
        help="Number of warmup iterations (default: 100)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3000,
        help="Number of test iterations (default: 3000)",
    )
    parser.add_argument("--concurrency", type=int, default=25, help="Concurrency level (default: 25)")
    parser.add_argument(
        "--clients",
        nargs="+",
        choices=CLIENTS,
        default=list(CLIENTS),
        help="Clients to benchmark, in order (default: all)",
    )
    args = parser.parse_args()

    port = random.randint(1000, 9000)
    url = f"http://127.0.0.1:{port}"
    try:
        with ServerProcess(port):
            results = asyncio.run(
                do_tests(
                    url,
                    repeat=args.iterations,
                    warmup=args.warmup,
                    concurrency=args.concurrency,
                    clients=args.clients,
                )
            )
            timings = {k: v for k, v in results.items() if not k.endswith("_error")}
            fastest_client = min(timings, key=timings.get)
            logger.info(f"Fastest client: {fastest_client}")
    except Exception as exc:
        logger.error(f"Error during performance test: {exc}", exc_info=True)


if __name__ == "__main__":
    main()
