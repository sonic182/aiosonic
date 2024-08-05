
===================
Welcome to aiosonic
===================

Really Fast Python asyncio HTTP 1.1 and 2.0 client.

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
- 100% test coverage (Sometimes not).



Requirements
============

- Python>=3.7
- PyPy >=3.7

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

Benchmarks
==========

Some benchmarking

.. code-block:: bash

 » python tests/performance.py
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


This is a *very basic, dummy test*, machine dependant. If you look for performance, test and compare your code with this and other packages like aiohttp.

You can perform this test by installing all test dependencies with `pip install -e ".[test]"` and doing `python tests/performance.py` in your own machine


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
