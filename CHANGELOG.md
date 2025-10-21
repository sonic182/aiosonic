# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- HTTP/2: consolidated test files (`test_http2.py` and `test_http2_additional.py`) into single test file for improved maintainability
- Multipart form data: changed `_send_multipart` to return AsyncIterator for streaming multipart content instead of building in memory (improves memory efficiency for large file uploads)
- HTTP/2: added `keep_alive()` call after HTTP/2 requests to properly manage connection state

## [0.27.0] 2025-10-09

### Added
- SSE support: SSEClient/SSEConnection with parsing, reconnection and tests.

### Changed
- HTTP/2: fixed duplicate WindowUpdated handling, improved testability (injectable reader/writer/h2conn) and added tests for error handling, flow-control fallback and concurrent streams.

## [0.26.0] 2025-09-26

### Added
- MultipartFile class for specifying content type and filename in multipart uploads (now accepts both file paths and file objects with lazy file opening to avoid memory preloading)
- MultipartForm.add_field() now supports MultipartFile instances for more control over file uploads

### Changed
- `response.json()` no longer enforces content-type to be application/json, allowing parsing of valid JSON responses regardless of content-type header

## [0.25.0] 2025-08-28

### Added
- Better handling of follow redirects with more 3XX codes coverage

## [0.24.0] 2025-03-11

### Added

- Multiple pools configurations in client connector per target host.
  - conn idle timeout closing for more robust conns.
- AioSonicBaseClient for easily wrap apis with a class

## [0.23.1] 2025-02-16

### Added
- Protocol Handler class for websockets

## [0.23.0] 2025-02-16

### Added
- WebSocket support
  - Text, binary and JSON messages
  - Automatic ping/pong keep-alive

## [0.22.3] 2025-02-10

### Fixed
- Ensure read data or force close connection


## [0.22.2] 2025-02-10

### Removed
- django server in tests
  - using a nodejs equivalent
- Python 3.7 compatibility

## [0.22.1] 2025-02-01

### Added
- Python 3.13 compatibility

## [0.22.0] 2024-10-16

### Added
- MultipartForm class for easier multipart form data creation (https://github.com/sonic182/aiosonic/pull/513)


## [0.21.0] 2024-08-14

### Fixed
- Safer closing transport with abort, less RuntimeErrors https://github.com/sonic182/aiosonic/pull/483 (Thanks to @geraldog)

## [0.20.1] 2024-08-05

### Changed
* version range for charset-normalizer

## [0.20.0] 2024-08-01

### Changed
* json argument added in `HTTPClient.request` method
* parameters usage inside HTTPClient class

## [0.19.0] 2024-07-31

### Fixed
- Runtime error in certain conditions https://github.com/sonic182/aiosonic/issues/473 (Thanks to @geraldog)

## [0.18.1] 2024-07-30
### Changed
- Dependency management with poetry

### Fixed
- Proxy usage for https targets


## [0.18.0] 2024-02-06
### Fixed
- Pool drain issues (https://github.com/sonic182/aiosonic/pull/456, https://github.com/sonic182/aiosonic/pull/457) Thanks to @geraldog
- Exception when querying dns (https://github.com/sonic182/aiosonic/pull/457) Thanks to @geraldog

## [0.17.1] 2024-01-17
### Added
- Tests compatibility for python 3.12, tox and nodejs update (thanks to @jamim)

### Fixed
- Bug when pool is empty (thanks to @geraldog)

## [0.17.0] 2023-09-08
### Added
- ok property to HTTPClient (thanks to @pysergio)

## [0.16.2] 2023-08-11
### Fixed
- onecache dependency update

## [0.16.1] 2023-03-27
### Fixed
- onecache dependency works with pypy

## [0.16.0] 2023-03-26
### Changed
- conn_max_requests parameter to allow a maximum number of requests per keep-alived connection.
- using charset-normalizer for encoding detection

## [0.15.1] 2022-07-07
### Changed
- Removed some Python 3.6 code remaining

## [0.15.0] 2022-07-07
### Deprecated
- Python 3.6 support dropped

## [0.14.1] 2022-05-14
### Changed
- Lazy get loop on dns resolver

## [0.14.0] 2021-11-29
### Added
- Basic Proxy support, with basic auth

## [0.13.1] 2021-07-14
### Fixed
- Fix case sensitive header usage, for "Content-Type" header (thanks to @skyoo2003) in #302

## [0.13.0] 2021-07-14
### Added
- onecache package instead of utils cache class.

### Fixed
- setup.py requirements reading

## [0.12.0] 2021-07-14
### Added
- http2 POST method, tested just that method for now, it is alpha/beta, just need more tests and other methods.

### Fixed
- Not overwrite headers bug [#270](https://github.com/sonic182/aiosonic/issues/270) fixed in [#272](https://github.com/sonic182/aiosonic/pull/272)

## [0.11.3] 2021-07-10
### Fixed
- Check server not alive because reading wrong response, retrying call

## [0.11.2] 2021-07-09
### Added
- More debug logging, http2 module

### Fixed
- Some fixes when sizing windows in http2
- Refactor a lot of files with black

## [0.11.1] 2021-06-30
### Added
- dummy debug log for some debugging

## [0.11.0] 2021-06-28
### Fixed
- Parsing url with idna encoding (Internationalizing Domain Names in Applications), for non ascii urls

## [0.10.1] 2021-05-29
### Fixed
- Cache should not return value after expired [#258](https://github.com/sonic182/aiosonic/pull/258) (thanks to @difeid)

## [0.10.0] 2021-04-29
### Added
- dns resolvers

## [0.9.7] 2021-03-22
### Fixed
- json argument when false like value (empty lists) not being sent

## [0.9.6] 2021-03-20
### Changed
- Better requirements.txt

## [0.9.5] 2021-01-28
### Fixed
- Keep alive close when server say so

## [0.9.4] 2021-01-26
### Added
- PyPy tests in travis

## [0.9.3] 2021-01-26
### Added
- Re-insert connection in pool if HttpResponse object is collected by gc and connection hasn't been released

## [0.9.2] 2021-01-14
### Fixes
- Adding query params in request, when url has the query

## [0.9.1] 2021-01-14
### Fixes
- Parsing empty header

## [0.9.0] 2020-12-11
### Changed
- Response headers are `str` instead of `bytes`

## [0.8.1] 2020-12-08
### Added
- verify_ssl flag in HTTPClient class

## [0.8.0] 2020-12-07
### Added
- Some more documentation in reference
- Cookie handling with `handle_cookies` flag in client

### Improved
- benchmarch improved after `headers_base` variable was changed to a list (faster to add and iterate items in a list vs dict)

## [0.7.2] 2020-11-23
### Added
- Safe/gracefully shutdown of client
- Concurrent requests example in docs

### Fixed
- Non closed warnings in tests, fixed with gracefully shutdown.

## [0.7.1] 2020-11-22
### Fixed
- Parsing response headers
- Some code refactor for string interpolation. (Thanks to [machinexa2](https://github.com/machinexa2))  

### Updated
- Dependabot

## [0.7.0] 2020-09-23
### Added
- HTTPClient class
- Download image test and example

### Fixed
- Reading response bytes

## [0.6.0] 2020-05-08
### Added
- Compatibility with python 3.8 now is fully supported

## [0.5.3] 2020-01-12
### Fixed
- Method upcase in header all the time

## [0.5.2] 2019-12-08
### Added
- Nodejs app.js for a testing http2 server
- Tests using this app.js node http1.1/2 server

### Changed
- Updated dependencies
- Updated performance.py test for httpx 0.8.X

### Fixed
- Regex in setup.py

## [0.5.1] 2019-10-22
### Added
- http2 flag to allow it (maybe will be removed in future when http2 fully supported)

## [0.5.0] 2019-10-22
### Added
- Http2 support
  * Get requests (POST, PUT, ... requests with data sending missing)

### Fixed
- HTTP parsing error when reason-phrase empty [#30](https://github.com/sonic182/aiosonic/pull/30) (Thanks to [Dibel](https://github.com/Dibel))  

## [0.4.1] 2019-09-10
### Added
- raw_headers to HttpResponse objects

### Changed
- skip timeout usage for pool_acquire when not specified

## [0.4.0] 2019-08-24
### Added
- Json parsing with HttpResponse method
- More Timeouts options
- Timeouts overwritable by requests call

## [0.3.1] 2019-08-23
### Fixed
- Fix windows compatibility

## [0.3.0] 2019-08-23
### Added
- Smart decoding for HttpResponse.text coroutine method thanks to chardet package (first dependency added)
- Index page in docs

## [0.2.1] 2019-08-19
### Fixed
- Missing import

## [0.2.0] 2019-08-19
### Added
- Follow Redirects

## [0.1.0] 2019-08-07
### Added
- Minimal docs
- Smart and Cyclic Pool of connections
- Cache decorator
- Transmission chunked requests
- 100% coverage

## [0.0.4] 2019-08-04
### Added
- Automatic decompress (gzip, deflate)

## [0.0.3] 2019-08-04
### Fixed
- Fix transfer encoding responses handling
- Port usage openning connection

## [0.0.2] 2019-08-04
### Added
- Keepalive and pool of connections

### Removed
- Python 3.5 compatibility

## [0.0.1] 2019-08-02
### Added
- Keepalive and pool of connections
- Multipart File Uploads
- Connection Timeouts
- https


[Unreleased]: https://github.com/sonic182/aiosonic/compare/0.27.0..HEAD
[0.27.0]: https://github.com/sonic182/aiosonic/compare/0.26.0..0.27.0
[0.26.0]: https://github.com/sonic182/aiosonic/compare/0.25.0..0.26.0
[0.25.0]: https://github.com/sonic182/aiosonic/compare/0.24.0..0.25.0
[0.24.0]: https://github.com/sonic182/aiosonic/compare/0.23.1..0.24.0
[0.23.1]: https://github.com/sonic182/aiosonic/compare/0.23.0..0.23.1
[0.23.0]: https://github.com/sonic182/aiosonic/compare/0.22.3..0.23.0
[0.22.3]: https://github.com/sonic182/aiosonic/compare/0.22.2..0.22.3
[0.22.2]: https://github.com/sonic182/aiosonic/compare/0.22.1..0.22.2
[0.22.1]: https://github.com/sonic182/aiosonic/compare/0.22.0..0.22.1
[0.22.0]: https://github.com/sonic182/aiosonic/compare/0.21.0..0.22.0
[0.21.0]: https://github.com/sonic182/aiosonic/compare/0.20.1..0.21.0
[0.20.1]: https://github.com/sonic182/aiosonic/compare/0.20.0..0.20.1
[0.20.0]: https://github.com/sonic182/aiosonic/compare/0.19.0..0.20.0
[0.19.0]: https://github.com/sonic182/aiosonic/compare/0.18.1..0.19.0
[0.18.1]: https://github.com/sonic182/aiosonic/compare/0.18.0..0.18.1
[0.18.0]: https://github.com/sonic182/aiosonic/compare/0.17.1..0.18.0
[0.17.1]: https://github.com/sonic182/aiosonic/compare/0.17.0..0.17.1
[0.17.0]: https://github.com/sonic182/aiosonic/compare/0.16.2..0.17.0
[0.16.2]: https://github.com/sonic182/aiosonic/compare/0.16.1..0.16.2
[0.16.1]: https://github.com/sonic182/aiosonic/compare/0.16.0..0.16.1
[0.16.0]: https://github.com/sonic182/aiosonic/compare/0.15.1..0.16.0
[0.15.1]: https://github.com/sonic182/aiosonic/compare/0.15.0..0.15.1
[0.15.0]: https://github.com/sonic182/aiosonic/compare/0.14.1..0.15.0
[0.14.1]: https://github.com/sonic182/aiosonic/compare/0.14.0..0.14.1
[0.14.0]: https://github.com/sonic182/aiosonic/compare/0.13.1..0.14.0
[0.13.1]: https://github.com/sonic182/aiosonic/compare/0.13.0..0.13.1
[0.13.0]: https://github.com/sonic182/aiosonic/compare/0.12.0..0.13.0
[0.12.0]: https://github.com/sonic182/aiosonic/compare/0.11.3..0.12.0
[0.11.3]: https://github.com/sonic182/aiosonic/compare/0.11.2..0.11.3
[0.11.2]: https://github.com/sonic182/aiosonic/compare/0.11.1..0.11.2
[0.11.1]: https://github.com/sonic182/aiosonic/compare/0.11.0..0.11.1
[0.11.0]: https://github.com/sonic182/aiosonic/compare/0.10.1..0.11.0
[0.10.1]: https://github.com/sonic182/aiosonic/compare/0.10.0..0.10.1
[0.10.0]: https://github.com/sonic182/aiosonic/compare/0.9.7..0.10.0
[0.9.7]: https://github.com/sonic182/aiosonic/compare/0.9.6..0.9.7
[0.9.6]: https://github.com/sonic182/aiosonic/compare/0.9.5..0.9.6
[0.9.5]: https://github.com/sonic182/aiosonic/compare/0.9.4..0.9.5
[0.9.4]: https://github.com/sonic182/aiosonic/compare/0.9.3..0.9.4
[0.9.3]: https://github.com/sonic182/aiosonic/compare/0.9.2..0.9.3
[0.9.2]: https://github.com/sonic182/aiosonic/compare/0.9.1..0.9.2
[0.9.1]: https://github.com/sonic182/aiosonic/compare/0.9.0..0.9.1
[0.9.0]: https://github.com/sonic182/aiosonic/compare/0.8.1..0.9.0
[0.8.1]: https://github.com/sonic182/aiosonic/compare/0.8.0..0.8.1
[0.8.0]: https://github.com/sonic182/aiosonic/compare/0.7.2..0.8.0
[0.7.2]: https://github.com/sonic182/aiosonic/compare/0.7.1..0.7.2
[0.7.1]: https://github.com/sonic182/aiosonic/compare/0.7.0..0.7.1
[0.7.0]: https://github.com/sonic182/aiosonic/compare/0.6.0..0.7.0
[0.6.0]: https://github.com/sonic182/aiosonic/compare/0.5.3..0.6.0
[0.5.3]: https://github.com/sonic182/aiosonic/compare/0.5.2..0.5.3
[0.5.2]: https://github.com/sonic182/aiosonic/compare/0.5.1..0.5.2
[0.5.1]: https://github.com/sonic182/aiosonic/compare/0.5.0..0.5.1
[0.5.0]: https://github.com/sonic182/aiosonic/compare/0.4.1..0.5.0
[0.4.1]: https://github.com/sonic182/aiosonic/compare/0.4.0..0.4.1
[0.4.0]: https://github.com/sonic182/aiosonic/compare/0.3.1..0.4.0
[0.3.1]: https://github.com/sonic182/aiosonic/compare/0.3.0..0.3.1
[0.3.0]: https://github.com/sonic182/aiosonic/compare/0.2.1..0.3.0
[0.2.1]: https://github.com/sonic182/aiosonic/compare/0.1.0..0.2.1
[0.2.0]: https://github.com/sonic182/aiosonic/compare/0.1.0..0.2.0
[0.1.0]: https://github.com/sonic182/aiosonic/compare/0.0.4..0.1.0
[0.0.4]: https://github.com/sonic182/aiosonic/compare/0.0.3..0.0.4
[0.0.3]: https://github.com/sonic182/aiosonic/compare/0.0.2..0.0.3
[0.0.2]: https://github.com/sonic182/aiosonic/compare/0.0.1..0.0.2
[0.0.1]: https://github.com/sonic182/aiosonic/compare/4da47a5f131756fd87f63248f130a659bad163de..0.0.1
