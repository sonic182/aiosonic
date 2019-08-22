
[![Build Status](https://travis-ci.org/sonic182/aiosonic.svg?branch=master)](https://travis-ci.org/sonic182/aiosonic)
[![Coverage Status](https://coveralls.io/repos/github/sonic182/aiosonic/badge.svg?branch=master)](https://coveralls.io/github/sonic182/aiosonic?branch=master)
[![PyPI version](https://badge.fury.io/py/aiosonic.svg)](https://badge.fury.io/py/aiosonic)
# aiosonic

Fastest Python async http client

Here is some [documentation](https://sonic182.github.io/aiosonic/html/index.html).

There is a performance script in tests folder which shows very nice numbers

```
» python tests/performance.py
doing tests...
{
 "aiohttp": "1000 requests in 247.47 ms",
 "requests": "1000 requests in 3625.10 ms",
 "aiosonic": "1000 requests in 80.09 ms",
 "aiosonic cyclic": "1000 requests in 128.71 ms",
 "httpx": "1000 requests in 528.73 ms"
}
aiosonic is 209.00% faster than aiohttp
aiosonic is 4426.34% faster than requests
aiosonic is 60.70% faster than aiosonic cyclic
aiosonic is 560.17% faster than httpx
```

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

# Usage

```python
import asyncio
import aiosonic
import json


async def run():
    """Start."""
    response = await aiosonic.get('https://www.google.com/')
    assert response.status_code == 200
    assert 'Google' in (await response.text())

    url = "https://postman-echo.com/post"
    posted_data = {'foo': 'bar'}

    # post data as multipart form
    response = await aiosonic.post(url, data=posted_data)

    assert response.status_code == 200
    data = json.loads(await response.content())
    assert data['form'] == posted_data

    # posted as json
    response = await aiosonic.post(url, json=posted_data)

    assert response.status_code == 200
    data = json.loads(await response.content())
    assert data['json'] == posted_data
    print('success')


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
```

# TODO

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
