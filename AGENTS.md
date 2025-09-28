# Agent Instructions for aiosonic

## Build/Lint/Test Commands
- **Build**: `poetry build` or `make build`
- **Test all**: `poetry run py.test` or `pytest`
- **Test single file**: `poetry run py.test tests/test_filename.py`
- **Test single function**: `poetry run py.test tests/test_filename.py::test_function_name`
- **Lint/Format**: `black .` (formatting), `mypy .` (type checking)
- **CI test command**: `poetry run py.test --cov-append`

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
```

### Architecture Overview

**HTTP Client Flow:**
- `HTTPClient` is the main entry point for HTTP requests
- It uses `TCPConnector` to manage connections and connection pools
- `TCPConnector` maintains pools of `Connection` objects via `SmartPool`
- Requests return `HttpResponse` objects containing `HttpHeaders`

**WebSocket Support:**
- `WebSocketClient` handles the initial HTTP upgrade handshake
- Successful connections return `WebSocketConnection` objects
- `WebSocketConnection` yields `Message` objects for received data
- Custom protocols can extend `ProtocolHandler` for encoding/decoding

**Connection Management:**
- `BasePool` provides the abstract interface for connection pooling
- `SmartPool` implements intelligent connection reuse by hostname/port
- `Connection` objects handle the actual socket communication
- DNS resolution and caching is handled by `TCPConnector`


## Test Setup

### Directory Structure
- **Tests location**: `tests/` directory at project root
- **Test files**: Follow `test_*.py` naming convention (e.g., `test_aiosonic.py`, `test_connection.py`)
- **Node.js servers**: Helper applications in `tests/nodeapps/` (HTTP/1, HTTP/2, WebSocket servers)
- **Test assets**: Certificates in `tests/files/certs/`, sample files in `tests/files/`
- **Coverage reports**: Generated in `tests/htmlcov/` directory

### Running Tests
- **All tests**: `pytest` or `poetry run py.test`
- **Single file**: `pytest tests/test_filename.py`
- **Single test**: `pytest tests/test_filename.py::test_function_name`
- **With coverage**: `poetry run py.test --cov-append` (CI command)
- **Pytest plugins**: Uses pytest-asyncio, pytest-cov, pytest-timeout, pytest-sugar

### Fixtures (conftest.py)
- **Session-scoped fixtures**: `http_serv`, `http2_serv`, `ws_serv`, `ws_serv_ssl`, `proxy_serv`
- **SSL context**: `ssl_context` fixture for HTTPS/WSS testing
- **Port management**: Random port allocation (3000-4000 for servers, 8000-9000 for proxy)
- **Process management**: Automatic Node.js server startup/teardown via subprocess
- **Health checks**: Built-in port checking with configurable timeouts

### Node.js Helper Servers
- **HTTP/1.1 server**: `tests/nodeapps/http1.mjs` - Basic HTTP endpoints, multipart, compression
- **HTTP/2 server**: `tests/nodeapps/http2.js` - HTTP/2 protocol testing
- **WebSocket server**: `tests/nodeapps/ws-server.mjs` - WebSocket with optional SSL support
- **Dependencies**: Requires Node.js installed (`brew install node` on macOS)
- **Package management**: `tests/package.json` defines dependencies (ws library for WebSockets)

### Test Dependencies
- **Core**: pytest, pytest-asyncio for async test support
- **Coverage**: pytest-cov for code coverage reporting
- **Mocking**: pytest-mock for test doubles
- **Type checking**: pytest-mypy (platform-dependent)
- **Proxy testing**: proxy-py for HTTP proxy integration tests
- **External tools**: httpx, requests for comparison testing

### Environment Setup
- **Python versions**: Supports Python 3.9+ (defined in pyproject.toml)
- **Platform-specific**: Different dependencies for Windows/Unix (uvloop vs winloop)
- **Installation**: `poetry install` installs all test dependencies
- **Event loop**: Windows uses WindowsSelectorEventLoopPolicy (configured in conftest.py)

### Troubleshooting
- **Node.js not found**: Ensure Node.js is installed and available in PATH
- **Port conflicts**: Tests use random ports; check for conflicting services
- **SSL certificate errors**: Verify `tests/files/certs/` contains valid cert/key files
- **Timeout failures**: Increase timeout in `check_port()` function if servers start slowly
- **Platform issues**: Check platform-specific dependencies in pyproject.toml
- **Process cleanup**: Failed tests may leave Node.js processes running; check with `ps` or Task Manager
