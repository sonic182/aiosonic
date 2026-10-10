.. _http_client_guide:

HTTP client guide
=================

Detailed behavior of the native :class:`aiosonic.HTTPClient`. For the HTTPX-compatible
wrapper, see :ref:`httpx_client`.

Authentication
--------------

- ``auths`` maps hosts to credentials (``"api.example.com"``, or ``"api.example.com:8443"`` to match a port), so a host that is not in the map never gets them. Each value is a ``(user, password)`` tuple, ``BasicAuth``, ``BearerAuth`` or any ``Auth`` subclass. Digest and netrc authentication are not supported.
- A request is authenticated with, in this order: its ``auth=`` argument, the ``user:password@`` part of its url, or the ``auths`` entry of its host. The auth is resolved once, for the host of the original request, so redirects to other hosts do not get it.

Proxies
-------

- ``proxy=Proxy(...)`` sends every request through that proxy.
- ``trust_env=True`` takes the proxy of each request from the environment: ``HTTP_PROXY``, ``HTTPS_PROXY`` or ``ALL_PROXY``, chosen by the scheme of the url, with ``NO_PROXY`` excluding hosts (``example.com``, ``.example.com`` or ``host:port``). Credentials in the proxy url are used as Basic proxy authentication. A ``proxy`` given to the client wins over the environment, and it is ``False`` by default so that the environment never reroutes requests silently.
- Only HTTP proxies are supported, with plain ``http://`` proxy urls.

Unix domain sockets
-------------------

- ``HTTPClient(TCPConnector(uds="/var/run/docker.sock"))`` sends every request through that Unix domain socket instead of resolving the host of the url, which is only used for the ``Host`` header (``await client.get("http://localhost/containers/json")``). It is not available on Windows and can not be combined with proxies.

API defaults
------------

- To send defaults (``base_url``, headers, query params) in every request of an API, use a ``BaseClient`` subclass with ``base_url``, ``default_headers`` and ``default_params``.

Event hooks
-----------

- ``event_hooks`` runs ``"request"`` hooks as ``hook(method, url, headers)`` and ``"response"`` hooks as ``hook(response)``, sync or async, on every send, including redirects and retries. Request hooks get the live headers, including ``Authorization`` and ``Cookie``, so a hook that adds a header must be idempotent and a logging hook should not print them.

Response details
----------------

- ``response.history`` lists the redirect responses followed to get the response, oldest first. They are already closed, so with ``stream=True`` their bodies are not available.
- ``response.elapsed`` is a ``timedelta`` with the time from sending the request until the response was received, including its body unless ``stream=True``. Every response of ``history`` has its own.
- ``response.links`` parses the ``Link`` headers into a dict by ``rel`` (or by url when there is none), each value with its ``url`` and parameters, e.g. ``response.links["next"]["url"]`` for pagination.

Status errors
-------------

- ``raise_for_status()`` raises ``HTTPStatusError`` (an ``AiosonicError``) for 4xx and 5xx responses; 3xx responses that were not followed do not raise.

Streaming and timeouts
----------------------

- ``stream()`` releases the connection when the block ends, even if the body was not fully read.
- ``iter_bytes()`` decompresses gzip and deflate bodies, but not over HTTP/2; ``read_chunks()`` keeps returning the bytes as received.
- ``timeouts.sock_read`` only covers waiting for the status line, not the body; the body of a ``stream()`` response has no read timeout, so a stalled server holds its connection until the response is closed.

Client cleanup
--------------

- ``async with HTTPClient()`` closes the connections of the connector the client created when the block ends. A connector given with ``HTTPClient(connector)`` is not closed, as it may be shared; call ``await connector.cleanup()`` or ``await client.aclose()`` for it.
- ``await client.aclose()`` does not wait for responses that are still being read: their connections are closed, so reading them afterwards fails. The client can still be used afterwards, as connections are opened again when needed.

