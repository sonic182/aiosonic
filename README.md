
[![Build Status](https://travis-ci.org/sonic182/aiosonic.svg?branch=master)](https://travis-ci.org/sonic182/aiosonic)
[![Coverage Status](https://coveralls.io/repos/github/sonic182/aiosonic/badge.svg?branch=master)](https://coveralls.io/github/sonic182/aiosonic?branch=master)
[![PyPI version](https://badge.fury.io/py/aiosonic.svg)](https://badge.fury.io/py/aiosonic)
# aiosonic

Async http client

This project is in alpha state.

There is a performance script in tests folder which shows very nice numbers

```
» python tests/performance.py
doing tests...
{
 "aiohttp": "1000 requests in 576.92 ms",
 "requests": "1000 requests in 2219.63 ms",
 "aiosonic": "1000 requests in 289.28 ms"
}
aiosonic is 0.99 times faster than aiohttp
aiosonic is 6.67 times faster than requests
```

# Requirements:

* Python>=3.6


# Features:

* Keepalive and pool of connections
* Multipart File Uploads
* Chunked responses handling
* Connection Timeouts

# TODO

In order

* Automatic Decompression
* International Domains and URLs (idna + cache)
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
