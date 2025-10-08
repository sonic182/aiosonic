from typing import (
    AsyncIterator,
    Dict,
    Iterator,
    Optional,
    Sequence,
    Tuple,
    TypedDict,
    Union,
)

from aiosonic.multipart import MultipartForm

# TYPES
ParamsType = Union[
    Dict[str, str],
    Sequence[Tuple[str, str]],
]
#: Data to be sent in requests, allowed types
DataType = Union[
    str, bytes, dict, tuple, AsyncIterator[bytes], Iterator[bytes], MultipartForm
]
BodyType = Union[
    str,
    bytes,
    AsyncIterator[bytes],
    Iterator[bytes],
]
ParsedBodyType = Union[
    bytes,
    AsyncIterator[bytes],
    Iterator[bytes],
]


class SSEEvent(TypedDict):
    """SSE event structure."""

    data: str
    event: Optional[str]
    id: Optional[str]
    retry: Optional[int]
