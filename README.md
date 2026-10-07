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
- (Nearly) 100% test coverage
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

    # POST data as multipart form
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

**Client-level** (all requests use HTTP/2):

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

gh == gh2
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

Notes and limits:

- `auths` maps hosts to credentials (`"api.example.com"`, or `"api.example.com:8443"` to match a port), so a host that is not in the map never gets them. Each value is a `(user, password)` tuple, `BasicAuth`, `BearerAuth` or any `Auth` subclass. Digest and netrc authentication are not supported.
- A request is authenticated with, in this order: its `auth=` argument, the `user:password@` part of its url, or the `auths` entry of its host. The auth is resolved once, for the host of the original request, so redirects to other hosts do not get it.
- To send defaults (`base_url`, headers, query params) in every request of an API, use a `BaseClient` subclass with `base_url`, `default_headers` and `default_params`, see "Api Wrapping".
- `event_hooks` runs `"request"` hooks as `hook(method, url, headers)` and `"response"` hooks as `hook(response)`, sync or async, on every send, including redirects and retries. Request hooks get the live headers, including `Authorization` and `Cookie`, so a hook that adds a header must be idempotent and a logging hook should not print them.
- `raise_for_status()` raises `HTTPStatusError` (an `AiosonicError`) for 4xx and 5xx responses; 3xx responses that were not followed do not raise.
- `stream()` releases the connection when the block ends, even if the body was not fully read.
- `iter_bytes()` decompresses gzip and deflate bodies, but not over HTTP/2; `read_chunks()` keeps returning the bytes as received.
- `timeouts.sock_read` only covers waiting for the status line, not the body; the body of a `stream()` response has no read timeout, so a stalled server holds its connection until the response is closed.
- `async with HTTPClient()` does not close the connector; call `await client.aclose()` once every response was read or closed.

## Benchmarks

A simple performance benchmark script is included in the `tests` folder. For example:

```bash
python scripts/performance.py
```

Example output:

```json
{
  "aiohttp": "5000 requests in 558.31 ms",
  "aiosonic": "5000 requests in 563.95 ms",
  "requests": "5000 requests in 10306.90 ms",
  "aiosonic_cyclic": "5000 requests in 642.15 ms",
  "httpx": "5000 requests in 7920.04 ms"
}
```

aiosonic is 1457.99% faster than requests
aiosonic is -1.38% faster than aiosonic cyclic

> **Note:**  
> These benchmarks are basic and machine-dependent. They are intended as a rough comparison.

## HTTP/2 Known Limitations

- **Server push not supported** — push promise frames are silently ignored (`PushPromiseReceived`, `PushedStreamReset`, `PushedStreamClosed`).
- **No cleartext HTTP/2 (`h2c`)** — HTTP/2 requires TLS. This matches RFC 7540 §3.3 browser requirements and is intentional.

## [TODO's](https://github.com/sonic182/aiosonic/projects/1)

- Better documentation
- International domains and URLs (IDNA + cache)
- Basic/Digest authentication

## Development

Install development dependencies with Poetry:

```bash
poetry install
```

It is recommended to install Poetry in a separate virtual environment (via apt, pacman, etc.) rather than in your development environment. You can configure Poetry to use an in-project virtual environment by running:

```bash
poetry config virtualenvs.in-project true
```

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
