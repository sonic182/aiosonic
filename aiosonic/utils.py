"""Utils."""
import functools
from typing import Callable
from datetime import datetime, timedelta


class ExpirableCache(object):
    """aiosonic.utils.ExpirableCache class.

    Class used for custom cache decorator, dummy expirable cache based
    on dict structure.

    Params:
        * **size**: max items in dict.
        * **timeout**: Timeout in milliseconds, if it is None,
            there is no timeout.
    """

    def __init__(self, size=512, timeout=None):
        self.cache = {}
        self.timeout = timeout
        self.size = size

    def set(self, key, data):
        if self.timeout:
            expire_at = datetime.utcnow() + timedelta(
                milliseconds=self.timeout)
            self.cache[key] = {
                'value': data,
                'expire_at': expire_at
            }
        else:
            self.cache[key] = data

        if len(self.cache) > self.size:
            self.cache.pop(next(iter(self.cache)))

    def get(self, key):
        data = self.cache.get(key)
        if self.timeout and data:
            if datetime.utcnow() > data['expire_at']:
                del self.cache[key]
                data = None
            else:
                return data['value']
        return data

    def __len__(self):
        return len(self.cache)


def cache_decorator(size: int=512, timeout: int = None) -> Callable:
    """Dummy cache decorator."""
    cache = ExpirableCache(size, timeout)

    def decorator(func):
        def _wrapper(*args):
            key = '-'.join(list(args))
            data = cache.get(key)
            if data:
                return data

            res = func(key)

            cache.set(key, data)
            return res

        _wrapper.cache = cache
        return _wrapper

    return decorator
