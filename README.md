
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
httpx did break with: [Errno 24] Too many open files
{
 "aiosonic": "1000 requests in 146.89 ms",
 "aiosonic cyclic": "1000 requests in 146.17 ms",
 "aiohttp": "1000 requests in 319.42 ms",
 "requests": "1000 requests in 1766.96 ms"
}
aiosonic is 117.46% faster than aiohttp
aiosonic is 1102.93% faster than requests
aiosonic is -0.49% faster than aiosonic cyclic
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
    """Start."""
    # Sample get request
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

    # Sample get request + timeout
    from aiosonic.timeout import Timeouts
    timeouts = Timeouts(
        sock_read=10,
        sock_connect=3
    )
    response = await aiosonic.get('https://www.google.com/', timeouts=timeouts)
    assert response.status_code == 200
    assert 'Google' in (await response.text())

    print('success')


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
```

# TODO

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
