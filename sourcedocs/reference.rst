
=========
Reference
=========


Connector and HTTP Client
=========================

.. autoclass:: aiosonic.connectors.TCPConnector

.. autoclass:: aiosonic.HTTPClient

.. autofunction:: aiosonic.HTTPClient.request

.. autofunction:: aiosonic.HTTPClient.get

.. autofunction:: aiosonic.HTTPClient.post

.. autofunction:: aiosonic.HTTPClient.put

.. autofunction:: aiosonic.HTTPClient.patch

.. autofunction:: aiosonic.HTTPClient.delete

.. autofunction:: aiosonic.HTTPClient.wait_requests

.. autofunction:: aiosonic.HTTPClient.head

.. autofunction:: aiosonic.HTTPClient.options

.. autofunction:: aiosonic.HTTPClient.stream

.. autofunction:: aiosonic.HTTPClient.aclose


Classes
=======


.. autoclass:: aiosonic.HttpHeaders
   :members:

.. autoclass:: aiosonic.HttpResponse
   :members:


SSE Client
==========

.. autoclass:: aiosonic.SSEClient
   :members:
   :show-inheritance:



Timeout Class
=============

.. autoclass:: aiosonic.timeout.Timeouts
   :members:


Pool Classes
============

.. autoclass:: aiosonic.pools.PoolConfig
   :members:

.. autoclass:: aiosonic.pools.SmartPool
   :members:

.. autoclass:: aiosonic.pools.CyclicQueuePool
   :members:


DNS Resolver
============

For custom DNS servers, install the ``aiodns`` package and use ``AsyncResolver`` as follows:

.. code-block::  python

  from aiosonic import TCPConnector
  from aiosonic.resolver import AsyncResolver

  resolver = AsyncResolver(nameservers=["8.8.8.8", "8.8.4.4"])
  conn = TCPConnector(resolver=resolver)

Then, pass connector to aiosonic HTTPClient instance.

.. autoclass:: aiosonic.resolver.AsyncResolver
   :members:

.. autoclass:: aiosonic.resolver.ThreadedResolver
   :members:

Multipart Form Data
===================

This class can be used for sending multipart form data.

.. autoclass:: aiosonic.multipart.MultipartForm
   :members:

.. autoclass:: aiosonic.multipart.MultipartFile
   :members:

Proxy Support
=============

.. autoclass:: aiosonic.proxy.Proxy
   :members:
