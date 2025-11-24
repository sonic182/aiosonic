"""Utils."""

import logging
from typing import Optional

from onecache import CacheDecorator


@CacheDecorator()
def get_debug_logger():
    """Get debug logger."""
    logger = logging.getLogger("aiosonic")
    # logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())
    return logger


def encode_idna(domain: str, port: Optional[int] = None) -> str:
    """
    Encode a domain name to IDNA (ASCII-compatible encoding).

    Converts internationalized domain names (IDN) from Unicode to
    ASCII-compatible encoding (punycode), suitable for DNS lookups.

    Args:
        domain: Domain name (can be Unicode or ASCII)
        port: Optional port number (ignored, for API compatibility)

    Returns:
        ASCII-compatible encoded domain name

    Raises:
        UnicodeError: If domain encoding fails
        ValueError: If domain is empty or invalid

    Examples:
        >>> encode_idna("münchen.de")
        'xn--mnchen-3ya.de'
        >>> encode_idna("example.com")
        'example.com'
    """
    if not domain:
        raise ValueError("Domain cannot be empty")

    # Remove trailing dot if present for processing
    has_trailing_dot = domain.endswith(".")
    domain = domain.rstrip(".")

    # Handle case sensitivity - IDNA is case-insensitive, normalize to lowercase
    domain = domain.lower()

    # Split by dots and encode each label
    labels = domain.split(".")
    encoded_labels = []

    for label in labels:
        if not label:
            raise ValueError(f"Invalid domain: empty label in {domain}")

        try:
            # Try to encode the label using IDNA
            encoded_label = label.encode("idna").decode("ascii")
            encoded_labels.append(encoded_label)
        except (UnicodeError, UnicodeDecodeError) as e:
            raise UnicodeError(f"Failed to encode domain label '{label}': {e}")

    result = ".".join(encoded_labels)

    # Add trailing dot back if it was present
    if has_trailing_dot:
        result += "."

    return result


def decode_idna(domain: str) -> str:
    """
    Decode a domain name from IDNA (ASCII-compatible encoding) to Unicode.

    Converts ASCII-compatible encoded domain names (punycode) back to
    their Unicode representation.

    Args:
        domain: ASCII-encoded domain name (punycode)

    Returns:
        Unicode representation of the domain name

    Raises:
        UnicodeError: If domain decoding fails
        ValueError: If domain is empty

    Examples:
        >>> decode_idna("xn--mnchen-3ya.de")
        'münchen.de'
        >>> decode_idna("example.com")
        'example.com'
    """
    if not domain:
        raise ValueError("Domain cannot be empty")

    # Remove trailing dot if present for processing
    has_trailing_dot = domain.endswith(".")
    domain = domain.rstrip(".")

    # Split by dots and decode each label
    labels = domain.split(".")
    decoded_labels = []

    for label in labels:
        if not label:
            raise ValueError(f"Invalid domain: empty label in {domain}")

        try:
            # Try to decode the label using IDNA
            decoded_label = label.encode("ascii").decode("idna")
            decoded_labels.append(decoded_label)
        except (UnicodeError, UnicodeDecodeError):
            # If decoding fails, the label is likely already Unicode
            # or ASCII - just use it as is
            decoded_labels.append(label)

    result = ".".join(decoded_labels)

    # Add trailing dot back if it was present
    if has_trailing_dot:
        result += "."

    return result
