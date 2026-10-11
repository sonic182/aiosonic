"""Exercise request serialization through the public client and a raw HTTP peer."""

import asyncio
from typing import Optional

import pytest

from aiosonic import HTTPClient, VERSION
from aiosonic.exceptions import ConnectionDisconnected
from aiosonic.proxy import Proxy


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["default", "custom_headers", "authenticated_proxy"])
async def test_request_headers_and_query_on_wire(mode: str) -> None:
    """Preserve default bytes, custom overrides, and proxy credentials across requests."""
    requests = []

    async def receive(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            for _ in range(2):
                requests.append(await reader.readuntil(b"\r\n\r\n"))
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(receive, "127.0.0.1", 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        proxy: Optional[Proxy] = None
        headers = None
        if mode == "authenticated_proxy":
            proxy = Proxy(origin, "user:password")
            origin = "http://destination.example:8080"
        elif mode == "custom_headers":
            headers = {"User-Agent": "wire-test", "X-Test": "present"}

        async with HTTPClient(proxy=proxy) as client:
            for value in ["first value", "second/value"]:
                response = await client.get(origin + "/resource?existing=1", params={"added": value}, headers=headers)
                assert response.status_code == 200
                assert await response.content() == b"ok"

    assert len(requests) == 2
    for raw, query in zip(requests, ["first+value", "second%2Fvalue"]):
        target = f"/resource?existing=1&added={query}"
        if proxy:
            target = origin + target
        assert raw.split(b"\r\n", 1)[0] == f"GET {target} HTTP/1.1".encode()
        fields = dict(line.split(b": ", 1) for line in raw.split(b"\r\n")[1:-2])
        assert fields[b"HOST"] == origin.removeprefix("http://").encode()
        assert fields[b"Connection"] == b"keep-alive"
        assert fields[b"User-Agent"] == (b"wire-test" if headers else f"aiosonic/{VERSION}".encode())
        if headers:
            assert fields[b"X-Test"] == b"present"
        if proxy:
            assert fields[b"Proxy-Connection"] == b"keep-alive"
            assert fields[b"Proxy-Authorization"] == b"Basic dXNlcjpwYXNzd29yZA=="
        else:
            assert b"Proxy-Authorization" not in fields


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case, retried",
    [("get_reused", True), ("post_reused", False), ("put_iterator_body", False), ("fresh_connection", False)],
)
async def test_retry_on_dropped_connection(case: str, retried: bool) -> None:
    """Send again only idempotent, replayable requests whose reused keep-alive connection dropped."""
    connections = []

    async def receive(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connections.append(writer)
        try:
            if len(connections) == 1 and case != "fresh_connection":
                await reader.readuntil(b"\r\n\r\n")
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
                await writer.drain()
                await reader.readuntil(b"\r\n\r\n")
            elif len(connections) > 1:
                await reader.readuntil(b"\r\n\r\n")
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 7\r\n\r\nretried")
                await writer.drain()
            else:
                await reader.readuntil(b"\r\n\r\n")
        finally:
            writer.close()
            await writer.wait_closed()

    def chunks():
        yield b"body"

    server = await asyncio.start_server(receive, "127.0.0.1", 0)
    async with server:
        url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
        async with HTTPClient() as client:
            if case != "fresh_connection":
                assert await (await client.get(url)).text() == "ok"
            requests = {
                "get_reused": lambda: client.get(url),
                "post_reused": lambda: client.post(url, data=b"x"),
                "put_iterator_body": lambda: client.put(url, data=chunks()),
                "fresh_connection": lambda: client.get(url),
            }
            if retried:
                assert await (await requests[case]()).text() == "retried"
            else:
                with pytest.raises(ConnectionDisconnected) as exc_info:
                    await requests[case]()
                assert exc_info.value.reused_connection is (case != "fresh_connection")

    assert len(connections) == (2 if retried else 1)
