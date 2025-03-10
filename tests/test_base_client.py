import pytest

from aiosonic.base_client import AioSonicBaseClient


@pytest.mark.asyncio
async def test_wrapper_get_http_serv(http_serv):
    """
    Test GET method:
      - Verify that a relative URL is correctly combined with base_url.
      - Ensure a GET request to "/" returns a non-empty response.
    """

    class TestWrapperClient(AioSonicBaseClient):
        base_url = http_serv
        pass

    client = TestWrapperClient()

    response = await client.get("/")
    assert response.strip() == "Hello, World!"


@pytest.mark.asyncio
async def test_wrapper_delete_http_serv(http_serv):
    """
    Test DELETE method on /delete endpoint:
      - Verify that a DELETE request returns "deleted".
    """

    class TestWrapperClient2(AioSonicBaseClient):
        base_url = http_serv
        pass

    client = TestWrapperClient2()

    response = await client.delete("/delete")
    assert isinstance(response, str), "Expected a string response"
    assert (
        response.strip() == "deleted"
    ), f"Expected 'deleted', got '{response.strip()}'"
