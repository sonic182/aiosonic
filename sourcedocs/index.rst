===================
Welcome to aiosonic
===================

Really Fast Python asyncio HTTP 1.1 and 2.0 client.

Current version is |release|.

Repo is hosted at GitHub_.

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
- **WebSocket support**: send and receive text, binary, and JSON messages; handle ping/pong; negotiate subprotocols; and manage close codes.
- 100% test coverage (Sometimes not).

Requirements
============

- Python>=3.8
- PyPy >=3.8

Install
=======

.. code-block:: bash

   $ pip install aiosonic

.. note::
   You may want to install *optional* :term:`cchardet` library as faster
   replacement for :term:`chardet`.


Getting Started
===============

.. code-block:: python

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
       # Posted as JSON
       # ##################
       response = await client.post(url, json=posted_data)
       assert response.status_code == 200
       data = json.loads(await response.content())
       assert data['json'] == posted_data

       # ##################
       # Request with timeout
       # ##################
       from aiosonic.timeout import Timeouts
       timeouts = Timeouts(sock_read=10, sock_connect=3)
       response = await client.get('https://www.google.com/', timeouts=timeouts)
       assert response.status_code == 200
       assert 'Google' in (await response.text())

       print('HTTP client success')

   if __name__ == '__main__':
       asyncio.run(run())


WebSocket Example
=================

This example demonstrates how to use the WebSocket support in aiosonic.

.. code-block:: python

   import asyncio
   from aiosonic import WebSocketClient

   async def run_ws():
       async with WebSocketClient() as client:
           # Connect to a WebSocket echo server
           async with await client.connect("ws://echo.websocket.org") as ws:
               # Send a text message
               await ws.send_text("Hello WebSocket!")
               # Wait for the echo response (with a timeout of 5 seconds)
               response = await ws.receive_text(timeout=5)
               print("Received:", response)
               # Close the connection gracefully
               await ws.close(code=1000, reason="Normal closure")

   if __name__ == '__main__':
       asyncio.run(run_ws())


Benchmarks
==========

Some benchmarking

.. code-block:: bash

   $ python tests/performance.py
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

You can perform this test by installing all test dependencies with
```
pip install -e ".[test]"
```
and running:

```
python tests/performance.py
```

Contributing
============

1. Fork
2. Create a branch `feature/your_feature`
3. Commit - Push - Pull Request

Thanks :)


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
* :ref:`websocket_client`

.. toctree::
   :maxdepth: 2

   index
   examples
   reference
   websocket_client
