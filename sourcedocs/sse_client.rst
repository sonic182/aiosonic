.. _sse_client:

SSE Client
==========

The Server-Sent Events (SSE) client allows consuming a stream of events over a single HTTP connection.

This module exposes the high-level :class:`aiosonic.SSEClient` API as well as low-level connection objects
used internally. The client is designed to be used with async context managers and async iteration:

Key features
------------

- Connect to standard SSE endpoints that return ``text/event-stream``.
- Automatic reconnection support with configurable retry delay and Last-Event-ID handling.
- Event parsing compatible with the SSE specification (``data``, ``event``, ``id``, ``retry`` fields).
- Deduplication of events by ``id`` and by last yielded ``data`` to reduce duplicate deliveries after reconnects.

Usage overview
--------------

Typical usage follows one of two patterns:

- Await the connect awaitable to obtain an ``SSEConnection`` and iterate over events:

.. code-block:: python

    from aiosonic import SSEClient
    import asyncio

    async def main():
        client = SSEClient()
        sse_conn = await client.connect("https://example.com/stream")
        async for event in sse_conn:
            print(event["event"], event["data"])  # event is a dict with keys: data, event, id, retry

        await sse_conn.close()

    asyncio.run(main())

- Use nested async context managers (recommended) for automatic cleanup:

.. code-block:: python

    async with SSEClient() as client:
        async with client.connect("https://example.com/stream") as sse_conn:
            async for event in sse_conn:
                print(event["data"])  # handle events

Parameters and configuration
----------------------------

The :meth:`aiosonic.SSEClient.connect` method accepts the same general parameters as the HTTP client, with
additional SSE-specific options:

- ``reconnect`` (bool): automatically reconnect when the server closes the stream. Default: ``True``.
- ``retry_delay`` (int): milliseconds to wait between reconnect attempts. Default: ``3000`` (3 seconds).
- ``keep_connection`` (bool): if ``True`` the underlying TCP connection will be kept open even after the
  SSE stream ends. This is experimental and may be unsafe with some servers.

Event parsing and semantics
---------------------------

Each yielded event is a mapping with the following keys:

- ``data`` (str): the combined ``data`` lines for the event (newlines preserved).
- ``event`` (Optional[str]): the event type if provided by the server.
- ``id`` (Optional[str]): the event id. Used for deduplication and Last-Event-ID when reconnecting.
- ``retry`` (Optional[int]): if set, indicates the server-suggested retry interval in milliseconds.

The implementation follows the SSE spec for line parsing. Malformed lines or invalid ``retry`` values will
raise :class:`aiosonic.exceptions.SSEParsingError`.

Error handling and reconnection
------------------------------

- Initial connection failures raise :class:`aiosonic.exceptions.SSEConnectionError` unless ``reconnect`` is
  enabled, in which case the client will retry using the configured ``retry_delay``.
- While iterating, transient socket or parse errors will either trigger reconnection (if enabled) or raise
  :class:`aiosonic.exceptions.SSEConnectionError`.
- When reconnecting, the client will include the last seen event id in the ``Last-Event-ID`` header, and
  deduplicate events by id and by the last yielded ``data`` to minimize duplicate deliveries.

Examples
--------

OpenAI-style streaming with a POST and JSON body::

    async with SSEClient() as client:
        async with client.connect(
            "https://api.openai.com/v1/chat/completions",
            method="POST",
            json={"model": "gpt-4", "messages": [...], "stream": True},
            headers={"Authorization": "Bearer <token>"},
        ) as sse_conn:
            async for event in sse_conn:
                # event['data'] contains the partial JSON payloads
                print(event['data'])

Notes and tips
--------------

- If you need precise control over reconnection or want to implement custom retry backoff, set
  ``reconnect=False`` and handle reconnection logic in your application.
- For idempotent processing across restarts, persist the last-seen event id reported in ``event['id']``.

.. automodule:: aiosonic.sse_client
    :members:
    :undoc-members:
    :show-inheritance:
