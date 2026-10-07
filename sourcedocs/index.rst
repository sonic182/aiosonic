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
- Comprehensive test coverage (nearly 100%)
- HTTP/2 (BETA; enabled via a flag)
- Authentication by host, event hooks, `raise_for_status()` and response streaming
- An httpx compatible client, see :ref:`httpx_client`

Requirements
============

- Python >= 3.10 (or PyPy 3.10+)

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

- ``auths`` maps hosts to credentials (``"api.example.com"``, or ``"api.example.com:8443"`` to match a port), so a host that is not in the map never gets them. Each value is a ``(user, password)`` tuple, ``BasicAuth``, ``BearerAuth`` or any ``Auth`` subclass. Digest and netrc authentication are not supported.
- A request is authenticated with, in this order: its ``auth=`` argument, the ``user:password@`` part of its url, or the ``auths`` entry of its host. The auth is resolved once, for the host of the original request, so redirects to other hosts do not get it.
- To send defaults (``base_url``, headers, query params) in every request of an API, use a ``BaseClient`` subclass with ``base_url``, ``default_headers`` and ``default_params``.
- ``event_hooks`` runs ``"request"`` hooks as ``hook(method, url, headers)`` and ``"response"`` hooks as ``hook(response)``, sync or async, on every send, including redirects and retries. Request hooks get the live headers, including ``Authorization`` and ``Cookie``, so a hook that adds a header must be idempotent and a logging hook should not print them.
- ``raise_for_status()`` raises ``HTTPStatusError`` (an ``AiosonicError``) for 4xx and 5xx responses; 3xx responses that were not followed do not raise.
- ``stream()`` releases the connection when the block ends, even if the body was not fully read.
- ``iter_bytes()`` decompresses gzip and deflate bodies, but not over HTTP/2; ``read_chunks()`` keeps returning the bytes as received.
- ``timeouts.sock_read`` only covers waiting for the status line, not the body; the body of a ``stream()`` response has no read timeout, so a stalled server holds its connection until the response is closed.
- ``async with HTTPClient()`` does not close the connector; call ``await client.aclose()`` once every response was read or closed.


Benchmarks
==========

Below is a basic performance benchmark comparing aiosonic with other HTTP clients:

.. code-block:: bash

 $ python scripts/performance.py
 {
   "aiohttp": "5000 requests in 558.31 ms",
   "aiosonic": "5000 requests in 563.95 ms",
   "requests": "5000 requests in 10306.90 ms",
   "aiosonic_cyclic": "5000 requests in 642.15 ms",
   "httpx": "5000 requests in 7920.04 ms"
 }

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
    httpx_client
    reference
    websocket_client
    sse_client
