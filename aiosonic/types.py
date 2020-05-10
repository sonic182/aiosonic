from typing import Union
from typing import Dict
from typing import Sequence
from typing import Tuple
from typing import AsyncIterator
from typing import Iterator

# TYPES
ParamsType = Union[Dict[str, str], Sequence[Tuple[str, str]], ]
#: Data to be sent in requests, allowed types
DataType = Union[str, bytes, dict, tuple, AsyncIterator[bytes],
                 Iterator[bytes], ]
BodyType = Union[str, bytes, AsyncIterator[bytes], Iterator[bytes], ]
ParsedBodyType = Union[bytes, AsyncIterator[bytes], Iterator[bytes], ]
