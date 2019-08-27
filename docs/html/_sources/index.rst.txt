
===================
Welcome to aiosonic
===================

Really Fast asynchronus HTTP 1.1 client,  Support for http 2.0 is planned.

Current version is |release|.

Repo is hosted at Github_.

.. _GitHub: https://github.com/sonic182/aiosonic


Features
========

- Keepalive and Smart Pool of Connections
- Multipart File Uploads
- Chunked responses handling
- Chunked requests
- Fully type annotated.
- Connection Timeouts
- Automatic Decompression
- Follow Redirects
- 100% test coverage.



Requirements
============

- Python>=3.6

Install
=======

.. code-block:: bash

   $ pip install aiosonic

.. You may want to install *optional* :term:`cchardet` library as faster
   replacement for :term:`chardet`:


Getting Started
===============

.. code-block::  python

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

Benchmarks
==========

The numbers speak for themselves

.. code-block:: bash

 $ python tests/performance.py
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


Contributing
============

1. Fork
2. create a branch `feature/your_feature`
3. commit - push - pull request

Thanks :)


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


.. toctree::
   :maxdepth: 2

   index
   examples
   reference
