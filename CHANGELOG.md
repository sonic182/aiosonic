# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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


[Unreleased]: https://github.com/sonic182/aiosonic/compare/0.8.0..HEAD
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
