
=========
Reference
=========

TODO: get better this page


Connector and Client Client
===========================

.. autoclass:: aiosonic.connectors.TCPConnector
|
.. autoclass:: aiosonic.HTTPClient
|
.. autofunction:: aiosonic.HTTPClient.request
|
.. autofunction:: aiosonic.HTTPClient.get
|
.. autofunction:: aiosonic.HTTPClient.post
|
.. autofunction:: aiosonic.HTTPClient.put
|
.. autofunction:: aiosonic.HTTPClient.patch
|
.. autofunction:: aiosonic.HTTPClient.delete
|
.. autofunction:: aiosonic.HTTPClient.wait_requests


Classes
=======


.. autoclass:: aiosonic.HttpHeaders
   :members:
|
.. autoclass:: aiosonic.HttpResponse
   :members:
|


Tiemout Class
=============

.. autoclass:: aiosonic.timeout.Timeouts
   :members:
|

Pool Classes
============

.. autoclass:: aiosonic.pools.PoolConfig
   :members:

.. autoclass:: aiosonic.pools.SmartPool
   :members:
|
.. autoclass:: aiosonic.pools.CyclicQueuePool
   :members:


DNS Resolver
============

For custom dns servers, you sould install `aiodns` package and use Async resolver as follow

.. code-block::  python

  from aiosonic.resolver import AsyncResolver

  resolver = AsyncResolver(nameservers=["8.8.8.8", "8.8.4.4"])
  conn = aiosonic.TCPConnector(resolver=resolver)

Then, pass connector to aiosonic HTTPClient instance.

.. autoclass:: aiosonic.resolver.AsyncResolver
   :members:
|
.. autoclass:: aiosonic.resolver.ThreadedResolver
   :members:

Multipart Form Data
===================

This class can be used for sending multipart form data.

.. autoclass:: aiosonic.multipart.MultipartForm
   :members:

Proxy Support
=============

.. autoclass:: aiosonic.proxy.Proxy
   :members:
