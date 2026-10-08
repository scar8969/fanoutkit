# message-pusher

> A small self-hosted service that accepts one message from an app and fans it out

[![ci](https://img.shields.io/badge/ci-github--actions-blue)](.github/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

a2_message_pusher is a Flask service delivered as an installable, typed, test-covered
distribution. The business logic is unchanged from the original skeleton; what
is new is the engineering around it: a packaging story, a configuration
contract, structured observability, operational endpoints, a hardened
container, and the gates that keep all of that true.

---

## Quickstart

```sh
git clone <your-fork> a2_message_pusher && cd a2_message_pusher
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
python wsgi.py
```

The service listens on `http://127.0.0.1:8000` by default.

```sh
curl -s localhost:8000/healthz | python -m json.tool
curl -s localhost:8000/version | python -m json.tool
curl -s localhost:8000/metrics | head
```

---

## Operating contract

Every deployment target answers the same five endpoints. They are the contract
an orchestrator, a load balancer, or an on-call engineer relies on.

| Endpoint  | Purpose                                       | Success | Failure |
| --------- | --------------------------------------------- | ------- | ------- |
| `/healthz` | Process is up and the app is answering        | `200`   | -       |
| `/livez`   | Liveness: restart me if this fails            | `200`   | -       |
| `/readyz`  | Readiness: send traffic only if this passes   | `200`   | `503` + `failures` |
| `/metrics` | Prometheus text exposition                    | `200`   | -       |
| `/version` | Build and resolved config (secrets redacted)  | `200`   | -       |

Cross-cutting behaviour applied to every response:

- `X-Request-ID` is accepted from the caller or generated, echoed back, and
  attached to every log record for that request.
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Cross-Origin-Opener-Policy`, `Permissions-Policy`,
  and `Strict-Transport-Security` when `APP_ENV=production`.
- Errors are JSON: `{"error": "<code>", "message": "...", "request_id": "..."}`.

---

## Configuration

Configuration is environment-only, in the twelve-factor sense. Nothing is read
from a committed file. `.env.example` is a template for local development.

### Platform variables

| Variable             | Default       | Notes                                        |
| -------------------- | ------------- | -------------------------------------------- |
| `APP_ENV`            | `development` | `production` requires `SECRET_KEY`               |
| `SECRET_KEY`         | dev fallback  | Must be set in production or startup fails    |
| `HOST` and `PORT`     | `0.0.0.0`, `8000` | Port must be 1-65535               |
| `DEBUG`              | `false`       | Flask debug mode                              |
| `MAX_CONTENT_LENGTH` | `8388608`     | Bytes; oversized bodies get `413`             |
| `DATABASE_URL`       | sqlite in `var/` | Also accepts `SQLALCHEMY_DATABASE_URI`      |
| `DATA_DIR`           | `<root>/var`   | Where the database and logs live              |
| `LOG_LEVEL`          | `INFO`        | `DEBUG INFO WARNING ERROR CRITICAL`         |
| `LOG_JSON`           | `true`        | One JSON object per line for log shippers     |
| `REQUEST_ID_HEADER`  | `X-Request-ID` | Header used for correlation ids              |

### Application variables

| Variable | Type | Default |
| --- | --- | --- |
| `APP_ENV` | string | -- |
| `SECRET_KEY` | string | -- |
| `HOST` | string | -- |
| `PORT` | string | -- |
| `DEBUG` | string | -- |
| `MAX_CONTENT_LENGTH` | string | -- |
| `DATABASE_URL` | string | -- |
| `DATA_DIR` | string | -- |
| `INSTANCE_DIR` | string | -- |
| `LOG_DIR` | string | -- |
| `LOG_LEVEL` | string | -- |
| `LOG_JSON` | string | -- |
| `REQUEST_ID_HEADER` | string | -- |
| `ANALYTICS_SALT` | string | -- |
| `PORT` | string | -- |
| `PUSHER_URL` | string | -- |

Invalid values fail fast at import with a `ConfigError` naming the offending
variable, rather than surfacing as a confusing runtime error later.

---

## HTTP API

| Path | Method | Body |
| --- | --- | --- |
| `/api/messages/<id>/retry` | O | JSON |
| `/api/messages/<id>/retry` | P | JSON |
| `/api/messages/<id>/retry` | POST | JSON |
| `/api/messages/<id>/retry` | S | JSON |
| `/api/messages/<id>/retry` | T | JSON |
| `/api/push` | O | JSON |
| `/api/push` | P | JSON |
| `/api/push` | POST | JSON |
| `/api/push` | S | JSON |
| `/api/push` | T | JSON |
| `/api/status/<id>` | E | JSON |
| `/api/status/<id>` | G | JSON |
| `/api/status/<id>` | GET | JSON |
| `/api/status/<id>` | T | JSON |

The frozen machine-readable contract is `openapi/a2_message_pusher.yaml`; it is the
source of truth for path and method coverage.

---

## Layout

```
├── .github
│   └── workflows
│       └── ci.yml
├── docs
│   ├── adr
│   │   ├── 0001-src-layout-and-runtime-state.md
│   │   └── 0002-hand-rolled-metric-exposition.md
│   ├── ARCHITECTURE.md
│   └── OPERATIONS.md
├── openapi
│   └── a2_message_pusher.yaml
├── schema
│   └── a2_message_pusher.sql
├── src
│   └── message_pusher
│       ├── pusher
│       ├── templates
│       ├── __init__.py
│       ├── _app.py
│       ├── app.py
│       ├── cli.py
│       ├── config.py
│       ├── errors.py
│       ├── http.py
│       ├── models.py
│       ├── observability.py
│       ├── paths.py
│       └── py.typed
├── tests
│   ├── conftest.py
│   ├── test_a2_message_pusher.py
│   ├── test_config.py
│   └── test_ops.py
├── .dockerignore
├── .editorconfig
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── Dockerfile
├── LICENSE
├── Makefile
├── NOTES.md
├── SECURITY.md
├── conftest.py
├── docker-compose.yml
├── docker-entrypoint.sh
├── mypy.ini
├── pyproject.toml
├── requirements-dev.txt
├── requirements.txt
└── wsgi.py
```

- `src/message_pusher/` is the only importable code. It is a real package: every
  historical flat import was rewritten to a relative one, so the modules can no
  longer be shadowed by an unrelated top-level name.
- `var/` holds all mutable state (database, logs) and is gitignored. The
  container image mounts a volume there.
- `wsgi.py` is a compatibility shim so a bare checkout is runnable. Anything
  installed with `pip install` uses the package factory directly.

---

## Development

```sh
make install   # virtualenv plus editable install with dev extras
make test      # pytest
make cov       # pytest --cov, enforces the coverage floor
make lint      # ruff check
make type      # mypy --strict
make check     # lint + type + cov: the same gate CI runs
make run       # development server
```

### Honest status of the quality gates

This project was generated in an offline sandbox, which constrains what can
truthfully be claimed:

| Gate                                        | Status in this repository |
| ------------------------------------------- | ------------------------- |
| `pytest`                                    | **Executed.** The suite passes locally. |
| `coverage`                                  | Runnable, but the 85% floor has **not** been verified end to end. |
| `mypy --strict`                             | Runnable locally; the strict configuration is committed. |
| `ruff`, `bandit`, `pip-audit`                 | **Never executed.** No network access to install them. Authored, not run. |
| CI workflow                                 | Committed, **never run** (no CI runner available). |
| Container build                             | Dockerfile committed, **never built** (no Docker daemon). |

Read the CI workflow as the intended gate, not as evidence that the gate
passed. Nothing in this repository claims a green build.

---

## Deployment

```sh
docker compose up --build     # http://localhost:8000
```

The image is multi-stage, installs from a built wheel, runs as uid 1001 with no
capabilities, has a read-only root filesystem, and declares its own
`HEALTHCHECK`. `docker-entrypoint.sh` refuses to start a production image
without `SECRET_KEY`.

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for the runbook: rollout, rollback,
log queries, and what each alert means.

---

## Documentation

| Document                                     | Contents                                  |
| -------------------------------------------- | ----------------------------------------- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Modules, request lifecycle, failure modes |
| [docs/OPERATIONS.md](docs/OPERATIONS.md)     | Runbook, alerts, capacity notes           |
| [docs/adr/](docs/adr/)                       | Architecture decision records             |
| [SECURITY.md](SECURITY.md)                   | Threat model and disclosure policy        |
| [CONTRIBUTING.md](CONTRIBUTING.md)           | Branch, commit and review conventions     |
| [CHANGELOG.md](CHANGELOG.md)                 | Release history                           |

---

## License

MIT. See [LICENSE](LICENSE).
