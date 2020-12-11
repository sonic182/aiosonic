"""Utils."""
from typing import Callable


def cache_decorator(size: int=512) -> Callable:
    """Dummy cache decorator."""
    _cache = {}

    def decorator(func):
        def _wrapper(key):
            if key in _cache:
                return _cache[key]

            _cache[key] = res = func(key)

            if len(_cache) > size:
                _cache.pop(next(iter(_cache)))
            return res

        _wrapper.cache = _cache
        return _wrapper

    return decorator
