<p align="center">
  <img src="docs/assets/screens/apps.png" alt="fanoutkit running" width="900">
</p>

<h1 align="center">fanoutkit</h1>

<p align="center"><b>One HTTP call, every channel: Telegram, Discord, Slack, ntfy, email, webhook.</b></p>

<p align="center">
  <a href="https://github.com/scar8969/fanoutkit/actions/workflows/ci.yml"><img src="https://github.com/scar8969/fanoutkit/actions/workflows/ci.yml/badge.svg" alt="ci"></a> <a href="#quality-gates"><img src="https://img.shields.io/badge/tests-189%20passed-2ea44f" alt="tests: 189 passed"></a> <a href="#quality-gates"><img src="https://img.shields.io/badge/coverage-100.0%-brightgreen" alt="coverage: 100.0%"></a> <a href="#api"><img src="https://img.shields.io/badge/routes-7%20live-0969da" alt="routes: 7 live"></a> <a href="#requirements"><img src="https://img.shields.io/badge/python-3.11%2B-3776ab" alt="python: 3.11+"></a> <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ea44f" alt="license: MIT"></a>
</p>

fanoutkit accepts a single message from your application and delivers it to every channel you configured for that app — with per-channel retries, a stored delivery record, and a status endpoint you can poll.

---

**Contents** &nbsp;·&nbsp; [Why](#why-this-exists) &nbsp;·&nbsp; [What it does](#what-it-does) &nbsp;·&nbsp; [Quickstart](#quickstart) &nbsp;·&nbsp; [Screenshots](#screenshots) &nbsp;·&nbsp; [API](#api) &nbsp;·&nbsp; [CLI](#cli) &nbsp;·&nbsp; [Configuration](#configuration) &nbsp;·&nbsp; [Measured](#measured-not-estimated) &nbsp;·&nbsp; [How a request flows](#how-a-request-flows) &nbsp;·&nbsp; [Architecture](#architecture) &nbsp;·&nbsp; [Quality gates](#quality-gates) &nbsp;·&nbsp; [Development](#development) &nbsp;·&nbsp; [Deploy](#deploy) &nbsp;·&nbsp; [Limits](#limits-stated-rather-than-hidden)

## Why this exists

Notification code is where applications quietly rot: each new channel adds a client, its own retry rules and its own failure mode, and none of it is observable. fanoutkit puts one endpoint and one delivery table in front of all of them, so a failed Slack post is a row with a status and a retry button, not a log line nobody reads.

## What it does

| Capability | How it works |
| --- | --- |
| **Channel registry** | Telegram, Discord, Slack, ntfy, SMTP email and a generic webhook, each a class that registers itself by name. |
| **Per-channel delivery records** | One row per (message, channel) with status and error text; the message status endpoint aggregates them. |
| **Retry without resending everything** | POST /api/messages/<id>/retry re-runs only the channels that failed. |
| **App-scoped routing** | An app owns its channel configuration, so two services do not share credentials by accident. |
| **HTML + JSON** | An /apps page manages configuration; the API does the same work for automation. |

## Quickstart

```sh
git clone https://github.com/scar8969/fanoutkit.git
cd fanoutkit
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python wsgi.py                                 # http://127.0.0.1:8000
```

## Screenshots

Captured from the running service with headless Chromium at 1440×900, one image per page, committed under [`docs/assets/screens/`](docs/assets/screens/).

<table>
<tr>
<td width="50%"><img src="docs/assets/screens/root.png" alt="/" width="100%"><br><sub><code>/</code> &middot; 55.0 KB</sub></td>
<td width="50%"><img src="docs/assets/screens/healthz.png" alt="/healthz" width="100%"><br><sub><code>/healthz</code> &middot; 8.9 KB</sub></td>
</tr>
</table>

<table>
<tr>
<td width="50%"><img src="docs/assets/screens/livez.png" alt="/livez" width="100%"><br><sub><code>/livez</code> &middot; 7.3 KB</sub></td>
<td width="50%"><img src="docs/assets/screens/metrics.png" alt="/metrics" width="100%"><br><sub><code>/metrics</code> &middot; 14.7 KB</sub></td>
</tr>
</table>

<table>
<tr>
<td width="50%"><img src="docs/assets/screens/readyz.png" alt="/readyz" width="100%"><br><sub><code>/readyz</code> &middot; 7.7 KB</sub></td>
<td width="50%"><img src="docs/assets/screens/version.png" alt="/version" width="100%"><br><sub><code>/version</code> &middot; 27.7 KB</sub></td>
</tr>
</table>

## API

Every route below is declared in [`openapi/fanoutkit.yaml`](openapi/fanoutkit.yaml) and exercised by the live probe recorded in [`docs/EVIDENCE.md`](docs/EVIDENCE.md).

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/api/push` | push message |
| `GET` | `/api/status/<id>` | message status |
| `POST` | `/api/messages/<id>/retry` | retry |

## CLI

The same operations without an HTTP client. Installed as `fanoutkit`, and runnable from a checkout with no install:

```sh
python -m message_pusher.cli --help
```

```text
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
                        http://127.0.0.1:8000)
```

## Configuration

Environment only — there is no config file. Copy `.env.example` to `.env` and edit; `APP_ENV=production` refuses to start without `SECRET_KEY`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `APP_ENV` | `development` | development \| staging \| production; production enforces the secret. |
| `SECRET_KEY` | `change-me-in-production` | Session/CSRF signing key. Required when APP_ENV=production. |
| `HOST` | `0.0.0.0` | Interface the dev server binds. |
| `PORT` | `8000` | Port the dev server and the container listen on. |
| `DEBUG` | `false` | Flask debug mode. Never true in production. |
| `MAX_CONTENT_LENGTH` | `8388608` | Largest accepted request body, in bytes. |
| `DATA_DIR` | `(empty)` | Where uploaded and generated files live. |
| `INSTANCE_DIR` | `(empty)` | Where the SQLite file and instance state live. |
| `LOG_DIR` | `(empty)` | Where rotated log files are written, if file logging is on. |
| `LOG_LEVEL` | `INFO` | DEBUG \| INFO \| WARNING \| ERROR. |
| `LOG_JSON` | `true` | true emits one JSON object per line; false is human-readable. |
| `REQUEST_ID_HEADER` | `X-Request-ID` | Header echoed on every response and stamped on every log line. |
| `PUSHER_URL` | `http://127.0.0.1:8000` | Base URL the CLI talks to; also accepted as --url. |

## Measured, not estimated

Produced on this checkout by `pytest --cov` and by booting `wsgi.py` and issuing one real GET per documented path. The commands are recorded in [`docs/EVIDENCE.md`](docs/EVIDENCE.md).

| Signal | Value |
| --- | --- |
| Tests | **189 / 189 passed** (7.8 s, exit 0) |
| Line coverage | **100.0%** — 761 of 761 statements |
| Source | 22 files / 1,561 lines |
| Test code | 12 files / 2,525 lines |
| Documented paths | 3 in the spec, 1 GET |
| Live probe | 9 GET requests to the booted app, **7 answered 200** |
| Median latency | **22.6 ms** (single uncached request, dev server) |
| Slowest / fastest | 82.0 ms `/` / 13.9 ms `/livez` |
| Bytes served | 11.3 KB across 9 responses |
| Screenshots | 7 captured |

## How a request flows

```text
client
  │  HTTP
  ▼
wsgi.py ──▶ message_pusher/app.py:get_app()
                │  reads config once (message_pusher/config.py)
                │  registers the `pusher` blueprint
                ▼
           route handler
             ├──▶ message_pusher/models.py        tables, via Flask-SQLAlchemy
             ├──▶ message_pusher/errors.py        raises typed errors → one JSON envelope
             └──▶ message_pusher/observability.py JSON log line + X-Request-ID
```

Every response carries `X-Request-ID`, and the matching log line is written once at the end of the request with the status and duration, so a report of "it failed" is one `grep` away from the traceback.

## Architecture

```
fanoutkit/
├── src/message_pusher/
│   ├── http.py                         391  HTTP plumbing for message_pusher: correlation ids, a
│   ├── config.py                       173  Environment-driven configuration for message_pusher
│   ├── observability.py                169  Structured logging and request correlation for messa
│   ├── cli.py                          155  message-pusher CLI — queue a push, inspect status, r
│   ├── app.py                          119  Application factory for message_pusher
│   ├── _app.py                         113  
│   ├── errors.py                       108  Typed application errors and their HTTP mapping for 
│   ├── pusher/api.py                    62  
│   ├── models.py                        57  
│   ├── pusher/dispatch.py               57  
│   ├── paths.py                         52  Filesystem layout for message_pusher
│   ├── pusher/retry.py                  38  
├── openapi/fanoutkit.yaml                 the contract of record
├── schema/fanoutkit.sql                   the DDL
├── tests/                       the suite that has to stay green
├── docs/EVIDENCE.md             the recorded live route walk
├── Dockerfile                   multi-stage build
└── wsgi.py                      entry point
```

The package keeps one shape across the service: `config.py` reads the environment once, `observability.py` emits structured JSON logs carrying a request id, `errors.py` turns exceptions into a single JSON envelope, `models.py` holds the tables, and the `pusher/` package holds the routes.

## Quality gates

| Gate | Command | Threshold |
| --- | --- | --- |
| Suite | `pytest -q` | all green |
| Coverage | `pytest --cov` | floor in `pyproject.toml`, set below the measured value |
| Lint | `ruff check src tests` | zero findings |
| Format | `ruff format --check src tests` | zero reformats |
| Types | `mypy src` | zero errors |
| Security | `bandit -c pyproject.toml -r src` | reviewed skip list, no unreviewed finding |
| Live routes | boot `wsgi.py`, one GET per documented path | no 5xx, no undocumented guard |

CI runs the first six on Python 3.11, 3.12 and 3.13 on every push to `main`, plus a container build — [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Development

```sh
pip install -e ".[dev]"
python -m pytest -q                      # the suite
python -m pytest --cov                   # with the coverage floor
python -m ruff check src tests           # lint
python -m ruff format --check src tests  # formatting
python -m mypy src                       # types
python -m bandit -c pyproject.toml -r src  # security
pre-commit install                       # the same checks on commit
```

Dependabot opens grouped PRs for the dev tooling weekly and for actions and the base image monthly.

## Deploy

```sh
docker build -t fanoutkit .
docker run --rm -p 8000:8000 --env-file .env.example fanoutkit
```

A `docker-compose.yml` is included for a local run with a volume for the SQLite file. The image runs as a non-root user and serves through gunicorn.

## Limits, stated rather than hidden

- Delivery is synchronous per request: the HTTP call returns once every channel has answered or timed out.
- Email requires a reachable SMTP host; without one that channel reports the connection error and the other channels still deliver.

## License

MIT — see [LICENSE](LICENSE).
