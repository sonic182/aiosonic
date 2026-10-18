# Threat model

## What this project does and where untrusted input enters

aiosonic is an asynchronous HTTP and WebSocket client. Treat server responses, headers, URLs, proxy responses, and WebSocket frames as untrusted input. The client also sends application-provided request data to remote servers.

## Components that matter most / least

Focus on HTTP and WebSocket protocol parsing, response and header handling, connection pooling, TLS configuration, proxy support, and URL processing. Test helpers and documentation are lower priority; exclude them only when they cannot affect shipped package behavior.

## How to exercise it

Run `poetry run py.test` from `/src`. The pytest suite in `tests/` includes local HTTP, proxy, and WebSocket servers. The Dockerfile installs its Python and Node dependencies before the scan.

## How you rate severity

Follow `SECURITY.md` for security issue scope. Assess severity from demonstrated impact, attacker control, and required application configuration. Prioritize TLS verification bypasses, credential leakage across redirects or pooled connections, HTTP request smuggling, header injection, and resource exhaustion from malformed remote responses. Include a minimal reproducer and explain the affected trust boundary.

## Anything to leave alone

Issues that only occur when applications explicitly disable TLS verification or other security controls are generally out of scope, as described in `SECURITY.md`. Report unsafe defaults, proxy authentication or routing bypasses, and unexpected weakening of security controls.
