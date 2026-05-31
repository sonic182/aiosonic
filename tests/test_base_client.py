import pytest

from aiosonic import BaseClient, HTTPClient


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_wrapper_get_http_serv(http_serv):
    class TextClient(BaseClient):
        base_url = http_serv

        async def process_response(self, response):
            return (await response.text()).strip()

    client = TextClient()

    response = await client.get("/")
    assert response == "Hello, world"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_wrapper_delete_http_serv(http_serv):
    class RawClient(BaseClient):
        base_url = http_serv

    client = RawClient()

    response = await client.delete("/delete")
    assert response.status_code == 200
    assert (await response.text()).strip() == "deleted"


def test_inject_http_client():
    injected = HTTPClient()
    client = BaseClient(http_client=injected)
    assert client.client is injected


def test_default_http_client_created():
    client = BaseClient()
    assert isinstance(client.client, HTTPClient)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_unsupported_method(http_serv):
    class RawClient(BaseClient):
        base_url = http_serv

    client = RawClient()
    with pytest.raises(ValueError, match="not supported"):
        await client.request("INVALID", "/")


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_post_method(http_serv):
    class RawClient(BaseClient):
        base_url = http_serv

    client = RawClient()
    response = await client.post("/post")
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_put_method(http_serv):
    class RawClient(BaseClient):
        base_url = http_serv

    client = RawClient()
    response = await client.put("/put-test")
    assert response.status_code in (200, 404, 405)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_patch_method(http_serv):
    class RawClient(BaseClient):
        base_url = http_serv

    client = RawClient()
    response = await client.patch("/patch-test")
    assert response.status_code in (200, 404, 405)
