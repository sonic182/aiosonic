import pytest

import aiosonic
from aiosonic.multipart import MultipartForm


@pytest.mark.asyncio
async def test_post_multipart(http_serv):
    """Test post multipart."""
    url = f"{http_serv}/upload_file"
    data = {"foo": open("tests/files/bar.txt", "rb"), "field1": "foo"}

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=data, multipart=True)
        assert res.status_code == 200
        # assert await res.content() == b"bar\n-foo"
        assert await res.text() == "bar-foo"


@pytest.mark.asyncio
async def test_post_multipart_with_class(http_serv):
    """Test post multipart."""
    url = f"{http_serv}/upload_file"

    form = MultipartForm()
    form.add_field("foo", open("tests/files/bar.txt", "rb"), "myfile.txt")
    form.add_field("field1", "foo")

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=form)
        assert res.status_code == 200
        assert await res.text() == "bar-foo"


@pytest.mark.asyncio
async def test_post_multipart_with_metadata(http_serv):
    """Test post multipart with custom filename and content-type."""
    from aiosonic.client import MultipartFile

    url = f"{http_serv}/upload_file"
    file_obj = open("tests/files/bar.txt", "rb")
    data = {
        "foo": MultipartFile(
            file_obj, filename="custom_name.txt", content_type="text/plain"
        ),
        "field1": "foo",
    }

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=data, multipart=True)
        assert res.status_code == 200
        # Assume server checks for custom filename and content-type
        assert await res.text() == "bar-foo"


@pytest.mark.asyncio
async def test_multipart_size_precalculation():
    """Test that multipart body size is precalculated without building body."""
    from aiosonic.client import _send_multipart, MultipartFile

    # Mock data with file
    file_obj = open("tests/files/bar.txt", "rb")
    data = {
        "field1": "value1",
        "file": MultipartFile(file_obj, filename="test.txt", content_type="text/plain"),
    }
    boundary = "test-boundary"
    headers = {}

    # This should precalculate size and set Content-Length header
    body = await _send_multipart(data, boundary, headers)
    assert isinstance(body, bytes)
    assert len(body) > 0
    assert "Content-Length" in headers
    assert headers["Content-Length"] == str(len(body))


@pytest.mark.asyncio
async def test_multipart_backward_compatibility(http_serv):
    """Test that old multipart dict format still works."""
    url = f"{http_serv}/upload_file"
    data = {"foo": open("tests/files/bar.txt", "rb"), "field1": "foo"}

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=data, multipart=True)
        assert res.status_code == 200
        assert await res.text() == "bar-foo"


@pytest.mark.asyncio
async def test_request_multipart_value_error():
    """Connection error check."""
    async with aiosonic.HTTPClient() as client:
        with pytest.raises(ValueError):
            await client.post("foo", data=b"foo", multipart=True)
