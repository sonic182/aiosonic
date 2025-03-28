![github status](https://github.com/sonic182/aiosonic/actions/workflows/python.yml/badge.svg)
[![Coverage Status](https://coveralls.io/repos/github/sonic182/aiosonic/badge.svg?branch=master)](https://coveralls.io/github/sonic182/aiosonic?branch=master)
[![PyPI version](https://badge.fury.io/py/aiosonic.svg)](https://badge.fury.io/py/aiosonic)
[![Documentation Status](https://readthedocs.org/projects/aiosonic/badge/?version=latest)](https://aiosonic.readthedocs.io/en/latest/?badge=latest)
[![Discord](https://img.shields.io/discord/898929656969965648)](https://discord.gg/e7tBnYSRjj)

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
- (Nearly) 100% test coverage
- HTTP/2 (BETA; enabled with a flag)

## Requirements

- Python >= 3.8 (or PyPy 3.8+)

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

## Api Wrapping

You can easily wrap apis with `AioSonicBaseClient` class

```python
import asyncio
import json
from aiosonic.base_client import AioSonicBaseClient

class GitHubAPI(AioSonicBaseClient):
    base_url = "https://api.github.com"
    default_headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        # "Authorization": "Bearer YOUR_GITHUB_TOKEN",
    }

    async def users(self, username: str, **kwargs):
        # base_url and headers are applied internally.
        return await self.get(f"/users/{username}", **kwargs)
    
    async def update_repo(self, owner: str, repo: str, description: str):
        data = {
            "name": repo,
            "description": description,
        }
        return await self.put(f"/repos/{owner}/{repo}", json=data)


async def main():
    # You can pass an existing aiosonic.HTTPClient() instance in the constructor.
    # If not provided, AioSonicBaseClient will create a new instance automatically.
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

class GitHubAPI(AioSonicBaseClient, SingletonMixin):
    base_url = "https://api.github.com"
    # ... the rest of the code

# now, each instance of the class will be the first created
gh = GitHubAPI()
g2 = GitHubAPI()

gh == gh2
```

## Benchmarks

A simple performance benchmark script is included in the `tests` folder. For example:

```bash
python tests/performance.py
```

Example output:

```json
doing tests...
{
 "aiosonic": "1000 requests in 105.53 ms",
 "aiosonic cyclic": "1000 requests in 104.08 ms",
 "aiohttp": "1000 requests in 184.51 ms",
 "requests": "1000 requests in 1644.21 ms"
}
aiosonic is 74.84% faster than aiohttp
aiosonic is 1457.99% faster than requests
aiosonic is -1.38% faster than aiosonic cyclic
```

> **Note:**  
> These benchmarks are basic and machine-dependent. They are intended as a rough comparison.

## [TODO's](https://github.com/sonic182/aiosonic/projects/1)

- **HTTP/2:**
  - [x] GET requests
  - [x] Requests with data sending
  - [ ] Stable HTTP/2 release
- Better documentation
- International domains and URLs (IDNA + cache)
- Basic/Digest authentication
- [x] HTTP proxy support
- [x] Sessions with cookie persistence
- [x] Elegant key/value cookies

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
