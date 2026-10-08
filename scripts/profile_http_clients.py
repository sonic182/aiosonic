"""Compare fully read HTTP responses and optionally collect cProfile statistics.

Run with ``python -m scripts.profile_http_clients`` from the repository root.
Requires the same dependencies as ``scripts.performance``.
"""

import argparse
import asyncio
import cProfile
import json
import logging
import random
import statistics
import time
from typing import Dict, List

import aiohttp

import aiosonic
from aiosonic.connectors import TCPConnector
from aiosonic.pools import PoolConfig
from scripts.performance import ServerProcess


async def benchmark(kind: str, url: str, iterations: int, warmup: int, concurrency: int) -> float:
    """Measure requests with equal pool limits and fully consumed response bodies."""
    if kind == "aiohttp":
        client = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=concurrency))

        async def request() -> None:
            async with client.get(url) as response:
                if response.status != 200 or await response.read() != b"foo":
                    raise RuntimeError("unexpected benchmark response")
    else:
        client = aiosonic.HTTPClient(TCPConnector(pool_configs={":default": PoolConfig(size=concurrency)}))

        async def request() -> None:
            response = await client.get(url)
            if response.status_code != 200 or await response.content() != b"foo":
                raise RuntimeError("unexpected benchmark response")

    try:
        for _ in range(warmup):
            await request()
        start = time.perf_counter()
        await asyncio.gather(*(request() for _ in range(iterations)))
        return (time.perf_counter() - start) * 1000
    finally:
        if kind == "aiohttp":
            await client.close()
        else:
            await client.aclose()


async def compare(args: argparse.Namespace, url: str) -> Dict[str, List[float]]:
    """Alternate client order between rounds to reduce ordering bias."""
    results: Dict[str, List[float]] = {"aiosonic": [], "aiohttp": []}
    for round_number in range(args.rounds):
        kinds = [args.profile] if args.profile else list(results)
        if round_number % 2:
            kinds.reverse()
        for kind in kinds:
            elapsed = await benchmark(kind, url, args.iterations, args.warmup, args.concurrency)
            results[kind].append(elapsed)
    return {kind: times for kind, times in results.items() if times}


def main() -> None:
    """Run a local benchmark, optionally saving a cProfile data file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10000)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--profile", choices=["aiosonic", "aiohttp"])
    parser.add_argument("--output", default="http-client.prof")
    args = parser.parse_args()
    if min(args.iterations, args.concurrency, args.rounds) <= 0 or args.warmup < 0:
        parser.error("iterations, concurrency and rounds must be positive; warmup must be nonnegative")

    port = random.randint(10000, 60000)
    with ServerProcess(port):
        profiler = cProfile.Profile() if args.profile else None
        if profiler:
            profiler.enable()
        try:
            results = asyncio.run(compare(args, f"http://127.0.0.1:{port}"))
        finally:
            if profiler:
                profiler.disable()
                profiler.dump_stats(args.output)
        logging.getLogger(__name__).info(
            json.dumps(
                {kind: {"runs_ms": times, "median_ms": statistics.median(times)} for kind, times in results.items()},
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
