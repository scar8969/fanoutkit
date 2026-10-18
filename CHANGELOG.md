# Changelog

All notable changes to fanoutkit are documented here.

The format follows Keep a Changelog (https://keepachangelog.com/en/1.1.0/), and
this project adheres to Semantic Versioning
(https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Recorded quality-gate evidence, quoted verbatim in
  [docs/EVIDENCE.md](docs/EVIDENCE.md) and in the README: 189 tests passed with
  0 failures and 0 errors, and 100.00% statement coverage over 760 statements,
  alongside the exact commands that produced both.
- Strict type annotations across all 22 source modules, so `mypy --strict`
  reports no issues and `pyflakes` reports no findings.
- Dependency-free SVG charts of test, coverage, latency, payload, LOC and
  file-count data under `docs/assets/`, generated from the recorded metrics
  document and committed so they render on the repository page without a build
  step.
- An application-factory test module covering `get_app()` (cold start, warm
  start and the Flask instance it returns) and the configuration forwarding in
  `create_app()`.

### Changed

- Every `Query.get()` and `Query.get_or_404()` call became `db.session.get()`
  and `db.get_or_404()`, removing the SQLAlchemy 2.0 legacy deprecation
  warnings from the suite.
- `datetime.utcnow()` is deprecated since 3.12 and warns on every call; the
  naive-UTC helper is now built from an aware `datetime.now(UTC)`. (It has not
  been removed in 3.14 — that removal is still only planned.)
- The README quality-gate table, the HTTP surface, the operational-endpoint
  bodies and the architecture tree are generated from measurements instead of
  being written by hand.
- `docs/OPERATIONS.md` and ADR 0002 now describe the metrics that are actually
  exported: `http_requests_total{method,status}` and
  `http_request_duration_seconds_sum{method}`, with no histogram, no count and
  no p99.

### Fixed

- `/metrics` advertised `text/plain; version=0.0.4; charset=utf-8; charset=utf-8`,
  a duplicated charset parameter, because the whole media type was passed to
  Flask as the mimetype. The header is now written once, and a test asserts its
  exact value.
- Overrides prefixed `MESSAGE_PUSHER_` were ignored: `paths.ENV_PREFIX` was
  missing its trailing underscore.
- A whitespace-only boolean such as `DEBUG=" "` was refused instead of falling
  back to the documented default.
- `message_pusher apps` kept a SQLAlchemy engine per invocation instead of
  disposing it, so a long-lived process accumulated engines.
- `message_pusher status` raised `KeyError` when a 200 response was not the
  documented envelope; it now prints the body verbatim.
- The CLI left an `HTTPError` response unclosed, holding the socket until the
  garbage collector ran; the response is now closed.

### Known limitations

- Screenshots are committed under `docs/assets/screens/`, one per page, captured
  from the running service with headless Chromium at 1440x900. `docs/EVIDENCE.md`
  records the live route walk that backs the numbers in the README.
 on an operating-system
  access denial and the Playwright bundle fails with `WinError 5`. The HTTP
  surface is evidenced with recorded status codes, sizes and bodies instead.
- `ruff`, `bandit` and `pip-audit` are configured but were never executed here:
  the generating host has no network access. `pyflakes` and `mypy` are the
  static checks that could run, and both are clean.
- No container image has been built.

## [0.1.0] - 2026-10-08

First release under the current packaging. This is the industry-baseline
release: the domain behaviour is the original contract's, and everything around
it is new.

### Added

- `src/` layout with an installable distribution and a typed, importable
  package (`pip install -e .`).
- `create_app()` application factory plus a compatibility `wsgi.py` shim.
- Environment-driven configuration parsed into a frozen `Settings` object and
  validated at startup with actionable errors.
- Structured JSON logging with per-request correlation ids.
- Operational endpoints: `/healthz`, `/livez`, `/readyz`, `/metrics`
  and `/version`.
- Security headers and a uniform JSON error envelope on every response.
- Hand-rolled Prometheus text exposition, with no `prometheus_client`
  dependency.
- Multi-stage Dockerfile running as an unprivileged user, with a healthcheck, a
  read-only root filesystem and dropped capabilities.
- `Makefile`, pre-commit configuration, ruff and mypy configuration, pytest
  with a coverage floor, and a GitHub Actions pipeline covering lint, type, test,
  security and container build.
- Documentation set: README, architecture, operations runbook, ADRs, security
  policy, contributing guide and this changelog.

### Changed

- Every historical flat import was rewritten to a package-relative import, so the
  modules can no longer be shadowed.
- Runtime state moved to `var/` (database, logs), outside the importable tree.

### Known limitations

- ruff, bandit and pip-audit are configured but were never executed: the
  generating sandbox had no network access.
- The coverage floor is configured here; it was measured in the following pass
  at 100.00%, above the 85% gate.
- No container image has been built.

[Unreleased]: https://example.invalid/message_pusher/compare/v0.1.0...HEAD
[0.1.0]: https://example.invalid/message_pusher/releases/tag/v0.1.0
