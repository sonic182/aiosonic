# Agent Instructions for aiosonic

## Build/Lint/Test Commands

### Python Runner

The project is managed with Poetry (`pyproject.toml` + `poetry.lock`). Install dependencies with `poetry install` and run every command through `poetry run <cmd>`.

> In the commands below, `<runner>` stands for `poetry run`.

### Commands

- **Build**: `<runner> python -m build` or `make build`
- **Test all**: `<runner> py.test`
- **Test single file**: `<runner> py.test tests/test_filename.py`
- **Test single function**: `<runner> py.test tests/test_filename.py::test_function_name`
- **Lint/Format**: `<runner> ruff format .` (formatting), `<runner> ruff check .` (linting)
- **CI test command**: `<runner> py.test --cov-append`
- **Run scripts or examples**: `<runner> python <file.py>`

## After Applying Code Changes

After finishing a set of code changes, always run these checks in order:

1. **Lint**: `<runner> ruff check aiosonic tests aiosonic_utils`
2. **Tests**: `<runner> py.test`

Fix any lint errors or test failures before considering the task done.

## Code Style Guidelines

- **Imports**: Standard library → Third-party → Local (absolute imports, blank lines between groups)
- **Types**: Extensive typing module use (`Dict`, `List`, `Optional`, `Union`, etc.) with full type hints
- **Naming**: Classes=CamelCase, Functions/Methods=snake_case, Constants=UPPER_CASE, Private=_leading_underscore
- **Error Handling**: Custom exceptions in `exceptions.py`, descriptive messages, appropriate try/except
- **Documentation**: Google/NumPy docstring format for all classes and public methods
- **Comments**: DO NOT ADD ***ANY*** COMMENTS in `aiosonic` package functions or classes
- **Formatting**: Ruff formatter (119 char lines, 4 space indent, no trailing whitespace)

## Module Map

All paths are under `aiosonic/` unless noted.

- `client.py`: `HTTPClient`, `HttpResponse`, `HttpHeaders`, request building and the redirect/proxy flow
- `connectors.py`: `TCPConnector`, which owns the pools (a `:default` pool plus optional per-host ones from `pool_configs`) and DNS resolution (`resolver.py`)
- `pools.py`: `SmartPool` (default), `CyclicQueuePool`, `WsPool`, `Http2MultiplexPool` (default with `http2=True`)
- `connection.py`: `Connection`, a single socket; HTTP/2 goes through `Http2Handler` in `http2.py`
- `base_client.py`: `BaseClient`, a wrapper over `HTTPClient` for building API clients
- `httpx_client.py`: `AsyncClient`, an httpx-compatible client built on `BaseClient`
- `web_socket_client.py`: `WebSocketClient`, `WebSocketConnection`, `Message`, `ProtocolHandler`
- `sse_client.py`, `sse_config.py`: `SSEClient`, `SSEConnection`
- `http_parser.py`, `multipart.py`, `compression.py`: header/body encoding, multipart forms, bounded decompression
- `auth.py`, `proxy.py`, `timeout.py`: `BasicAuth`/`BearerAuth`, `Proxy`, `Timeouts`
- `exceptions.py`: every custom exception, rooted at `AiosonicError`
- `aiosonic_utils/structures.py`: `CaseInsensitiveDict`

## Test Setup

- **Tests location**: `tests/` directory at project root
- **Test files**: Follow `test_*.py` naming convention
- **Node.js servers**: Helper applications in `tests/nodeapps/` (HTTP/1, HTTP/2, WebSocket servers)
- **Test assets**: Certificates in `tests/files/certs/`, sample files in `tests/files/`
- **Pytest plugins**: Uses `pytest-asyncio`, `pytest-cov`, `pytest-mock`, `pytest-timeout`, `pytest-sugar`

### Node.js Helper Servers

| File | Purpose |
|------|---------|
| `tests/nodeapps/http1.mjs` | Basic HTTP endpoints, multipart, compression |
| `tests/nodeapps/http2.js` | HTTP/2 protocol testing |
| `tests/nodeapps/ws-server.mjs` | WebSocket with optional SSL support |
| `tests/nodeapps/sse-server.mjs` | Server-Sent Events testing |

- **Dependencies**: Requires Node.js installed (`brew install node` on macOS)
- **Package management**: `tests/package.json` defines dependencies (`ws` library for WebSockets)
