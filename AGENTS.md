# Agent Instructions for aiosonic

## Build/Lint/Test Commands

ALWAYS USE poetry for commands eg: `poetry run <command>` it coud be "python", py.test, black, etc.

- **Build**: `poetry build` or `make build`
- **Test all**: `poetry run py.test`
- **Test single file**: `poetry run py.test tests/test_filename.py`
- **Test single function**: `poetry run py.test tests/test_filename.py::test_function_name`
- **Lint/Format**: `poetry run black .` (formatting), `poetry run ruff check .` (linting)
- **CI test command**: `poetry run py.test --cov-append`
- **Run scripts or examples**: `poetry run <file.py>`

## Code Style Guidelines
### Imports: Standard library → Third-party → Local (absolute imports, blank lines between groups)
### Types: Extensive typing module use (Dict, List, Optional, Union, etc.) with full type hints
### Naming: Classes=CamelCase, Functions/Methods=snake_case, Constants=UPPER_CASE, Private=_leading_underscore
### Error Handling: Custom exceptions in exceptions.py, descriptive messages, appropriate try/except
### Documentation: Google/NumPy docstring format for all classes and public methods
### Comments: DO NOT ADD ***ANY*** COMMENTS in "aiosonic" package functions or classes
### Formatting: Black formatter (88 char lines, 4 space indent, no trailing whitespace)

## HTTP Client Architecture

### Class Diagram

```
┌─────────────────┐     ┌─────────────────┐
│   HTTPClient    │     │AioSonicBaseClient│
│                 │     │                 │
│ • get()         │     │ • get()         │
│ • post()        │     │ • post()        │
│ • put()         │     │ • put()         │
│ • patch()       │     │ • patch()       │
│ • delete()      │     │ • delete()      │
│ • request()     │     │ • request()     │
└─────────┬───────┘     └─────────────────┘
          │
          │ uses
          ▼
┌─────────────────┐     ┌─────────────────┐
│  TCPConnector   │     │   Connection    │
│                 │     │                 │
│ • acquire()     │     │ • connect()     │
│ • pools         │◄────┤ • write()       │
│ • resolver      │     │ • read()        │
│ • dns_cache     │     │ • keep_alive()  │
└─────────┬───────┘     └─────────────────┘
          │
          │ manages
          ▼
┌─────────────────┐     ┌─────────────────┐
│   BasePool      │     │   SmartPool     │
│ (abstract)      │     │                 │
│                 │     │ • acquire()     │
│ • acquire()     │     │ • release()     │
│ • release()     │     │ • cleanup()     │
│ • cleanup()     │     │ • free_conns()  │
└─────────────────┘     └─────────────────┘

┌─────────────────┐     ┌─────────────────┐
│  HttpResponse   │     │   HttpHeaders   │
│                 │     │ (CaseInsensitive│
│ • status_code   │     │   Dict)         │
│ • headers       │◄────┤                 │
│ • content()     │     │ • __getitem__   │
│ • text()        │     │ • __setitem__   │
│ • json()        │     │ • get()         │
└─────────────────┘     └─────────────────┘

┌─────────────────┐     ┌─────────────────┐
│ WebSocketClient │     │WebSocketConnection│
│                 │     │                 │
│ • connect()     │────►│ • send()        │
│ • close()       │     │ • receive()     │
│                 │     │ • ping()        │
└─────────────────┘     └─────────┬───────┘
                                 │
                                 │ yields
                                 ▼
┌─────────────────┐     ┌─────────────────┐
│    Message      │     │ ProtocolHandler │
│                 │     │ (abstract)      │
│ • type          │     │                 │
│ • data          │◄────┤ • encode()      │
│ • raw_data      │     │ • decode()      │
│ • opcode        │     │ • name          │
└─────────────────┘     └─────────────────┘

┌─────────────────┐     ┌─────────────────┐
│    SSEClient    │     │   SSEConnection │
│                 │     │                 │
│ • connect()     │────►│ • __aiter__()   │
│                 │     │ • close()       │
└─────────────────┘     └─────────────────┘
```

## Test Setup
- **Tests location**: `tests/` directory at project root
- **Test files**: Follow `test_*.py` naming convention
- **Node.js servers**: Helper applications in `tests/nodeapps/` (HTTP/1, HTTP/2, WebSocket servers)
- **Test assets**: Certificates in `tests/files/certs/`, sample files in `tests/files/`
- **Pytest plugins**: Uses pytest-asyncio, pytest-cov, pytest-timeout, pytest-sugar

### Node.js Helper Servers
- **HTTP/1.1 server**: `tests/nodeapps/http1.mjs` - Basic HTTP endpoints, multipart, compression
- **HTTP/2 server**: `tests/nodeapps/http2.js` - HTTP/2 protocol testing
- **WebSocket server**: `tests/nodeapps/ws-server.mjs` - WebSocket with optional SSL support
- **SSE server**: `tests/nodeapps/sse-server.mjs` - Server-Sent Events testing
- **Dependencies**: Requires Node.js installed (`brew install node` on macOS)
- **Package management**: `tests/package.json` defines dependencies (ws library for WebSockets)
