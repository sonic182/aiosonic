# Contributing to aiosonic

Thanks for your interest in improving aiosonic, a fast asyncio HTTP/1.1, HTTP/2, WebSocket and SSE client. This guide explains how to report problems, propose changes and get a pull request merged.

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **Report a bug** using the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).
- **Suggest a feature** using the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).
- **Improve the docs** in `sourcedocs/` or the `README.md`.
- **Fix a bug or implement a feature** through a pull request.

Questions and discussion are welcome on [Discord](https://discord.gg/e7tBnYSRjj).

### Security issues

Do **not** open public issues for vulnerabilities. Follow [SECURITY.md](SECURITY.md) and use GitHub's private vulnerability reporting.

## Reporting bugs

Before opening an issue, check that the bug still happens on the latest release and that it has not already been reported. A useful report includes:

- aiosonic version, Python version and implementation (CPython / PyPy), and operating system.
- The protocol involved (HTTP/1.1, HTTP/2, WebSocket, SSE) and whether a proxy, TLS or a custom connector/pool is used.
- A minimal, runnable script that reproduces the problem, with the expected and the actual result.
- The full traceback. Debug logs of the request and response often help; enable them with `logging.getLogger("aiosonic").setLevel(logging.DEBUG)`. When running the test suite, set `AIOSONIC_DEBUG=1` instead.

Remove credentials, tokens and cookies from anything you paste.

## Proposing features

For anything beyond a small fix, open an issue first to discuss the design. aiosonic aims to stay lightweight and fast, with few runtime dependencies (`charset-normalizer`, `h2`, `onecache`), so new dependencies or large API additions need a good reason. Mention how other clients (httpx, aiohttp, requests) handle the same case if it is relevant.

## Development setup

Requirements:

- Python 3.10 or newer.
- [Poetry](https://python-poetry.org/).
- Node.js (CI uses Node 24). The test suite starts helper servers written in Node.

```bash
git clone https://github.com/<your-user>/aiosonic.git
cd aiosonic
poetry install
cd tests && npm install && cd ..
```

Run every command through `poetry run`.

## Project layout

| Path | Contents |
| --- | --- |
| `aiosonic/client.py` | `HTTPClient`, `HttpResponse`, `HttpHeaders` and the request/response flow |
| `aiosonic/connectors.py`, `pools.py`, `connection.py` | `TCPConnector`, connection pools (`SmartPool`, `CyclicQueuePool`) and the connection lifecycle |
| `aiosonic/http2.py` | HTTP/2 support on top of `h2` |
| `aiosonic/proxy.py`, `resolver.py`, `tcp_helpers.py` | Proxies, DNS resolution and socket helpers |
| `aiosonic/web_socket_client.py` | WebSocket client |
| `aiosonic/sse_client.py`, `sse_config.py` | Server-Sent Events client |
| `aiosonic/httpx_client.py` | httpx-compatible `AsyncClient` wrapper |
| `aiosonic/multipart.py`, `compression.py`, `auth.py` | Multipart bodies, decompression and authentication |
| `aiosonic/exceptions.py` | Custom exceptions |
| `aiosonic_utils/` | Shared data structures |
| `tests/` | Pytest suite; `tests/nodeapps/` holds the Node helper servers |
| `sourcedocs/` | Sphinx documentation (published on Read the Docs) |
| `scripts/` | Benchmarks and profiling tools |

## Making changes

1. Fork the repository and create a branch from `master`, for example `feature/my-feature` or `fix/short-description`.
2. Keep each pull request focused on one change.
3. Add or update tests for the behavior you change.
4. Update the docs in `sourcedocs/` and/or `README.md` when the public API changes.
5. Add an entry under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md), in the `Added`, `Changed` or `Fixed` section, following [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). Describe the change from the user's point of view.

### Code style

- Formatting and linting use Ruff with a 119 character line length:

  ```bash
  poetry run ruff format .
  poetry run ruff check aiosonic tests aiosonic_utils
  ```

- Use full type hints.
- Write Google or NumPy style docstrings for public classes and methods.
- Do not add inline comments inside the `aiosonic` package; prefer clear names and docstrings.
- Imports go standard library, then third party, then local, using absolute imports.
- Raise the custom exceptions from `aiosonic/exceptions.py` with descriptive messages.
- `print` is banned by the linter; use the `aiosonic` logger.

### Tests

```bash
poetry run py.test                                   # whole suite, with coverage
poetry run py.test tests/test_http2.py               # one file
poetry run py.test tests/test_sse.py::test_name      # one test
```

- Tests live in `tests/test_*.py` and use `pytest-asyncio`.
- Prefer tests that exercise a real request against the helper servers (fixtures such as `http_serv` and `http2_serv` in `tests/conftest.py`) over mocks. A few tests covering the important paths are better than many granular ones.
- Wire-level behavior (headers, query strings, proxies) is covered in `tests/test_request_wire.py`.
- Tests that need a new endpoint should extend the matching server in `tests/nodeapps/` (`http1.mjs`, `http2.js`, `ws-server.mjs`, `sse-server.mjs`).

CI runs lint and the full suite on Linux, macOS and Windows for Python 3.10 to 3.14 and PyPy 3.11. To try other Python versions locally with Docker, use `make test310`, `make test311`, `make test312`, `make test313`, `make test-pypy311` or `make test` for all of them.

### Documentation

```bash
poetry run sphinx-build -W -b html sourcedocs build/html
```

Warnings are treated as errors, so fix them before submitting.

## Pull requests

Before opening a pull request, make sure that:

- [ ] `poetry run ruff check aiosonic tests aiosonic_utils` passes.
- [ ] `poetry run py.test` passes.
- [ ] New behavior has tests and, if public, documentation.
- [ ] `CHANGELOG.md` has an entry under `[Unreleased]`.

In the description, explain what changed and why, and link the related issue (`Fixes #123`). Keep commit messages short and in the imperative mood ("Fix cookie merging on redirects").

A maintainer will review the PR; please be ready to iterate on feedback. Releases, version bumps and PyPI uploads are handled by the maintainers.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
