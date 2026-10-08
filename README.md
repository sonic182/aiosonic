![github status](https://github.com/sonic182/aiosonic/actions/workflows/python.yml/badge.svg)
[![PyPI version](https://badge.fury.io/py/aiosonic.svg)](https://badge.fury.io/py/aiosonic)
[![Documentation Status](https://readthedocs.org/projects/aiosonic/badge/?version=latest)](https://aiosonic.readthedocs.io/en/latest/?badge=latest)

![aiosonic banner](https://raw.githubusercontent.com/sonic182/aiosonic/master/assets/aiosonic-banner.png)

# aiosonic - lightweight Python asyncio HTTP/WebSocket client

A very fast, lightweight Python asyncio HTTP/1.1, HTTP/2, and WebSocket client.


The repository is hosted on [GitHub](https://github.com/sonic182/aiosonic).

For full documentation, please see [aiosonic docs](https://aiosonic.readthedocs.io/en/latest/).

## Features

- Keepalive support and smart pool of connections
- Multipart file uploads
- Handling of chunked responses and requests
- Connection timeouts and automatic decompression
- Automatic redirect following
- Fully type-annotated
- WebSocket support
- HTTP proxy support
- Sessions with cookie persistence
- Elegant key/value cookies
- Comprehensive test coverage
- HTTP/2 (enabled with a flag)
- Authentication by host, event hooks, `raise_for_status()` and response streaming

## Requirements

- Python >= 3.10 (or PyPy 3.11+)

## Installation

```bash
pip install aiosonic
```

## Getting Started

Below is an example demonstrating basic HTTP client usage:

```python
import asyncio
import aiosonic
import json

async def run():
    client = aiosonic.HTTPClient()

    # Sample GET request
    response = await client.get('https://www.google.com/')
    assert response.status_code == 200
    assert 'Google' in (await response.text())

    # POST data as URL-encoded form
    url = "https://postman-echo.com/post"
    posted_data = {'foo': 'bar'}
    response = await client.post(url, data=posted_data)
    assert response.status_code == 200
    data = json.loads(await response.content())
    assert data['form'] == posted_data

    # POST data as JSON
    response = await client.post(url, json=posted_data)
    assert response.status_code == 200
    data = json.loads(await response.content())
    assert data['json'] == posted_data

    # GET request with timeouts
    from aiosonic.timeout import Timeouts
    timeouts = Timeouts(sock_read=10, sock_connect=3)
    response = await client.get('https://www.google.com/', timeouts=timeouts)
    assert response.status_code == 200
    assert 'Google' in (await response.text())

    print('HTTP client success')

if __name__ == '__main__':
    asyncio.run(run())
```

Native ``HTTPClient`` context managers do not close the connector; call `await client.aclose()`
when finished, after consuming or closing all responses. The HTTPX-compatible `AsyncClient`
closes its owned client when its context manager exits.

## HTTPX-like Client

Use `AsyncClient` for an HTTPX-style API, including synchronous response methods:

> **Performance:** This compatibility layer adds overhead compared with using `aiosonic.HTTPClient` directly.
> In a local five-round benchmark (5,000 requests per round, pool size 25), its median time was about 5% longer
> than the native client (805 ms vs 769 ms). Results depend on the machine and workload;
> prefer the native client for performance-sensitive workloads.

```python
import asyncio
from aiosonic.httpx_client import AsyncClient


async def main():
    async with AsyncClient(base_url="https://api.github.com", timeout=10.0) as client:
        response = await client.get("/users/sonic182")
        response.raise_for_status()
        print(response.json())


asyncio.run(main())
```

## WebSocket Usage

Below is an example demonstrating how to use aiosonic's WebSocket support:

```python
import asyncio
from aiosonic import WebSocketClient

async def main():
    # Replace with your WebSocket server URL
    ws_url = "ws://localhost:8080"
    async with WebSocketClient() as client:
        async with await client.connect(ws_url) as ws:
            # Send a text message
            await ws.send_text("Hello WebSocket")
            
            # Receive an echo response
            response = await ws.receive_text()
            print("Received:", response)
            
            # Send a ping and wait for the pong
            await ws.ping(b"keep-alive")
            pong = await ws.receive_pong()
            print("Pong received:", pong)

            # You can have a "reader" task like this:
            async def ws_reader(conn):
                async for msg in conn:
                    # handle the message...
                    # msg is an instance of aiosonic.web_socket_client.Message dataclass.
                    pass

            asyncio.create_task(ws_reader(ws))
            
            # Gracefully close the connection (optional)
            await ws.close(code=1000, reason="Normal closure")

if __name__ == "__main__":
    asyncio.run(main())
```

## HTTP/2 Usage

HTTP/2 requires HTTPS. Enable it at the client level or per-request.

**Client-level** (request HTTP/2 for HTTPS connections; servers may negotiate HTTP/1.1):

```python
import asyncio
import aiosonic

async def run():
    client = aiosonic.HTTPClient(http2=True)
    response = await client.get("https://http2.golang.org/reqinfo")
    assert response.status_code == 200
    print(await response.text())

asyncio.run(run())
```

**Per-request** (opt in for a single call):

```python
import asyncio
import aiosonic

async def run():
    client = aiosonic.HTTPClient()
    response = await client.get("https://http2.golang.org/reqinfo", http2=True)
    assert response.status_code == 200
    print(await response.text())

asyncio.run(run())
```

## Api Wrapping

You can easily wrap APIs with `BaseClient` and override its hooks to customize the response handling.

```python
import asyncio
import json
from aiosonic import BaseClient

class GitHubAPI(BaseClient):
    base_url = "https://api.github.com"
    default_headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        # "Authorization": "Bearer YOUR_GITHUB_TOKEN",
    }
    default_params = {"per_page": 50}

    async def process_response(self, response):
        body = await response.text()
        return json.loads(body)

    async def users(self, username: str, **kwargs):
        return await self.get(f"/users/{username}", **kwargs)
    
    async def update_repo(self, owner: str, repo: str, description: str):
        data = {
            "name": repo,
            "description": description,
        }
        return await self.put(f"/repos/{owner}/{repo}", json=data)


async def main():
    # You can pass an existing aiosonic.HTTPClient() instance in the constructor.
    # If not provided, BaseClient will create a new instance automatically.
    github = GitHubAPI()
    # Call the custom 'users' method to get data for user "sonic182"
    user_data = await github.users("sonic182")
    print(json.dumps(user_data, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
```

Note: You may wanna do a singleton of your clients implementations in order to reuse the internal HTTPClient instance, and it's pool of connections (efficient usage of the client), an example:

```python
class SingletonMixin:
    _instances = {}

    def __new__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__new__(cls)
        return cls._instances[cls]

class GitHubAPI(BaseClient, SingletonMixin):
    base_url = "https://api.github.com"
    # ... the rest of the code

# now, each instance of the class will be the first created
gh = GitHubAPI()
g2 = GitHubAPI()

gh is g2
```

## Auth, hooks and streaming

```python
import asyncio
import aiosonic
from aiosonic import BearerAuth


async def log_response(response):
    print(response.method, response.url, response.status_code)


async def main():
    client = aiosonic.HTTPClient(
        auths={"api.example.com": BearerAuth("token")},
        event_hooks={"response": [log_response]},
    )

    response = await client.get("https://api.example.com/items", params={"page": 2})
    response.raise_for_status()
    print(await response.json())

    async with client.stream("GET", "https://api.example.com/export") as response:
        async for line in response.iter_lines():
            print(line)

    await client.aclose()

asyncio.run(main())
```

## Benchmarks

`scripts/profile_http_clients.py` compares fully read responses with equal connection limits and alternates
client order between rounds. Install development dependencies with Poetry, then run:

```bash
poetry run python -m scripts.profile_http_clients --iterations 5000 --concurrency 25 --rounds 5
```

The script logs JSON containing dependency versions, individual run times, and medians.
Summarized results from a local HTTP/1.1 server returning a three-byte body:

```json
{
  "python": "3.13.5",
  "versions": {
    "aiohttp": "3.14.4",
    "httpx": "0.28.1"
  },
  "requests_per_round": 5000,
  "pool_size": 25,
  "rounds": 5,
  "results": {
    "aiosonic": {"median_ms": 768.92},
    "aiosonic_httpx": {"median_ms": 805.06},
    "aiohttp": {"median_ms": 914.26},
    "httpx": {"median_ms": 19308.40}
  }
}
```

Native aiosonic took about 16% less time than aiohttp in this workload. The HTTPX-compatible aiosonic client
is listed separately from the actual `httpx` library.

For the broader comparison including `requests` and cyclic pooling, run `poetry run python -m scripts.performance`.
To collect profiling data, add `--profile aiosonic --rounds 1 --output aiosonic.prof` to the command above.

> **Note:** These are local, machine- and workload-dependent measurements, not general performance guarantees.
> cProfile adds overhead; use unprofiled runs for timing comparisons.

## HTTP/2 Known Limitations

- **Server push not supported** — push promise frames are silently ignored (`PushPromiseReceived`, `PushedStreamReset`, `PushedStreamClosed`).
- **No cleartext HTTP/2 (`h2c`)** — HTTP/2 requires TLS. This matches RFC 7540 §3.3 browser requirements and is intentional.

## Development

Install development dependencies with Poetry:

```bash
poetry install
```

It is recommended to install Poetry in a separate virtual environment (via apt, pacman, etc.) rather than in your development environment. You can configure Poetry to use an in-project virtual environment by running:

```bash
poetry config virtualenvs.in-project true
```

### Building Documentation

```bash
poetry run sphinx-build -W -b html sourcedocs build/html
```

HTML builds also export each page, including API reference content, as Markdown. Use the
**Copy Markdown** button or **Download Markdown** link on a documentation page. Clipboard
copying requires HTTPS or localhost and browser permission; downloading remains available otherwise.

### Running Tests

```bash
poetry run pytest
```

## Contributing

1. Fork the repository.
2. Create a branch named `feature/your_feature`.
3. Commit your changes, push, and submit a pull request.

Thanks for contributing!

## Contributors

<a href="https://github.com/sonic182/aiosonic/graphs/contributors">
 <img src="https://contributors-img.web.app/image?repo=sonic182/aiosonic" alt="Contributors" />
</a>
