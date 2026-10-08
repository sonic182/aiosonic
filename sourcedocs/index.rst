===================
Welcome to aiosonic
===================

.. image:: _static/aiosonic-banner.png
   :alt: aiosonic banner
   :align: center
   :width: 100%

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
- Server-Sent Events (SSE) support
- HTTP proxy support
- Sessions with cookie persistence
- Elegant key/value cookies
- Comprehensive test coverage
- HTTP/2 (enabled via a flag; requires HTTPS)
- Authentication by host, event hooks, `raise_for_status()` and response streaming
- An httpx compatible client, see :ref:`httpx_client`

Requirements
============

- Python >= 3.10 (or PyPy 3.11+)

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
 
     # POST data as URL-encoded form
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


SSE Example
===========

This example demonstrates how to use the Server-Sent Events (SSE) support provided by aiosonic.

.. code-block:: python

  import asyncio
  from aiosonic import SSEClient

  async def main():
      # Replace with your SSE endpoint URL
      sse_url = "http://localhost:8080/sse"
      client = SSEClient()
      async with client.connect(sse_url) as sse_conn:
          async for event in sse_conn:
              print(f"Event: {event['event']}, Data: {event['data']}")
              if event['data'] == 'stop':
                  break

  if __name__ == "__main__":
      asyncio.run(main())


Auth, hooks and streaming
==========================

.. code-block:: python

  import asyncio
  import aiosonic
  from aiosonic import BearerAuth


  async def log_response(response):
      print(response.method, response.url, response.status_code)


  async def main():
      client = aiosonic.HTTPClient(
          auths={"api.example.com": BearerAuth("token")},
          event_hooks={"response": [log_response]},
      )

      response = await client.get("https://api.example.com/items", params={"page": 2})
      response.raise_for_status()
      print(await response.json())

      async with client.stream("GET", "https://api.example.com/export") as response:
          async for line in response.iter_lines():
              print(line)

      await client.aclose()

  asyncio.run(main())

See the :ref:`http_client_guide` for authentication precedence, API defaults, event hooks,
status errors, streaming timeouts, and client cleanup.


Benchmarks
==========

Use the controlled benchmark driver with fully consumed, validated responses, equal pool limits,
and alternating client order:

.. code-block:: bash

   poetry run python -m scripts.profile_http_clients --iterations 5000 --concurrency 25 --rounds 5

The documented five-round local medians (Python 3.13.5, pool size 25, three-byte HTTP/1.1 responses)
were 768.92 ms for native aiosonic, 805.06 ms for its HTTPX-compatible wrapper,
914.26 ms for aiohttp 3.14.4, and 19,308.40 ms for httpx 0.28.1.

These are machine- and workload-dependent results, not general performance guarantees.
Use unprofiled runs to compare throughput; add ``--profile aiosonic --rounds 1`` to identify hotspots.
The broader comparison including requests and cyclic pooling is available with
``poetry run python -m scripts.performance``.

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
    http_client
    httpx_client
    reference
    websocket_client
    sse_client
