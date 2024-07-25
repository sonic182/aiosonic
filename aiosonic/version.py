from importlib.metadata import PackageNotFoundError, version

try:
    VERSION = version("aiosonic")
except PackageNotFoundError:
    # Package is not installed
    VERSION = "0.0.0"
