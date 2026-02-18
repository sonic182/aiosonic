"""Benchmark HTTP/1.1 pooling vs HTTP/2 multiplexing under synthetic latency."""

import argparse
import asyncio
import json
import logging
import random
import ssl
import subprocess
import time
from pathlib import Path
from shutil import which
from typing import Dict
from urllib.error import URLError
from urllib.request import urlopen

import aiosonic
from aiosonic.connectors import TCPConnector
from aiosonic.pools import PoolConfig
from aiosonic.timeout import Timeouts

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def is_tool(name: str) -> bool:
    """Check whether `name` is available in PATH."""
    return which(name) is not None


class NodeBenchmarkServer:
    """Context manager to run the local Node.js benchmark server."""

    def __init__(self, script_path: Path, port: int, min_delay_ms: int, max_delay_ms: int):
        self.script_path = script_path
        self.port = port
        self.min_delay_ms = min_delay_ms
        self.max_delay_ms = max_delay_ms
        self.process: subprocess.Popen | None = None

    def __enter__(self):
        cmd = [
            "node",
            str(self.script_path),
            "--port",
            str(self.port),
            "--min-delay-ms",
            str(self.min_delay_ms),
            "--max-delay-ms",
            str(self.max_delay_ms),
        ]
        self.process = subprocess.Popen(cmd)
        self._wait_until_ready()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)

    def _wait_until_ready(self):
        deadline = time.perf_counter() + 8
        url = f"https://127.0.0.1:{self.port}/health"
        ssl_ctx = ssl._create_unverified_context()
        while time.perf_counter() < deadline:
            try:
                with urlopen(url, context=ssl_ctx) as response:
                    if response.status == 200:
                        return
            except URLError:
                time.sleep(0.2)
        raise RuntimeError("Benchmark server did not start in time")


async def run_scenario(
    url: str,
    requests_count: int,
    task_concurrency: int,
    pool_size: int,
    http2: bool,
    sock_read_timeout: float,
    debug: bool = False,
) -> Dict[str, float | int | str]:
    """Run one benchmark scenario and return metrics."""
    connector = TCPConnector(pool_configs={":default": PoolConfig(size=pool_size)}, http2=http2)
    client = aiosonic.HTTPClient(connector=connector, http2=http2)
    limiter = asyncio.Semaphore(task_concurrency)
    version_counter: Dict[str, int] = {}
    completed = 0

    async def one_request(req_id: int) -> None:
        nonlocal completed
        async with limiter:
            if debug:
                logger.info("[%s] start request id=%s", "h2" if http2 else "h1", req_id)
            response = await client.get(
                url,
                verify=False,
                timeouts=Timeouts(sock_connect=5, sock_read=sock_read_timeout),
            )
            if response.status_code != 200:
                raise RuntimeError(f"Unexpected status code: {response.status_code}")
            version = response.http_version
            version_counter[version] = version_counter.get(version, 0) + 1
            completed += 1
            if debug:
                logger.info(
                    "[%s] done request id=%s version=%s completed=%s/%s",
                    "h2" if http2 else "h1",
                    req_id,
                    version,
                    completed,
                    requests_count,
                )

    start = time.perf_counter()
    tasks = [one_request(i) for i in range(requests_count)]
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start
    await connector.cleanup()

    return {
        "elapsed_seconds": elapsed,
        "throughput_rps": requests_count / elapsed,
        "requests": requests_count,
        "pool_size": pool_size,
        "http_version_counts": json.dumps(version_counter, sort_keys=True),
    }


async def benchmark(args):
    """Run both scenarios and print comparison."""
    url = f"https://127.0.0.1:{args.port}/infer"
    read_timeout = args.max_delay + 20

    logger.info("Scenario 1: HTTP/1.1 with pool size=%s", args.h1_pool_size)
    h1_result = await run_scenario(
        url=url,
        requests_count=args.requests,
        task_concurrency=args.task_concurrency,
        pool_size=args.h1_pool_size,
        http2=False,
        sock_read_timeout=read_timeout,
        debug=args.debug,
    )

    logger.info("Scenario 2: HTTP/2 with pool size=%s", args.h2_pool_size)
    h2_result = await run_scenario(
        url=url,
        requests_count=args.requests,
        task_concurrency=args.task_concurrency,
        pool_size=args.h2_pool_size,
        http2=True,
        sock_read_timeout=read_timeout,
        debug=args.debug,
    )

    h1_elapsed = float(h1_result["elapsed_seconds"])
    h2_elapsed = float(h2_result["elapsed_seconds"])
    improvement = ((h1_elapsed / h2_elapsed) - 1) * 100

    logger.info("--- Results ---")
    logger.info("HTTP/1.1: %s", json.dumps(h1_result, indent=2))
    logger.info("HTTP/2:   %s", json.dumps(h2_result, indent=2))
    logger.info("HTTP/2 speed improvement vs HTTP/1.1: %.2f%%", improvement)


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Benchmark HTTP/1.1 vs HTTP/2 under synthetic latency")
    parser.add_argument("--requests", type=int, default=1000, help="Total requests per scenario")
    parser.add_argument(
        "--task-concurrency",
        type=int,
        default=1000,
        help="Client task concurrency (pool still limits real open connections)",
    )
    parser.add_argument("--h1-pool-size", type=int, default=30, help="Pool size for HTTP/1.1 scenario")
    parser.add_argument("--h2-pool-size", type=int, default=2, help="Pool size for HTTP/2 scenario")
    parser.add_argument("--min-delay", type=int, default=5, help="Server min delay in seconds")
    parser.add_argument("--max-delay", type=int, default=15, help="Server max delay in seconds")
    parser.add_argument("--port", type=int, default=random.randint(9001, 14000), help="Server port")
    parser.add_argument("--debug", action="store_true", help="Enable verbose benchmark and aiosonic logs")
    return parser.parse_args()


def main():
    """Run benchmark."""
    if not is_tool("node"):
        raise RuntimeError("Node.js is required. Install it first (e.g. brew install node).")

    args = parse_args()
    if args.debug:
        logging.getLogger("aiosonic").setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    if args.min_delay <= 0 or args.max_delay < args.min_delay:
        raise ValueError("Invalid delay bounds")

    repo_root = Path(__file__).resolve().parent.parent
    node_script = repo_root / "scripts" / "http_benchmark_server.mjs"
    if not node_script.exists():
        raise FileNotFoundError(f"Missing server script: {node_script}")

    with NodeBenchmarkServer(
        script_path=node_script,
        port=args.port,
        min_delay_ms=args.min_delay * 1000,
        max_delay_ms=args.max_delay * 1000,
    ):
        asyncio.run(benchmark(args))


if __name__ == "__main__":
    main()
