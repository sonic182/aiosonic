import base64
from contextlib import AsyncExitStack

import pytest

from aiosonic.exceptions import ConnectionPoolAcquireTimeout, HTTPStatusError, ResponseNotRead, StreamConsumed
from aiosonic.httpx_client import AsyncClient, Request, Response


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_defaults_merge_and_sync_body(http_serv):
    async with AsyncClient(
        base_url=http_serv,
        headers={"X-Default": "one", "X-Other": "keep"},
        params={"foo": "from_default"},
        auth=("user", "pass"),
    ) as client:
        response = await client.get("/headers", headers={"x-default": "two"})
        assert response.is_success
        assert response.http_version == "HTTP/1.1"
        sent = response.raise_for_status().json()
        assert sent["x-default"] == "two"
        assert sent["x-other"] == "keep"
        assert sent["authorization"] == "Basic " + base64.b64encode(b"user:pass").decode()

        response = await client.get("/", params={"foo": "override"})
        assert response.text == "override"
        assert response.content == b"override"

        response = await client.get("/headers", auth=None)
        assert "authorization" not in response.json()
    assert client.is_closed


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_status_errors_and_redirects(http_serv):
    async with AsyncClient(base_url=http_serv) as client:
        response = await client.get("/status", params={"code": "404"})
        with pytest.raises(HTTPStatusError) as exc_info:
            response.raise_for_status()
        assert exc_info.value.response is response
        assert "Client error '404 Not Found'" in str(exc_info.value)

        response = await client.get("/get_redirect")
        assert response.status_code == 302
        assert response.is_redirect
        with pytest.raises(HTTPStatusError):
            response.raise_for_status()

        response = await client.get("/get_redirect", follow_redirects=True)
        assert response.status_code == 200
        assert response.text == "Hello, world"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_request_bodies(http_serv):
    async with AsyncClient(base_url=http_serv) as client:
        assert (await client.post("/post", data={"foo": "form"})).text == "form"
        assert (await client.post("/post", content=b"raw")).text == "raw"
        assert (await client.post("/post_json", json={"foo": "json"})).text == "json"
        response = await client.post(
            "/upload_file",
            data={"field1": "value1"},
            files={"foo": ("foo.txt", b"file content", "text/plain")},
        )
        assert response.text == "file content-value1"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_stream(http_serv):
    async with AsyncClient(base_url=http_serv) as client:
        async with client.stream("GET", "/chunked") as response:
            with pytest.raises(ResponseNotRead):
                response.content
            assert "".join([text async for text in response.aiter_text()]) == "foobar"
            with pytest.raises(StreamConsumed):
                await response.aread()

        async with client.stream("GET", "/gzip") as response:
            assert await response.aread() == b"Hello, world"
            assert response.text == "Hello, world"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_event_hooks(http_serv):
    seen = []

    def on_request(request):
        assert isinstance(request, Request)
        request.headers["X-Hook"] = "added"

    async def on_response(response):
        assert isinstance(response, Response)
        seen.append((response.request.method, response.status_code))

    async with AsyncClient(
        base_url=http_serv, event_hooks={"request": [on_request], "response": [on_response]}
    ) as client:
        response = await client.get("/headers")

    assert response.json()["x-hook"] == "added"
    assert seen == [("GET", 200)]


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_timeout_limits_waiting_for_pool(http_serv):
    async with AsyncClient(base_url=http_serv, timeout=0.5) as client:
        async with AsyncExitStack() as stack:
            for _ in range(30):
                await stack.enter_async_context(client.stream("GET", "/random"))
            with pytest.raises(ConnectionPoolAcquireTimeout):
                await client.get("/")
        assert (await client.get("/")).text == "Hello, world"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_proxy_url_credentials(http_serv, proxy_serv):
    proxy_url, auth = proxy_serv
    proxy = proxy_url.replace("://", f"://{auth}@")
    async with AsyncClient(proxy=proxy) as client:
        response = await client.get(http_serv)
    assert response.text == "Hello, world"
