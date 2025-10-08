import os
from io import IOBase
from os.path import basename
from random import randint
from typing import Optional, Union, cast

from aiosonic.resolver import get_loop

RANDOM_RANGE = (1000, 9999)
_CHUNK_SIZE = 1024 * 1024  # 1mb


class MultipartFile:
    """A class to represent a file in multipart data with metadata.

    This class encapsulates a file path or file object along with its filename and content type,
    providing convenient access to file properties such as size.

    Args:
        file_path_or_obj (Union[str, IOBase]): Path to file or opened file object for multipart data.
        filename (Optional[str]): The name of the file. If not provided, defaults to
            the basename of the file path or file object's name.
        content_type (Optional[str]): The MIME type of the file. If not provided,
            it may be inferred or left unspecified.
    """

    def __init__(
        self,
        file_path_or_obj: Union[str, IOBase],
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
    ):
        if isinstance(file_path_or_obj, str):
            self.file_path: Optional[str] = file_path_or_obj
            self._file_obj: Optional[IOBase] = None
            self.filename = filename or basename(file_path_or_obj)
        else:
            self.file_path = None
            self._file_obj = file_path_or_obj
            self.filename = filename or str(getattr(file_path_or_obj, "name", "file"))
        self.content_type = content_type
        self._size: Optional[int] = None

    @property
    def file_obj(self) -> IOBase:
        """Return the file object, opening it if necessary."""
        if self._file_obj is None and self.file_path is not None:
            self._file_obj = open(self.file_path, "rb")
        return cast(IOBase, self._file_obj)

    @property
    def size(self) -> int:
        """Calculate and cache the file size efficiently."""
        if self._size is None:
            if self.file_path is not None:
                # We have a file path, use os.path.getsize for efficiency
                try:
                    self._size = os.path.getsize(self.file_path)
                except OSError:
                    self._size = 0
            else:
                # We have a file object, use seek/tell
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
        from aiosonic.multipart import MultipartForm, MultipartFile

        async def upload_file():
            client = aiosonic.HTTPClient()
            form = MultipartForm()

            # Add a text field
            form.add_field("field1", "value1")

            # Add a file to upload using file path
            form.add_file("file1", "path/to/your/file.txt")

            # Add a file using MultipartFile for more control (with file path)
            multipart_file = MultipartFile("img.png", filename="custom.png", content_type="image/png")
            form.add_field("image", multipart_file)

            # Or with an already opened file object (caller responsible for closing)
            file_obj = open("path/to/your/document.pdf", "rb")
            multipart_file2 = MultipartFile(file_obj, filename="doc.pdf", content_type="application/pdf")
            form.add_field("document", multipart_file2)
            # Close the file after the request if needed
            # file_obj.close()

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
        self,
        name: str,
        value: Union[str, IOBase, MultipartFile],
        filename: Optional[str] = None,
    ):
        """Adds a field to the multipart form data.

        Args:
            name (str): The name of the field.
            value (Union[str, IOBase, MultipartFile]): Field value: str, IOBase, or MultipartFile.
            filename (Optional[str]): File name if value is file-like or MultipartFile.
                                      Defaults to the file's name if not provided.
        """
        if isinstance(value, MultipartFile):
            if not filename:
                filename = value.filename
            self.fields.append((name, value, filename))
        elif isinstance(value, IOBase):
            if not filename:
                filename = os.path.basename(
                    getattr(value, "name", "file")
                )  # Default to the file's name
            self.fields.append((name, value, filename))
        else:
            self.fields.append((name, value))

    def add_file(self, name: str, file_path: str, filename: Optional[str] = None):
        """Adds a file to the multipart form data.

        The file is opened and it is closed after the request is sent.

        Args:
            name (str): The name of the file field.
            file_path (str): The file path of the file to be added.
            filename (Optional[str]): File name for server. Defaults to file's name.
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
            if isinstance(field[1], (IOBase, MultipartFile)):
                to_write = (
                    "Content-Disposition: form-data; "
                    + f'name="{field[0]}"; filename="{field[2]}"\r\n\r\n'
                )
                yield to_write.encode()

                # Read the file asynchronously
                file_obj = field[1].file_obj if isinstance(field[1], MultipartFile) else field[1]
                async for data in self._read_file(file_obj):
                    yield data
                file_obj.close()
            else:
                yield (f'Content-Disposition: form-data; name="{field[0]}"\r\n\r\n').encode()
                yield field[1].encode() + b"\r\n"

        yield (f"--{self.boundary}--").encode()

    async def get_buffer(self):
        """Returns an asynchronous iterator that generates the constructed multipart buffer."""
        async for chunk in self._generate_chunks():
            yield chunk

    async def get_body_size(self):
        """Calculate total multipart body size and return with body.

        This function asynchronously constructs the body by iterating over the chunks
        generated by the get_buffer method. It accumulates the total size of the body
        in bytes while building the complete body as a byte string.

        Returns:
            tuple: (multipart body bytes, size).
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
