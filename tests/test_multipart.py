import pytest

import aiosonic
from aiosonic.client import MultipartFile, _send_multipart
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
    # Mock data with file
    file_obj = open("tests/files/bar.txt", "rb")
    data = {
        "field1": "value1",
        "file": MultipartFile(file_obj, filename="test.txt", content_type="text/plain"),
    }
    boundary = "test-boundary"
    headers = {}

    # This should precalculate size and set Content-Length header
    body_iter = await _send_multipart(data, boundary, headers)
    assert hasattr(body_iter, "__aiter__")

    # Collect streamed chunks into bytes to validate size
    collected = b""
    async for chunk in body_iter:
        collected += chunk

    assert len(collected) > 0
    assert "Content-Length" in headers
    assert headers["Content-Length"] == str(len(collected))


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
async def test_post_multipart_with_multipartfile_class(http_serv):
    """Test post multipart using MultipartForm with MultipartFile instance."""
    from aiosonic.multipart import MultipartFile

    url = f"{http_serv}/upload_file"

    form = MultipartForm()
    file_obj = open("tests/files/bar.txt", "rb")
    multipart_file = MultipartFile(
        file_obj, filename="custom_bar.txt", content_type="text/plain"
    )
    form.add_field("foo", multipart_file)
    form.add_field("field1", "foo")

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=form)
        assert res.status_code == 200
        assert await res.text() == "bar-foo"


@pytest.mark.asyncio
async def test_post_multipart_with_multipartfile_path(http_serv):
    """Test post multipart using MultipartForm with MultipartFile from file path."""
    from aiosonic.multipart import MultipartFile

    url = f"{http_serv}/upload_file"

    form = MultipartForm()
    multipart_file = MultipartFile(
        "tests/files/bar.txt", filename="custom_bar.txt", content_type="text/plain"
    )
    form.add_field("foo", multipart_file)
    form.add_field("field1", "foo")

    async with aiosonic.HTTPClient() as client:
        res = await client.post(url, data=form)
        assert res.status_code == 200
        assert await res.text() == "bar-foo"


@pytest.mark.asyncio
async def test_multipartfile_lazy_file_opening():
    """Test that MultipartFile with file path doesn't open file until accessed."""
    # Test with file path - file should not be opened until file_obj is accessed
    multipart_file = MultipartFile("tests/files/bar.txt")
    assert multipart_file._file_obj is None  # File not opened yet

    # Access file_obj - should open the file
    with multipart_file.file_obj:
        assert multipart_file._file_obj is not None
        assert not multipart_file._file_obj.closed

    # After context, file should be closed
    assert multipart_file._file_obj.closed

    # Test with file object - should use the provided object
    file_obj = open("tests/files/bar.txt", "rb")
    multipart_file2 = MultipartFile(file_obj)
    assert multipart_file2._file_obj is file_obj  # Uses provided object
    file_obj.close()


@pytest.mark.asyncio
async def test_multipartform_doesnt_open_files_during_construction():
    """Test that MultipartForm doesn't open files during construction, only during sending."""
    # Create MultipartFile with file path
    multipart_file = MultipartFile("tests/files/bar.txt")
    assert multipart_file._file_obj is None  # File not opened yet

    # Create form and add the file
    form = MultipartForm()
    form.add_field("file", multipart_file)

    # File should still not be opened after adding to form
    assert multipart_file._file_obj is None

    # File should be opened when we access file_obj during sending
    # Let's simulate what happens during _generate_chunks
    file_obj = multipart_file.file_obj  # This should open the file
    assert multipart_file._file_obj is not None
    assert not file_obj.closed

    # Clean up
    file_obj.close()


@pytest.mark.asyncio
async def test_request_multipart_value_error():
    """Connection error check."""
    async with aiosonic.HTTPClient() as client:
        with pytest.raises(ValueError):
            await client.post("foo", data=b"foo", multipart=True)
