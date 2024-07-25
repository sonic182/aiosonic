
![github status](https://github.com/sonic182/aiosonic/actions/workflows/python.yml/badge.svg)
[![Coverage Status](https://coveralls.io/repos/github/sonic182/aiosonic/badge.svg?branch=master)](https://coveralls.io/github/sonic182/aiosonic?branch=master)
[![PyPI version](https://badge.fury.io/py/aiosonic.svg)](https://badge.fury.io/py/aiosonic)
[![Documentation Status](https://readthedocs.org/projects/aiosonic/badge/?version=latest)](https://aiosonic.readthedocs.io/en/latest/?badge=latest)
[![Discord](https://img.shields.io/discord/898929656969965648)](https://discord.gg/e7tBnYSRjj)

# aiosonic - lightweight Python asyncio http client


Very fast, lightweight Python asyncio http client

Here is some [documentation](https://aiosonic.readthedocs.io/en/latest/).

There is a performance script in tests folder which shows very nice numbers

```
» python tests/performance.py
doing tests...
{
 "aiosonic": "1000 requests in 182.03 ms",
 "aiosonic cyclic": "1000 requests in 370.55 ms",
 "aiohttp": "1000 requests in 367.66 ms",
 "requests": "1000 requests in 4613.77 ms",
 "httpx": "1000 requests in 812.41 ms"
}
aiosonic is 101.97% faster than aiohttp
aiosonic is 2434.55% faster than requests
aiosonic is 103.56% faster than aiosonic cyclic
aiosonic is 346.29% faster than httpx
```

This is a *very basic, dummy test*, machine dependant. If you look for performance, test and compare your code with this and other packages like aiohttp.

You can perform this test by installing all test dependencies with `pip install -e ".[test]"` and doing `python tests/performance.py` in your own machine

# Requirements:

* Python>=3.8
* PyPy>=3.8


# Features:

* Keepalive and smart pool of connections
* Multipart File Uploads
* Chunked responses handling
* Chunked requests
* Connection Timeouts
* Automatic Decompression
* Follow Redirects
* Fully type annotated.
* 100% test coverage (Sometimes not).
* HTTP2 (BETA) when using the correct flag

# Installation

`pip install aiosonic`

# Usage

```python
import asyncio
import aiosonic
import json


async def run():
    client = aiosonic.HTTPClient()

    # ##################
    # Sample get request
    # ##################
    response = await client.get('https://www.google.com/')
    assert response.status_code == 200
    assert 'Google' in (await response.text())

    # ##################
    # Post data as multipart form
    # ##################
    url = "https://postman-echo.com/post"
    posted_data = {'foo': 'bar'}
    response = await client.post(url, data=posted_data)

    assert response.status_code == 200
    data = json.loads(await response.content())
    assert data['form'] == posted_data

    # ##################
    # Posted as json
    # ##################
    response = await client.post(url, json=posted_data)

    assert response.status_code == 200
    data = json.loads(await response.content())
    assert data['json'] == posted_data

    # ##################
    # Sample request + timeout
    # ##################
    from aiosonic.timeout import Timeouts
    timeouts = Timeouts(
        sock_read=10,
        sock_connect=3
    )
    response = await client.get('https://www.google.com/', timeouts=timeouts)
    assert response.status_code == 200
    assert 'Google' in (await response.text())

    print('success')


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
```

# [TODO'S](https://github.com/sonic182/aiosonic/projects/1)

* HTTP2
  * [x] Get
  * [x] Request with data sending
  * [ ] Do a aiosonic release with stable http2
* Better documentation
* International Domains and URLs (idna + cache)
* Basic/Digest Authentication
* [x] Requests using a http proxy
* [x] Sessions with Cookie Persistence
* [x] Elegant Key/Value Cookies

# Development

Install packages with poetry

Reference: https://python-poetry.org/docs/

```bash
poetry install
```

It is advised that you should install poetry in a serparate virtualenv (I suggest to install it with apt/pacman/etc.), other than the one you may use for development in aiosonic.

I do configure poetry with `poetry config virtualenvs.in-project true` so it uses a virtualenv created in `.venv/`, in aiosonic folder.

### Running tests

```bash
poetry run py.test
```

# Contribute

1. Fork
2. create a branch `feature/your_feature`
3. commit - push - pull request

Thanks :)

# Contributors

<a href="https://github.com/sonic182/aiosonic/graphs/contributors">
 <img src="https://contributors-img.web.app/image?repo=sonic182/aiosonic" />
</a>
