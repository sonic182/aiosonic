from typing import AsyncIterator, Dict, Iterator, Sequence, Tuple, Union
from aiosonic.multipart import MultipartForm

# TYPES
ParamsType = Union[
    Dict[str, str],
    Sequence[Tuple[str, str]],
]
#: Data to be sent in requests, allowed types
DataType = Union[
    str,
    bytes,
    dict,
    tuple,
    AsyncIterator[bytes],
    Iterator[bytes],
    MultipartForm
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
