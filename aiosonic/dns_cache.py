"""DNS resolution cache with TTL and LRU eviction."""

import time
import threading
from typing import Dict, List, Tuple, Optional, Any
from collections import OrderedDict


class DNSCache:
    """
    Thread-safe DNS cache with TTL and LRU eviction.

    Caches DNS resolution results with configurable time-to-live (TTL)
    and maximum size. Uses Least Recently Used (LRU) eviction policy
    when the cache reaches maximum capacity.

    Args:
        ttl: Time-to-live for cache entries in seconds (default: 300)
        max_size: Maximum number of entries in cache (default: 1000)
        disabled: If True, cache is disabled and always returns None (default: False)

    Attributes:
        ttl: Cache entry TTL
        max_size: Maximum cache size
        disabled: Whether cache is disabled
    """

    def __init__(self, ttl: int = 300, max_size: int = 1000, disabled: bool = False):
        """Initialize DNS cache."""
        self.ttl = ttl
        self.max_size = max_size
        self.disabled = disabled

        # Use OrderedDict to track LRU order
        self._cache: OrderedDict[str, Tuple[List[Tuple[str, int]], float]] = (
            OrderedDict()
        )
        self._lock = threading.Lock()

        # Statistics
        self._hits = 0
        self._misses = 0

    def set(
        self, domain: str, addresses: List[Tuple[str, int]], ttl: Optional[int] = None
    ) -> None:
        """
        Store DNS resolution result in cache.

        Args:
            domain: Domain name
            addresses: List of (host, port) tuples
            ttl: Optional custom TTL for this entry (uses default if not specified)
        """
        if self.disabled:
            return

        use_ttl = ttl if ttl is not None else self.ttl
        timestamp = time.time()

        with self._lock:
            # Remove if exists to update order
            if domain in self._cache:
                del self._cache[domain]

            # Check if we need to evict
            if len(self._cache) >= self.max_size:
                # Remove least recently used (first item)
                self._cache.popitem(last=False)

            # Add new entry
            self._cache[domain] = (addresses, timestamp + use_ttl)

    def get(self, domain: str) -> Optional[List[Tuple[str, int]]]:
        """
        Retrieve DNS resolution result from cache.

        Returns cached addresses if entry exists and hasn't expired,
        None otherwise.

        Args:
            domain: Domain name

        Returns:
            List of (host, port) tuples or None if not cached/expired
        """
        if self.disabled:
            self._misses += 1
            return None

        with self._lock:
            if domain not in self._cache:
                self._misses += 1
                return None

            addresses, expiry = self._cache[domain]

            # Check if entry has expired
            if time.time() > expiry:
                del self._cache[domain]
                self._misses += 1
                return None

            # Move to end to mark as recently used
            self._cache.move_to_end(domain)
            self._hits += 1

            return addresses

    def delete(self, domain: str) -> None:
        """
        Remove a specific entry from cache.

        Args:
            domain: Domain name
        """
        with self._lock:
            self._cache.pop(domain, None)

    def clear(self) -> None:
        """Clear all entries from cache."""
        with self._lock:
            self._cache.clear()

    def __contains__(self, domain: str) -> bool:
        """Check if domain is in cache and not expired."""
        result = self.get(domain)
        return result is not None

    def __len__(self) -> int:
        """Return current number of valid entries in cache."""
        with self._lock:
            # Clean up expired entries
            now = time.time()
            expired = [
                domain for domain, (_, expiry) in self._cache.items() if now > expiry
            ]
            for domain in expired:
                del self._cache[domain]

            return len(self._cache)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with keys:
                - hits: Number of cache hits
                - misses: Number of cache misses
                - size: Current number of entries
                - max_size: Maximum cache size
                - hit_rate: Hit rate as percentage (0-100)
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0

        with self._lock:
            current_size = len(self._cache)

        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": current_size,
            "max_size": self.max_size,
            "hit_rate": hit_rate,
        }

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        self._hits = 0
        self._misses = 0
