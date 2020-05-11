
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
      client = aiosonic.HttpClient()
      response = await client.get('https://www.google.com/')
      assert response.status_code == 200
      assert 'Google' in (await response.text())
  
      url = "https://postman-echo.com/post"
      posted_data = {'foo': 'bar'}
  
      # post data as multipart form
      response = await client.post(url, data=posted_data)
  
      assert response.status_code == 200
      data = json.loads(await response.content())
      assert data['form'] == posted_data
  
      # posted as json
      response = await client.post(url, json=posted_data)
  
      assert response.status_code == 200
      data = json.loads(await response.content())
      assert data['json'] == posted_data
  
      # Sample get request + timeout
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

The numbers speak for themselves

.. code-block:: bash

 $ python ./tests/performance.py
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
