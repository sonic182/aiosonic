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

## Project Layout

```text
aiosonic/
├── aiosonic/                  # library package
│   ├── client.py              # HTTPClient, HttpResponse, HttpHeaders; request building, redirects, proxy
│   ├── connectors.py          # TCPConnector: owns the pools (":default" + per-host from pool_configs), DNS
│   ├── resolver.py            # ThreadedResolver, AsyncResolver (DefaultResolver picks one)
│   ├── pools.py               # BasePool -> SmartPool (default), CyclicQueuePool, WsPool, Http2MultiplexPool
│   ├── connection.py          # Connection: one socket, created and held by a pool
│   ├── http2.py               # Http2Handler, Http2Config
│   ├── base_client.py         # BaseClient: wrapper over HTTPClient for building API clients
│   ├── httpx_client.py        # AsyncClient (subclass of BaseClient) with the httpx API
│   ├── web_socket_client.py   # WebSocketClient, WebSocketConnection, Message, ProtocolHandler
│   ├── sse_client.py          # SSEClient, SSEConnection (config in sse_config.py)
│   ├── http_parser.py         # header validation, body encoding
│   ├── multipart.py           # MultipartForm, MultipartFile
│   ├── compression.py         # bounded decompression
│   ├── auth.py                # BasicAuth, BearerAuth
│   ├── proxy.py, timeout.py   # Proxy, Timeouts
│   └── exceptions.py          # all custom exceptions, rooted at AiosonicError
├── aiosonic_utils/
│   └── structures.py          # CaseInsensitiveDict
├── tests/
│   ├── conftest.py            # fixtures, starts the Node helper servers
│   ├── test_*.py
│   ├── nodeapps/              # Node.js helper servers (see below)
│   └── files/                 # certs/ and sample files
├── scripts/                   # benchmarks and profiling
└── sourcedocs/                # Sphinx sources
```

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
