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


@pytest.mark.asyncio
async def test_retries_exhausted_on_stale_connections() -> None:
    """Report the last drop when every retry gets another stale keep-alive connection."""
    opened = asyncio.Event()
    connections = []

    async def receive(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connections.append(writer)
        if len(connections) == 3:
            opened.set()
        try:
            await reader.readuntil(b"\r\n\r\n")
            await opened.wait()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            await writer.drain()
            await reader.readuntil(b"\r\n\r\n")
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(receive, "127.0.0.1", 0)
    async with server:
        url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
        async with HTTPClient() as client:
            responses = await asyncio.gather(*[client.get(url) for _ in range(3)])
            assert [await response.text() for response in responses] == ["ok"] * 3
            with pytest.raises(ConnectionDisconnected, match="retried 3 times") as exc_info:
                await client.get(url)

    assert exc_info.value.reused_connection is True
    assert isinstance(exc_info.value.__cause__, ConnectionDisconnected)
    assert exc_info.value.__context__ is None
    assert len(connections) == 3


@pytest.mark.asyncio
async def test_post_see_other_redirect_is_sent_as_get_without_body() -> None:
    """Follow a 303 after a POST with a GET that drops the body and its headers."""
    requests = []

    async def receive(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            requests.append(head + await reader.readexactly(4))
            writer.write(b"HTTP/1.1 303 See Other\r\nLocation: /next\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            requests.append(await reader.readuntil(b"\r\n\r\n"))
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\ndone")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(receive, "127.0.0.1", 0)
    async with server:
        url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/form"
        async with HTTPClient() as client:
            response = await client.post(url, data=b"data", follow=True)
            assert await response.text() == "done"
            assert [r.status_code for r in response.history] == [303]

    first, second = requests
    assert first.startswith(b"POST /form HTTP/1.1\r\n") and first.endswith(b"\r\n\r\ndata")
    assert second.startswith(b"GET /next HTTP/1.1\r\n")
    assert b"content-length" not in second.lower() and b"content-type" not in second.lower()


@pytest.mark.asyncio
async def test_secure_cookies_stay_on_https(ssl_context) -> None:
    """Send a Secure cookie only over https, also after an https to http redirect, and let http not replace it."""
    seen = []
    http_port = []
    set_cookies = {
        "/login": b"Set-Cookie: sid=secret; Secure\r\n",
        "/direct": b"Set-Cookie: sid=forged\r\nSet-Cookie: pref=x; Secure\r\nSet-Cookie: theme=dark\r\n",
    }

    async def receive(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        scheme = "https" if writer.get_extra_info("ssl_object") else "http"
        try:
            while True:
                lines = (await reader.readuntil(b"\r\n\r\n")).decode().split("\r\n")
                path = lines[0].split()[1]
                cookie = next((line.split(": ", 1)[1] for line in lines if line.lower().startswith("cookie:")), None)
                seen.append((scheme, path, cookie))
                if path == "/bounce":
                    head = f"302 Found\r\nLocation: http://127.0.0.1:{http_port[0]}/landing\r\n".encode()
                else:
                    head = b"200 OK\r\n" + set_cookies.get(path, b"")
                writer.write(b"HTTP/1.1 " + head + b"Content-Length: 0\r\n\r\n")
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    https_server = await asyncio.start_server(receive, "127.0.0.1", 0, ssl=ssl_context)
    http_server = await asyncio.start_server(receive, "127.0.0.1", 0)
    async with https_server, http_server:
        http_port.append(http_server.sockets[0].getsockname()[1])
        https_url = f"https://127.0.0.1:{https_server.sockets[0].getsockname()[1]}"
        urls = [f"{https_url}/login", f"http://127.0.0.1:{http_port[0]}/direct", f"{https_url}/check"]
        async with HTTPClient(handle_cookies=True, verify_ssl=False) as client:
            for url in [*urls, f"{https_url}/bounce"]:
                await (await client.get(url, follow=True)).content()

    assert seen == [
        ("https", "/login", None),
        ("http", "/direct", None),
        ("https", "/check", "sid=secret; theme=dark"),
        ("https", "/bounce", "sid=secret; theme=dark"),
        ("http", "/landing", "theme=dark"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "framing, connections_used",
    [
        (b"Transfer-Encoding:  chunked\r\nConnection: close\r\nConnection: Transfer-Encoding\r\n", 2),
        (b"Transfer-Encoding:\tChunked \r\n", 1),
    ],
)
async def test_chunked_response_with_header_whitespace(framing: bytes, connections_used: int) -> None:
    """Read a chunked body despite extra whitespace or case, and honour Connection: close in any repeated header."""
    connections = []

    async def receive(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connections.append(writer)
        try:
            while True:
                await reader.readuntil(b"\r\n\r\n")
                writer.write(b"HTTP/1.1 200 OK\r\n" + framing + b"\r\n3\r\nhel\r\n2\r\nlo\r\n0\r\n\r\n")
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(receive, "127.0.0.1", 0)
    async with server:
        url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
        async with HTTPClient() as client:
            for _ in range(2):
                response = await client.get(url)
                assert response.chunked
                assert await response.content() == b"hello"

    assert len(connections) == connections_used
