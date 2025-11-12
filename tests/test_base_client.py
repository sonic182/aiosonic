import pytest

from aiosonic import BaseClient


@pytest.mark.asyncio
async def test_wrapper_get_http_serv(http_serv):
    class TextClient(BaseClient):
        base_url = http_serv

        async def process_response(self, response):
            return (await response.text()).strip()

    client = TextClient()

    response = await client.get("/")
    assert response == "Hello, world"


@pytest.mark.asyncio
async def test_wrapper_delete_http_serv(http_serv):
    class RawClient(BaseClient):
        base_url = http_serv

    client = RawClient()

    response = await client.delete("/delete")
    assert response.status_code == 200
    assert (await response.text()).strip() == "deleted"
