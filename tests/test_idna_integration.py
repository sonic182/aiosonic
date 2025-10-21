"""
Integration tests for IDNA and DNS caching in resolver.
"""

import pytest
import asyncio
from aiosonic.resolver import ThreadedResolver
from aiosonic.dns_cache import DNSCache


class TestIDNAIntegration:
    """Integration tests for IDNA support in resolver."""

    @pytest.mark.asyncio
    async def test_resolver_with_ascii_domain(self):
        """Resolver should handle ASCII domains."""
        resolver = ThreadedResolver()
        result = await resolver.resolve("example.com", 80)

        assert result is not None
        assert len(result) > 0
        assert result[0]["hostname"] == "example.com"
        assert result[0]["port"] == 80

        await resolver.close()

    @pytest.mark.asyncio
    async def test_resolver_with_idna_domain(self):
        """Resolver should handle internationalized domains with IDNA encoding."""
        resolver = ThreadedResolver()

        # Test with a domain that requires IDNA encoding
        # Note: This will work if the domain resolves, otherwise it will fail with OSError
        try:
            result = await resolver.resolve("münchen.de", 80)
            assert result is not None
            assert len(result) > 0
            # The hostname should be preserved as the original Unicode
            assert result[0]["hostname"] == "münchen.de"
        except OSError:
            # Domain might not exist or not be reachable
            pytest.skip("Domain münchen.de not resolvable")

        await resolver.close()

    @pytest.mark.asyncio
    async def test_resolver_with_cache(self):
        """Resolver should cache DNS results."""
        cache = DNSCache(ttl=300)
        resolver = ThreadedResolver(cache=cache)

        # First lookup - should miss cache
        result1 = await resolver.resolve("example.com", 80)
        stats1 = cache.get_stats()
        assert stats1["misses"] >= 1

        # Second lookup - should hit cache
        result2 = await resolver.resolve("example.com", 80)
        stats2 = cache.get_stats()
        assert stats2["hits"] >= 1

        # Results should be the same
        assert result1[0]["host"] == result2[0]["host"]

        await resolver.close()

    @pytest.mark.asyncio
    async def test_resolver_cache_disabled(self):
        """Resolver should work with cache disabled."""
        resolver = ThreadedResolver(use_cache=False)

        result = await resolver.resolve("example.com", 80)
        assert result is not None
        assert len(result) > 0

        await resolver.close()

    @pytest.mark.asyncio
    async def test_resolver_cache_stats(self):
        """Resolver cache statistics should be accurate."""
        cache = DNSCache()
        resolver = ThreadedResolver(cache=cache)

        # Perform multiple lookups
        await resolver.resolve("example.com", 80)
        await resolver.resolve("example.com", 80)
        await resolver.resolve("example.org", 80)

        stats = cache.get_stats()

        # Should have at least 1 hit (second example.com lookup)
        assert stats["hits"] >= 1
        # Should have at least 2 misses (first example.com and example.org)
        assert stats["misses"] >= 2

        await resolver.close()

    @pytest.mark.asyncio
    async def test_resolver_handles_invalid_idna(self):
        """Resolver should gracefully handle invalid IDNA domains."""
        resolver = ThreadedResolver()

        # Domain with invalid characters should still attempt resolution
        # (encode_idna will fail gracefully and return original)
        try:
            # This should not raise an error in the IDNA encoding phase
            result = await resolver.resolve("invalid..domain", 80)
            # If it gets here, the encoding was handled gracefully
            # but DNS lookup itself might fail
        except (OSError, ValueError, UnicodeError) as e:
            # This is expected - either our encode_idna or the system's IDNA encoding should fail
            assert (
                "DNS" in str(e)
                or "invalid" in str(e).lower()
                or "label" in str(e).lower()
            )

        await resolver.close()

    @pytest.mark.asyncio
    async def test_cache_key_differentiation(self):
        """Cache should differentiate between different ports and families."""
        cache = DNSCache()
        resolver = ThreadedResolver(cache=cache)

        # Same domain, different ports
        result1 = await resolver.resolve("example.com", 80)
        result2 = await resolver.resolve("example.com", 443)

        # Both should have been cache misses since ports differ
        stats = cache.get_stats()
        assert stats["misses"] >= 2

        # Verify they have different ports
        assert result1[0]["port"] == 80
        assert result2[0]["port"] == 443

        await resolver.close()
