"""
Tests for IDNA (Internationalized Domain Names in Applications) support.
"""

import pytest
from aiosonic.utils import encode_idna, decode_idna


class TestIDNAEncoding:
    """Test IDNA encoding functionality."""

    def test_encode_ascii_domain(self):
        """ASCII domains should remain unchanged."""
        assert encode_idna("example.com") == "example.com"
        assert encode_idna("localhost") == "localhost"
        assert encode_idna("test-domain.org") == "test-domain.org"

    def test_encode_unicode_domain(self):
        """Unicode domains should be converted to punycode."""
        # German domain
        assert encode_idna("münchen.de") == "xn--mnchen-3ya.de"
        # Chinese domain
        assert encode_idna("中国.cn") == "xn--fiqs8s.cn"
        # Japanese domain
        assert encode_idna("日本.jp") == "xn--wgv71a.jp"

    def test_encode_mixed_domain(self):
        """Mixed ASCII and Unicode subdomains should be handled."""
        assert encode_idna("test.münchen.de") == "test.xn--mnchen-3ya.de"
        assert encode_idna("example.中国.cn") == "example.xn--fiqs8s.cn"

    def test_encode_already_encoded_domain(self):
        """Already encoded domains should work correctly."""
        assert encode_idna("xn--mnchen-3ya.de") == "xn--mnchen-3ya.de"

    def test_encode_case_insensitive(self):
        """IDNA encoding should be case-insensitive."""
        assert encode_idna("MÜNCHEN.DE").lower() == "xn--mnchen-3ya.de"
        assert encode_idna("München.De") == encode_idna("münchen.de")

    def test_encode_with_port(self):
        """Encoding should handle domains with ports."""
        result = encode_idna("münchen.de", port=8080)
        assert result == "xn--mnchen-3ya.de"

    def test_encode_invalid_domain(self):
        """Invalid domains should raise appropriate errors."""
        with pytest.raises(Exception):
            encode_idna("invalid..domain")
        with pytest.raises(Exception):
            encode_idna("")

    def test_encode_special_characters(self):
        """Domains with special characters should be handled."""
        # Hyphen in subdomain
        assert encode_idna("sub-domain.example.com") == "sub-domain.example.com"
        # Numbers
        assert encode_idna("test123.example.com") == "test123.example.com"

    def test_decode_ascii_domain(self):
        """ASCII domains should remain unchanged when decoding."""
        assert decode_idna("example.com") == "example.com"

    def test_decode_punycode_domain(self):
        """Punycode domains should be decoded to Unicode."""
        assert decode_idna("xn--mnchen-3ya.de") == "münchen.de"
        assert decode_idna("xn--fiqs8s.cn") == "中国.cn"
        assert decode_idna("xn--wgv71a.jp") == "日本.jp"

    def test_encode_decode_roundtrip(self):
        """Encoding then decoding should return original Unicode domain."""
        domains = [
            "münchen.de",
            "中国.cn",
            "日本.jp",
            "test.münchen.de",
            "example.com",  # ASCII should also work
        ]
        for domain in domains:
            encoded = encode_idna(domain)
            decoded = decode_idna(encoded)
            assert decoded.lower() == domain.lower()

    def test_encode_with_trailing_dot(self):
        """Domains with trailing dot should be handled."""
        result = encode_idna("münchen.de.")
        assert result in ["xn--mnchen-3ya.de.", "xn--mnchen-3ya.de"]
