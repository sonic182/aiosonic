"""Response body decompression helpers."""

from typing import Optional
from zlib import MAX_WBITS, decompressobj

from aiosonic.exceptions import DecompressionError

DEFAULT_MAX_DECOMPRESSED_SIZE = 100 * 1024 * 1024
GZIP_WBITS = MAX_WBITS | 16
DEFLATE_WBITS = MAX_WBITS
ENCODING_WBITS = {"gzip": GZIP_WBITS, "deflate": DEFLATE_WBITS}


class BoundedDecompressor:
    """Incremental decompressor which limits the size of its output.

    Args:
        wbits (int): The ``wbits`` value of the zlib decompressor, see :data:`GZIP_WBITS` and :data:`DEFLATE_WBITS`.
        max_size (int): Maximum number of bytes the decompressed data may have.
    """

    def __init__(self, wbits: int, max_size: int):
        self._decompressor = decompressobj(wbits)
        self._max_size = max_size
        self._produced = 0

    def _account(self, out: bytes) -> bytes:
        self._produced += len(out)
        if self._produced > self._max_size:
            raise DecompressionError(f"decompressed response body exceeds the {self._max_size} byte limit")
        return out

    def feed(self, data: bytes) -> bytes:
        """Decompress a chunk of data.

        Args:
            data (bytes): The next chunk of compressed data.

        Returns:
            bytes: The data decompressed from the chunk.

        Raises:
            DecompressionError: If the total output would exceed ``max_size``.
        """
        return self._account(self._decompressor.decompress(data, self._max_size - self._produced + 1))

    def flush(self) -> bytes:
        """Get the data still buffered once all the chunks were fed.

        Returns:
            bytes: The remaining decompressed data.

        Raises:
            DecompressionError: If the total output would exceed ``max_size``.
        """
        return self._account(self._decompressor.flush())


def decompress_bounded(data: bytes, wbits: int, max_size: int) -> bytes:
    """Decompress a whole body, limiting the size of its output.

    Args:
        data (bytes): The compressed data.
        wbits (int): The ``wbits`` value of the zlib decompressor.
        max_size (int): Maximum number of bytes the decompressed data may have.

    Returns:
        bytes: The decompressed data.

    Raises:
        DecompressionError: If the output would exceed ``max_size``.
    """
    decompressor = BoundedDecompressor(wbits, max_size)
    return decompressor.feed(data) + decompressor.flush()


def get_decompressor(encoding: str, max_size: int) -> Optional[BoundedDecompressor]:
    """Get the incremental decompressor of a ``Content-Encoding``.

    Args:
        encoding (str): The ``Content-Encoding`` value of the response.
        max_size (int): Maximum number of bytes the decompressed data may have.

    Returns:
        Optional[BoundedDecompressor]: The decompressor, or None when the encoding is not gzip or deflate.
    """
    wbits = ENCODING_WBITS.get(encoding)
    return BoundedDecompressor(wbits, max_size) if wbits is not None else None


def decompress_body(data: bytes, encoding: str, max_size: int) -> bytes:
    """Decompress a whole body according to its ``Content-Encoding``.

    Args:
        data (bytes): The body as received.
        encoding (str): The ``Content-Encoding`` value of the response.
        max_size (int): Maximum number of bytes the decompressed data may have.

    Returns:
        bytes: The decompressed data, or ``data`` itself when the encoding is not gzip or deflate.

    Raises:
        DecompressionError: If the output would exceed ``max_size``.
    """
    wbits = ENCODING_WBITS.get(encoding)
    return decompress_bounded(data, wbits, max_size) if wbits is not None else data
