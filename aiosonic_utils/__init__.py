"""Deprecated: the ``aiosonic_utils`` package moved into ``aiosonic`` and will be removed in the next major release."""

import warnings

warnings.warn(
    "aiosonic_utils is deprecated and will be removed in the next major release; "
    "import CaseInsensitiveDict from aiosonic.structures instead",
    DeprecationWarning,
    stacklevel=2,
)
