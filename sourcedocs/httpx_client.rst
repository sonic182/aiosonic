.. _httpx_client:

httpx compatible client
=======================

:class:`aiosonic.httpx_client.AsyncClient` has the API of ``httpx.AsyncClient``, so code written for httpx can
use aiosonic with few changes. It does not need httpx installed.

It is a :class:`aiosonic.BaseClient` that sends its requests with :class:`aiosonic.HTTPClient`, and returns a
:class:`aiosonic.httpx_client.Response` with httpx's synchronous ``content``, ``text`` and ``json()``.


Migrating from httpx
--------------------

In most cases only the import changes:

.. code-block:: python

    # import httpx
    # client = httpx.AsyncClient(...)
    from aiosonic.httpx_client import AsyncClient

    client = AsyncClient(...)

Exceptions are not named as in httpx, so ``except httpx.HTTPStatusError`` becomes
``except aiosonic.exceptions.HTTPStatusError``, and the other ``except httpx.*`` clauses need the aiosonic
exceptions listed in `Exceptions`_.


Usage
-----

.. code-block:: python

    import asyncio

    from aiosonic.exceptions import HTTPStatusError
    from aiosonic.httpx_client import AsyncClient


    async def main():
        async with AsyncClient(
            base_url="https://api.example.com",
            headers={"Accept": "application/json"},
            params={"lang": "en"},
            auth=("user", "password"),
            timeout=10.0,
            follow_redirects=True,
        ) as client:
            response = await client.get("/users", params={"page": "2"})
            response.raise_for_status()
            print(response.status_code, response.json())

            response = await client.post("/users", json={"name": "Ana"})
            print(response.text)

            try:
                (await client.delete("/users/1")).raise_for_status()
            except HTTPStatusError as exc:
                print("failed:", exc.response.status_code)

    asyncio.run(main())

``async with`` closes the connections of the client when the block ends; without it, call
``await client.aclose()``.


Client options
--------------

==================== ==========================================================================================
Argument             Meaning
==================== ==========================================================================================
``base_url``         Url prepended to relative request urls (``"/users"``). Absolute urls are used as given.
``headers``          Headers sent in every request. Request headers override them, ignoring case.
``params``           Query params sent in every request. Request params with the same name override them.
``auth``             ``(user, password)`` tuple, :class:`aiosonic.auth.BasicAuth`,
                     :class:`aiosonic.auth.BearerAuth` or an :class:`aiosonic.auth.Auth` subclass, used for every
                     request. It is not sent to another host when following a redirect.
``timeout``          Seconds for connecting, waiting for the response and getting a connection from the pool
                     (5 by default), ``None`` to disable them, or a :class:`aiosonic.timeout.Timeouts`.
                     The ``timeout`` of a request overrides it, except for getting a connection from the
                     pool, which only uses the client one.
``follow_redirects`` Whether to follow redirects (``False`` by default).
``max_redirects``    Redirects to follow before raising :class:`aiosonic.exceptions.MaxRedirects` (20).
``verify``           Whether to verify ssl certificates, or the ``ssl.SSLContext`` to use.
``http2``            Whether to use HTTP/2.
``event_hooks``      ``{"request": [...], "response": [...]}``, see `Event hooks`_.
``proxy``            Proxy url (``"http://user:password@proxy:8080"``), or an :class:`aiosonic.proxy.Proxy`.
``http_client``      An :class:`aiosonic.HTTPClient` to send the requests with, to share its connections. It
                     can not be combined with ``event_hooks`` or ``proxy``, and ``aclose()`` does not close it.
                     The pool timeout and cookie handling are then the ones of that client.
==================== ==========================================================================================

``client.headers`` and ``client.params`` can be changed after creating the client, as in httpx:

.. code-block:: python

    client.headers["Authorization"] = "Bearer new-token"

Cookies set by the server are kept and sent back in later requests to the same host, unless ``http_client``
is given, which keeps them according to its ``handle_cookies``.


Requests
--------

``client.request(method, url, ...)``, ``get``, ``head``, ``options``, ``post``, ``put``, ``patch`` and
``delete`` accept:

- ``params`` and ``headers``, merged with the client ones.
- ``content``: raw body, as ``bytes``, ``str`` or an (async) iterator of ``bytes``.
- ``data``: form fields, sent ``application/x-www-form-urlencoded``, or as multipart fields along with
  ``files``.
- ``files``: files sent as ``multipart/form-data``, by field name. Each one is a file object, ``bytes``, or a
  ``(filename, file)`` or ``(filename, file, content_type)`` tuple.
- ``json``: object sent encoded as json.
- ``auth``, ``follow_redirects`` and ``timeout`` to override the client ones for this request.
  ``auth=None`` sends no credentials.

.. code-block:: python

    await client.post("/form", data={"name": "Ana"})
    await client.post("/raw", content=b"\x00\x01")
    await client.post(
        "/upload",
        data={"description": "avatar"},
        files={"image": ("avatar.png", open("avatar.png", "rb"), "image/png")},
    )


Responses
---------

The body of the response is read before the request returns.

- ``status_code``, ``headers``, ``url``, ``http_version`` (``"HTTP/1.1"``), ``reason_phrase``, ``cookies``
  and ``encoding``.
- ``content`` (bytes), ``text`` and ``json(**kwargs)``. gzip and deflate bodies are decompressed.
- ``is_success``, ``is_redirect``, ``is_informational``, ``is_client_error``, ``is_server_error`` and
  ``is_error``.
- ``raise_for_status()`` raises :class:`aiosonic.exceptions.HTTPStatusError` for any status that is not 2xx,
  including a redirect that was not followed, and returns the response otherwise, so it can be chained:
  ``data = response.raise_for_status().json()``.
- ``request``: the method and url of the request.


Streaming
---------

``client.stream()`` gives the response before reading its body. The connection is released when the block
ends, even if the body was not fully read.

.. code-block:: python

    async with client.stream("GET", "/export.csv") as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            print(line)

    async with client.stream("GET", "/big-file") as response:
        with open("big-file", "wb") as file:
            async for chunk in response.aiter_bytes():
                file.write(chunk)

- ``await response.aread()`` reads the whole body, after which ``content``, ``text`` and ``json()`` work.
  Before it they raise :class:`aiosonic.exceptions.ResponseNotRead`.
- ``aiter_bytes()`` (decompressed), ``aiter_text()``, ``aiter_lines()`` and ``aiter_raw()`` (as received)
  iterate over the body. A body can be iterated once; reading it again raises
  :class:`aiosonic.exceptions.StreamConsumed`.
- ``await response.aclose()`` releases the connection before the block ends.


Event hooks
-----------

Request hooks are called with a :class:`aiosonic.httpx_client.Request` before sending each request, and
response hooks with a :class:`aiosonic.httpx_client.Response` after receiving each one, also for redirects and
retries. Hooks may be sync or async.

.. code-block:: python

    def add_request_id(request):
        request.headers["X-Request-Id"] = new_request_id()

    async def log_response(response):
        print(response.request.method, response.request.url, response.status_code)

    client = AsyncClient(event_hooks={"request": [add_request_id], "response": [log_response]})

- Changes to ``request.headers`` are sent. They include ``Authorization`` and ``Cookie``, so a logging hook
  should not print them.
- The body of the response given to a response hook may not be read yet; use ``await response.aread()`` to
  read it there.


Exceptions
----------

======================================= ================================================================
httpx                                   aiosonic
======================================= ================================================================
``httpx.HTTPStatusError``               :class:`aiosonic.exceptions.HTTPStatusError`
``httpx.TimeoutException``              :class:`aiosonic.exceptions.BaseTimeout` (``ConnectTimeout``,
                                        ``ReadTimeout``, ``RequestTimeout``,
                                        ``ConnectionPoolAcquireTimeout``)
``httpx.TooManyRedirects``              :class:`aiosonic.exceptions.MaxRedirects`
``httpx.ResponseNotRead``               :class:`aiosonic.exceptions.ResponseNotRead`
``httpx.StreamConsumed``                :class:`aiosonic.exceptions.StreamConsumed`
``httpx.HTTPError``                     :class:`aiosonic.exceptions.AiosonicError`, the base of every
                                        aiosonic exception. Connection errors such as
                                        ``ConnectionRefusedError`` are ``OSError``, not ``AiosonicError``.
======================================= ================================================================


Differences with httpx
----------------------

- Urls are ``str``, not ``httpx.URL``, and ``response.request`` only has the method and url (its headers
  are empty).
- ``timeout`` takes a number, ``None`` or :class:`aiosonic.timeout.Timeouts`, not ``httpx.Timeout``. A number
  limits connecting, waiting for the response and getting a connection from the pool, not reading the body,
  and the pool timeout can not be changed per request.
- Not supported: ``cookies=``, ``cert=``, ``transport=``, ``limits=``, ``build_request()``, ``send()``,
  ``response.history``, ``response.elapsed``, ``DigestAuth``, netrc and callable auths.
- List values in ``params`` and ``data`` are not expanded into repeated fields; pass a list of tuples to
  ``params`` instead.
- File objects given in ``files`` are closed after they are sent.
- ``aiter_bytes()`` does not decompress over HTTP/2.


Reference
---------

.. autoclass:: aiosonic.httpx_client.AsyncClient
   :members: request, stream, aclose, merge_headers

.. autoclass:: aiosonic.httpx_client.Response
   :members:

.. autoclass:: aiosonic.httpx_client.Request

.. autofunction:: aiosonic.httpx_client.to_timeouts

.. autofunction:: aiosonic.httpx_client.to_proxy
