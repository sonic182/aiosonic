
[![Build Status](https://travis-ci.org/sonic182/aiosonic.svg?branch=master)](https://travis-ci.org/sonic182/aiosonic)
[![Azure Build Status](https://dev.azure.com/johander-182/aiosonic/_apis/build/status/sonic182.aiosonic?branchName=master)](https://dev.azure.com/johander-182/aiosonic/_build/latest?definitionId=1&branchName=master)
[![Coverage Status](https://coveralls.io/repos/github/sonic182/aiosonic/badge.svg?branch=master)](https://coveralls.io/github/sonic182/aiosonic?branch=master)
[![PyPI version](https://badge.fury.io/py/aiosonic.svg)](https://badge.fury.io/py/aiosonic)
[![Documentation Status](https://readthedocs.org/projects/aiosonic/badge/?version=latest)](https://aiosonic.readthedocs.io/en/latest/?badge=latest)
# aiosonic

Fastest Python async http client

Here is some [documentation](https://aiosonic.readthedocs.io/en/latest/).

There is a performance script in tests folder which shows very nice numbers

```
» python ./tests/performance.py
doing tests...
{
 "aiosonic": "1000 requests in 110.56 ms",
 "aiosonic cyclic": "1000 requests in 207.75 ms",
 "aiohttp": "1000 requests in 357.19 ms",
 "requests": "1000 requests in 4274.21 ms",
 "httpx": "1000 requests in 800.98 ms"
}
aiosonic is 223.05% faster than aiohttp
aiosonic is 3765.79% faster than requests
aiosonic is 87.90% faster than aiosonic cyclic
aiosonic is 624.45% faster than httpx
```

You can perform this test by installing all test dependencies with `pip install -e ".[test]"` and doing `python tests/performance.py` in your own machine

# Requirements:

* Python>=3.6


# Features:

* Keepalive and smart pool of connections
* Multipart File Uploads
* Chunked responses handling
* Chunked requests
* Connection Timeouts
* Automatic Decompression
* Follow Redirects
* Fully type annotated.
* 100% test coverage.

# Installation

`pip install aiosonic`

# Usage

```python
import asyncio
import aiosonic
import json


async def run():
    client = aiosonic.HttpClient()

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
  * [ ] Request with data sending
* Better documentation
* International Domains and URLs (idna + cache)
* Requests using a http proxy
* Sessions with Cookie Persistence
* Basic/Digest Authentication
* Elegant Key/Value Cookies

# Development

Install packages with pip-tools:
```bash
pip install pip-tools
pip-compile
pip-compile test-requirements.in
pip-sync requirements.txt test-requirements.txt
```

# Contribute

1. Fork
2. create a branch `feature/your_feature`
3. commit - push - pull request

Thanks :)
