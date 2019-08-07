
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
 "aiohttp": "1000 requests in 471.06 ms",
 "requests": "1000 requests in 2298.61 ms",
 "aiosonic": "1000 requests in 206.83 ms",
 "aiosonic cyclic": "1000 requests in 241.14 ms"
}
aiosonic is 127.76% faster than aiohttp
aiosonic is 1011.37% faster than requests
aiosonic is 16.59% faster than aiosonic cyclic  # Using non standard pool of connections
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
