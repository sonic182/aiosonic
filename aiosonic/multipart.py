import os
from io import IOBase
from os.path import basename
from random import randint
from typing import Optional, Union

from aiosonic.resolver import get_loop

RANDOM_RANGE = (1000, 9999)
_CHUNK_SIZE = 1024 * 1024  # 1mb


class MultipartFile:
    """A class to represent a file in multipart data with metadata.

    This class encapsulates a file-like object along with its filename and content type,
    providing convenient access to file properties such as size.

    Args:
        file_obj (IOBase): The file-like object to be included in multipart data.
        filename (Optional[str]): The name of the file. If not provided, defaults to
            the basename of the file object's name.
        content_type (Optional[str]): The MIME type of the file. If not provided,
            it may be inferred or left unspecified.
    """

    def __init__(
        self,
        file_obj: IOBase,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
    ):
        self.file_obj = file_obj
        self.filename = filename or basename(file_obj.name)
        self.content_type = content_type
        self._size: Optional[int] = None

    @property
    def size(self) -> int:
        """Calculate and cache the file size efficiently."""
        if self._size is None:
            try:
                current_pos = self.file_obj.tell()
                self.file_obj.seek(0, 2)
                self._size = self.file_obj.tell()
                self.file_obj.seek(current_pos)
            except (OSError, AttributeError):
                self._size = 0
        return self._size


class MultipartForm:
    """
    A class to handle multipart form data for HTTP requests.

    Example:

    .. code-block:: python

        import asyncio
        import aiosonic
        from aiosonic.multipart import MultipartForm

        async def upload_file():
            client = aiosonic.HTTPClient()
            form = MultipartForm()

            # Add a text field
            form.add_field("field1", "value1")

            # Add a file to upload
            form.add_file("file1", "path/to/your/file.txt")

            # Make the POST request with MultipartForm directly
            url = "https://your-upload-endpoint.com/upload"
            response = await client.post(url, data=form)

            print("Response Status:", response.status_code)
            response_data = await response.text()
            print("Response Body:", response_data)

        if __name__ == '__main__':
            asyncio.run(upload_file())
    """

    def __init__(self):
        """Initializes an empty list for fields and generates a boundary."""
        self.fields = []
        self.boundary = f"boundary-{randint(*RANDOM_RANGE)}"

    def add_field(
        self, name: str, value: Union[str, IOBase], filename: Optional[str] = None
    ):
        """Adds a field to the multipart form data.

        Args:
            name (str): The name of the field.
            value (Union[str, IOBase]): The value of the field. Can be a string or a file-like object.
            filename (Optional[str]): The name of the file, if the value is a file-like object.
                                      Defaults to the file's name if not provided.
        """
        if isinstance(value, IOBase):
            if not filename:
                filename = os.path.basename(value.name)  # Default to the file's name
            self.fields.append((name, value, filename))
        else:
            self.fields.append((name, value))

    def add_file(self, name: str, file_path: str, filename: Optional[str] = None):
        """Adds a file to the multipart form data.

        The file is opened and it is closed after the request is sent.

        Args:
            name (str): The name of the file field.
            file_path (str): The file path of the file to be added.
            filename (Optional[str]): The name of the file for the target server. defaults to the file's name.
        """
        file = open(file_path, "rb")
        self.add_field(name, file, filename or os.path.basename(file_path))

    async def _read_file(self, file_obj: IOBase):
        loop = get_loop()
        while True:
            data = await loop.run_in_executor(None, file_obj.read, _CHUNK_SIZE)
            if not data:
                break
            yield data

    async def _generate_chunks(self):
        """Yields chunks of the multipart buffer containing all fields asynchronously."""
        for field in self.fields:
            yield (f"--{self.boundary}\r\n").encode()
            if isinstance(field[1], IOBase):
                to_write = (
                    "Content-Disposition: form-data; "
                    + f'name="{field[0]}"; filename="{field[2]}"\r\n\r\n'
                )
                yield to_write.encode()

                # Read the file asynchronously
                async for data in self._read_file(field[1]):
                    yield data
                field[1].close()
            else:
                yield (
                    f'Content-Disposition: form-data; name="{field[0]}"\r\n\r\n'
                ).encode()
                yield field[1].encode() + b"\r\n"

        yield (f"--{self.boundary}--").encode()

    async def get_buffer(self):
        """Returns an asynchronous iterator that generates the constructed multipart buffer."""
        async for chunk in self._generate_chunks():
            yield chunk

    async def get_body_size(self):
        """Calculates the total size of the multipart body and returns it along with the body itself.

        This function asynchronously constructs the body by iterating over the chunks
        generated by the get_buffer method. It accumulates the total size of the body
        in bytes while building the complete body as a byte string.

        Returns:
            tuple: A tuple containing the complete multipart body as bytes and its size in bytes.
        """
        body = b""
        size = 0
        async for chunk in self.get_buffer():
            body += chunk
            size += len(chunk)
        return body, size

    def get_headers(self, size=None):
        """Returns the headers for the multipart form data."""
        headers = {"Content-Type": f"multipart/form-data; boundary={self.boundary}"}
        if size:
            headers["Content-Length"] = str(size)
        return headers
