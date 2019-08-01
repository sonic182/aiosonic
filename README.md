
[![Build Status](https://travis-ci.org/sonic182/aiosonic.svg?branch=master)](https://travis-ci.org/sonic182/aiosonic)
[![Coverage Status](https://coveralls.io/repos/github/sonic182/aiosonic/badge.svg?branch=master)](https://coveralls.io/github/sonic182/aiosonic?branch=master)
# aiosonic

Async http client

This project is in alpha state.

# Features:

* Keepalive and pool of connections
* Multipart File Uploads
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
pip-compile dev-requirements.in
pip-sync requirements.txt dev-requirements.txt
```

# Contribute

1. Fork
2. create a branch `feature/your_feature`
3. commit - push - pull request

Thanks :)
