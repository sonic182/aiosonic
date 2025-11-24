"""
Tests for DNS caching functionality.
"""

import time
import pytest
import threading
from aiosonic.dns_cache import DNSCache


class TestDNSCache:
    """Test DNS cache functionality."""

    def test_cache_initialization(self):
        """Cache should initialize with correct parameters."""
        cache = DNSCache(ttl=300, max_size=1000)
        assert cache.ttl == 300
        assert cache.max_size == 1000
        assert len(cache) == 0

    def test_cache_set_and_get(self):
        """Cache should store and retrieve entries."""
        cache = DNSCache()
        addresses = [("192.168.1.1", 80)]

        cache.set("example.com", addresses)
        result = cache.get("example.com")

        assert result == addresses

    def test_cache_get_nonexistent_key(self):
        """Getting nonexistent key should return None."""
        cache = DNSCache()
        assert cache.get("nonexistent.com") is None

    def test_cache_ttl_expiration(self):
        """Cache entries should expire after TTL."""
        cache = DNSCache(ttl=1)  # 1 second TTL
        addresses = [("192.168.1.1", 80)]

        cache.set("example.com", addresses)
        assert cache.get("example.com") is not None

        time.sleep(1.1)
        assert cache.get("example.com") is None

    def test_cache_clear(self):
        """Cache should clear all entries."""
        cache = DNSCache()
        cache.set("example.com", [("192.168.1.1", 80)])
        cache.set("test.com", [("192.168.1.2", 80)])

        assert len(cache) == 2
        cache.clear()
        assert len(cache) == 0

    def test_cache_max_size_limit(self):
        """Cache should respect max_size limit with LRU eviction."""
        cache = DNSCache(max_size=3)

        # Add 3 entries
        cache.set("domain1.com", [("192.168.1.1", 80)])
        cache.set("domain2.com", [("192.168.1.2", 80)])
        cache.set("domain3.com", [("192.168.1.3", 80)])

        assert len(cache) == 3

        # Add 4th entry, should evict least recently used
        cache.set("domain4.com", [("192.168.1.4", 80)])
        assert len(cache) == 3

        # domain1 should be evicted (least recently used)
        assert cache.get("domain1.com") is None
        assert cache.get("domain4.com") is not None

    def test_cache_lru_eviction_on_access(self):
        """Accessing an entry should mark it as recently used."""
        cache = DNSCache(max_size=2)

        cache.set("domain1.com", [("192.168.1.1", 80)])
        cache.set("domain2.com", [("192.168.1.2", 80)])

        # Access domain1 to mark it as recently used
        cache.get("domain1.com")

        # Add domain3, should evict domain2 (now least recently used)
        cache.set("domain3.com", [("192.168.1.3", 80)])

        assert cache.get("domain1.com") is not None
        assert cache.get("domain2.com") is None
        assert cache.get("domain3.com") is not None

    def test_cache_statistics(self):
        """Cache should track hits and misses."""
        cache = DNSCache()

        # Initial stats
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        cache.set("example.com", [("192.168.1.1", 80)])

        # Cache hit
        cache.get("example.com")
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 0

        # Cache miss
        cache.get("nonexistent.com")
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_cache_size_tracking(self):
        """Cache should track current size."""
        cache = DNSCache()

        assert cache.get_stats()["size"] == 0

        cache.set("example.com", [("192.168.1.1", 80)])
        assert cache.get_stats()["size"] == 1

        cache.set("test.com", [("192.168.1.2", 80)])
        assert cache.get_stats()["size"] == 2

    def test_cache_reset_stats(self):
        """Cache should allow resetting statistics."""
        cache = DNSCache()
        cache.set("example.com", [("192.168.1.1", 80)])
        cache.get("example.com")

        stats = cache.get_stats()
        assert stats["hits"] == 1

        cache.reset_stats()
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0

    def test_cache_contains(self):
        """Cache should support 'in' operator."""
        cache = DNSCache()

        cache.set("example.com", [("192.168.1.1", 80)])
        assert "example.com" in cache
        assert "nonexistent.com" not in cache

    def test_cache_delete(self):
        """Cache should support deleting entries."""
        cache = DNSCache()
        cache.set("example.com", [("192.168.1.1", 80)])

        assert cache.get("example.com") is not None
        cache.delete("example.com")
        assert cache.get("example.com") is None

    def test_cache_thread_safety(self):
        """Cache should be thread-safe for concurrent access."""
        cache = DNSCache()
        errors = []

        def add_and_get(domain, address):
            try:
                cache.set(domain, [(address, 80)])
                result = cache.get(domain)
                assert result is not None
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(
                target=add_and_get, args=(f"domain{i}.com", f"192.168.1.{i}")
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(cache) == 10

    def test_cache_disable(self):
        """Cache should support being disabled."""
        cache = DNSCache(ttl=300, disabled=True)

        cache.set("example.com", [("192.168.1.1", 80)])
        # When disabled, get should always return None
        assert cache.get("example.com") is None

    def test_cache_with_multiple_addresses(self):
        """Cache should handle multiple addresses for a domain."""
        cache = DNSCache()
        addresses = [
            ("192.168.1.1", 80),
            ("192.168.1.2", 80),
            ("2001:db8::1", 80),
        ]

        cache.set("example.com", addresses)
        result = cache.get("example.com")

        assert result == addresses
        assert len(result) == 3

    def test_cache_custom_ttl(self):
        """Cache should support custom TTL per entry."""
        cache = DNSCache(ttl=10)

        addresses = [("192.168.1.1", 80)]
        cache.set("example.com", addresses, ttl=1)

        assert cache.get("example.com") is not None
        time.sleep(1.1)
        assert cache.get("example.com") is None
