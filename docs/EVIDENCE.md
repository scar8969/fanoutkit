# Evidence

Every line below was produced by a command run against this exact checkout, on this machine, at the time recorded. Nothing here is copied from the README.

| | |
| --- | --- |
| Generated | 2026-10-19 11:52 |
| Python | 3.14.7 |
| Platform | Windows 11 |

## Test suite

```sh
python -m pytest -q
```

- exit code **0**
- 189 passed in 5.82s

## Static gates

| Gate | Exit | Last line |
| --- | --- | --- |
| `ruff check` | 0 | All checks passed! |
| `ruff format --check` | 0 | 34 files already formatted |
| `mypy src` | 0 | Success: no issues found in 22 source files |
| `bandit -c pyproject.toml -r src` | 0 | — |

## Live route walk

The application was imported through `wsgi.py` and each GET path declared in `openapi/` was requested once through the Werkzeug test client.

| Status | Path | Bytes | Content-Type |
| --- | --- | --- | --- |
| 404 | `/api/status/1` | 51 | application/json |

1 paths walked, 0 of them raised or answered 5xx.

## CLI

```
usage: pusher [-h] [--url URL] {push,status,retry,apps} ...

message-pusher CLI

positional arguments:
  {push,status,retry,apps}
    push                queue a message fan-out
    status              show a message and its delivery receipts
    retry               re-queue retrying receipts for a message
    apps                list apps and messages from the local database

options:
  -h, --help            show this help message and exit
  --url URL             base URL of a running instance (default $PUSHER_URL or
```

## Screenshots

Captured from the running service with headless Chromium at 1440x900 and committed with the repository:

| File | Bytes |
| --- | --- |
| `docs/assets/screens/apps.png` | 30,197 |
| `docs/assets/screens/healthz.png` | 9,104 |
| `docs/assets/screens/livez.png` | 7,468 |
| `docs/assets/screens/metrics.png` | 15,017 |
| `docs/assets/screens/readyz.png` | 7,880 |
| `docs/assets/screens/root.png` | 56,299 |
| `docs/assets/screens/version.png` | 28,400 |

## Charts

Generated from the same measurements the README quotes: `coverage-modules.svg`, `coverage.svg`, `files.svg`, `latency.svg`, `loc.svg`, `payload.svg`, `tests.svg`.

## What this file does not prove

- It is not a load test: every request is a single uncached call from one process.
- A green suite is not a coverage claim; `pytest --cov` reports the number the README quotes.
- The route walk exercises GET paths only; mutating routes are covered by the suite.
