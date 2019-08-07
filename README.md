
[![Build Status](https://travis-ci.org/sonic182/aiosonic.svg?branch=master)](https://travis-ci.org/sonic182/aiosonic)
[![Coverage Status](https://coveralls.io/repos/github/sonic182/aiosonic/badge.svg?branch=master)](https://coveralls.io/github/sonic182/aiosonic?branch=master)
[![PyPI version](https://badge.fury.io/py/aiosonic.svg)](https://badge.fury.io/py/aiosonic)
# aiosonic

Async http client

This project is in alpha state. Here is some [documentation](https://sonic182.github.io/aiosonic/html/index.html).

There is a performance script in tests folder which shows very nice numbers

```
» python tests/performance.py
doing tests...
{
 "aiohttp": "1000 requests in 577.93 ms",
 "requests": "1000 requests in 2231.33 ms",
 "aiosonic": "1000 requests in 310.97 ms"
}
aiosonic is 85.85% faster than aiohttp
aiosonic is 617.55% faster than requests
```

# Requirements:

* Python>=3.6


# Features:

* Keepalive and pool of connections
* Multipart File Uploads
* Chunked responses handling
* Chunked requests
* Connection Timeouts
* Automatic Decompression

# TODO

In order

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
