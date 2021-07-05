from importlib import reload
from unittest.mock import patch


def test_cchardet_import_error(mocker):
    """Test cchardet import error.

    Test to cover "pass" line in ImportError handling.
    """
    orig_import = __import__

    def import_mock(name, *args):
        if name == "cchardet":
            raise ImportError()
        return orig_import(name, *args)

    with patch("builtins.__import__", side_effect=import_mock):
        import aiosonic  # noqa

        reload(aiosonic)
