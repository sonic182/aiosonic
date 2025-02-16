===================
Welcome to aiosonic
===================

A really fast, lightweight Python asyncio HTTP/1.1, HTTP/2, and WebSocket client.

Current version is |release|.

The repository is hosted on GitHub_: 

.. _GitHub: https://github.com/sonic182/aiosonic


Features
========

- Keepalive support and a smart pool of connections
- Multipart file uploads
- Handling of chunked responses and requests
- Connection timeouts and automatic decompression
- Automatic redirect following
- Fully type-annotated code
- WebSocket support
- Comprehensive test coverage (nearly 100%)
- HTTP/2 (BETA; enabled via a flag)

Requirements
============

- Python >= 3.8 (or PyPy 3.8+)

Installation
============

.. code-block:: bash

   $ pip install aiosonic


Getting Started
===============

Below is a basic example of using aiosonic's HTTP client:

.. code-block:: python

   import asyncio
   import aiosonic
   import json

   async def run():
       client = aiosonic.HTTPClient()

       # Sample GET request
       response = await client.get('https://www.google.com/')
       assert response.status_code == 200
       assert 'Google' in (await response.text())

       # POST data as multipart form
       url = "https://postman-echo.com/post"
       posted_data = {'foo': 'bar'}
       response = await client.post(url, data=posted_data)
       assert response.status_code == 200
       data = json.loads(await response.content())
       assert data['form'] == posted_data

       # POST data as JSON
       response = await client.post(url, json=posted_data)
       assert response.status_code == 200
       data = json.loads(await response.content())
       assert data['json'] == posted_data

       # GET request with timeouts
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

This example demonstrates how to use the WebSocket support provided by aiosonic.

.. code-block:: python

   import asyncio
   from aiosonic import WebSocketClient

   async def main():
       # Replace with your WebSocket server URL
       ws_url = "ws://localhost:8080"  
       async with WebSocketClient() as client:
           async with await client.connect(ws_url) as ws:
               # Send a text message.
               await ws.send_text("Hello WebSocket")
               
               # Receive the echo response.
               response = await ws.receive_text()
               print("Received:", response)
               
               # Send a ping and wait for the pong response.
               await ws.ping(b"keep-alive")
               pong = await ws.receive_pong()
               print("Pong received:", pong)
               
               # Gracefully close the connection.
               await ws.close(code=1000, reason="Normal closure")

   if __name__ == "__main__":
       asyncio.run(main())


Benchmarks
==========

Below is a basic performance benchmark comparing aiosonic with other HTTP clients:

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

Note that these benchmarks are machine-dependent and intended only as a rough comparison.


Contributing
============

1. Fork the repository.
2. Create a branch (e.g. ``feature/your_feature``).
3. Commit, push, and submit a pull request.

Thanks to all contributors!


Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. toctree::
   :maxdepth: 2

   examples
   reference
   websocket_client
