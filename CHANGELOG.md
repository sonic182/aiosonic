# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
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


[Unreleased]: https://github.com/sonic182/aiosonic/compare/0.3.1..HEAD
[0.3.1]: https://github.com/sonic182/aiosonic/compare/0.3.0..0.3.1
[0.3.0]: https://github.com/sonic182/aiosonic/compare/0.2.1..0.3.0
[0.2.1]: https://github.com/sonic182/aiosonic/compare/0.1.0..0.2.1
[0.2.0]: https://github.com/sonic182/aiosonic/compare/0.1.0..0.2.0
[0.1.0]: https://github.com/sonic182/aiosonic/compare/0.0.4..0.1.0
[0.0.4]: https://github.com/sonic182/aiosonic/compare/0.0.3..0.0.4
[0.0.3]: https://github.com/sonic182/aiosonic/compare/0.0.2..0.0.3
[0.0.2]: https://github.com/sonic182/aiosonic/compare/0.0.1..0.0.2
[0.0.1]: https://github.com/sonic182/aiosonic/compare/4da47a5f131756fd87f63248f130a659bad163de..0.0.1
