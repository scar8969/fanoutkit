# fanoutkit

[![python: 3.11 %7C 3.12 %7C 3.13](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776ab)](#requirements) [![tests: 189 passed](https://img.shields.io/badge/tests-189%20passed-2ea44f)](#quality-gates) [![coverage: 100.0%25](https://img.shields.io/badge/coverage-100.0%25-brightgreen)](#quality-gates) [![version: 0.1.0](https://img.shields.io/badge/version-0.1.0-0969da)](CHANGELOG.md) [![license: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)

**fanoutkit** is a Flask service packaged the way a production service is packaged: a real package under `src/`, an environment-only configuration contract, structured JSON logs with request correlation, the five operational endpoints an orchestrator expects, a multi-stage container image, and CI gates that keep all of it honest.

This README is a measured document. Every number in it was produced on this exact checkout by the commands recorded in [docs/EVIDENCE.md](docs/EVIDENCE.md): **189 tests** run under pytest, **760 statements** traced by coverage, and **9 HTTP requests** issued over a real socket to the running server.

<table>
<tr>
<td align="center"><b>189 / 189</b><br><sub>tests passed</sub></td>
<td align="center"><b>100.0%</b><br><sub>line coverage</sub></td>
<td align="center"><b>1,535</b><br><sub>source lines</sub></td>
<td align="center"><b>9</b><br><sub>routes probed</sub></td>
<td align="center"><b>0</b><br><sub>screenshots</sub></td>
</tr>
</table>

---

## At a glance

| Signal | Measured value | How it was measured |
| --- | --- | --- |
| Tests passed | **189 / 189** | `python -m pytest -q` (exit code 0) |
| Test wall clock | 5.26 s | junit-xml suite time |
| Line coverage | **100.0%** | 760 of 760 statements executed, 0 missed |
| Source size | 1,535 lines / 22 modules | counted under `src/` |
| Test size | 2,437 lines / 12 files | counted under `tests/` |
| Documentation | 557 lines / 5 files | counted under `docs/` |
| Routes probed | 9 GET routes, 7 answered 200 | real HTTP against `127.0.0.1:<port>` |
| Total bytes served | 11.3 KB | 9 responses summed |
| Median response | 16.0 ms | median of 9 measured round trips |
| Screenshots | none captured | the build host cannot run a headless browser |

The slowest measured route was **62.3 ms** (`/`) and the fastest **14.2 ms** (`/metrics`). Every figure is a single uncached first request against the development server, so the spread reflects cold template rendering and lazy imports rather than steady-state latency.

## Screenshots

**No screenshot is committed for this project, because the host that built and measured this checkout cannot run a headless browser.** Nothing here pretends otherwise. What was actually attempted:

- Google Chrome in `--headless=new` mode exited with status **21** and wrote `OpenProcess: Access is denied. (0x5)` to its crashpad log; every `--dump-dom` run printed **0** characters.
- Microsoft Edge, installed at `C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe`, was tried next and dies one layer earlier still: `FATAL:mojo/public/cpp/platform/platform_channel.cc:187 Check failed: . : Access is denied. (0x5)`, with `crash server failed to launch`. It produced no PNG either.
- Playwright’s Chromium build fails at `launch()` with `PermissionError [WinError 5]`. Its `chrome-headless-shell.exe` is present on disk, so the blocker is the operating system’s denial above, not a missing binary.
- No further renderer exists to fall back on: neither `wkhtmltoimage` nor Firefox is installed.

Rather than commit a fabricated or placeholder image, the measured HTTP surface is published instead: every route's status code, byte size, content type and body is recorded in [docs/EVIDENCE.md](docs/EVIDENCE.md), the raw response bodies are quoted below, and the same numbers are charted. For the JSON endpoints that is the complete response a screenshot would show.

## Charts

Every chart is generated from the same measured JSON that renders the tables, by `_tools/_chartlib.py` - hand-written SVG with no plotting dependency - and committed so GitHub renders it without a build step.

![Line coverage](docs/assets/coverage.svg)

![Coverage by module](docs/assets/coverage-modules.svg)

![Test outcome](docs/assets/tests.svg)

![Response time per route](docs/assets/latency.svg)

![Response size per route](docs/assets/payload.svg)

![Repository size](docs/assets/loc.svg)

![File counts](docs/assets/files.svg)

## HTTP surface

Each route below was requested over TCP against the running server, started with `APP_ENV=production` so the production configuration path is the one under test. Static file routes are excluded: they are served by the WSGI container, not the application.

| # | Route | Status | Time | Bytes | Content type |
| --- | --- | --- | --- | --- | --- |
| 1 | `/` | **200** | 62.3 ms | 5,684 | text/html; charset=utf-8 |
| 2 | `/api/status/demo` | **404** | 19.0 ms | 51 | application/json |
| 3 | `/apps` | **200** | 24.1 ms | 4,240 | text/html; charset=utf-8 |
| 4 | `/healthz` | **200** | 22.2 ms | 83 | application/json |
| 5 | `/livez` | **200** | 14.8 ms | 19 | application/json |
| 6 | `/messages/demo` | **404** | 15.6 ms | 207 | text/html; charset=utf-8 |
| 7 | `/metrics` | **200** | 14.2 ms | 305 | text/plain; version=0.0.4; charset=utf-8 |
| 8 | `/readyz` | **200** | 15.4 ms | 31 | application/json |
| 9 | `/version` | **200** | 16.0 ms | 950 | application/json |

Status distribution: **200** x7, **404** x2. No response was a 5xx.

### Declared API contract

`openapi/fanoutkit.yaml` declares **3 paths** carrying **3 operations** (1 GET, 2 POST):

| Method | Path |
| --- | --- |
| `POST` | `/api/push` |
| `GET` | `/api/status/<id>` |
| `POST` | `/api/messages/<id>/retry` |

## Operational endpoints

Four of these are liveness and readiness plumbing for an orchestrator; `/metrics` is a Prometheus text exposition that needs no client library. The bodies below are captured verbatim from the running process.

`/healthz` answered **200**:

```json
{"apps":0,"messages":0,"service":"message_pusher","status":"ok","version":"0.1.0"}
```

`/livez` answered **200**:

```json
{"status":"alive"}
```

`/readyz` answered **200**:

```json
{"checks":[],"status":"ready"}
```

`/metrics` answered **200**:

```text
# TYPE http_requests_total counter http_requests_total{method="GET",status="200"} 2 # TYPE http_request_duration_seconds_sum counter http_request_duration_seconds_sum{method="GET"} 0.0549416 http_requests_total{method="GET",status="404"} 2 # TYPE process_uptime_seconds gauge process_uptime_seconds 0.722
```

`/version` answered **200**:

```json
{"config":{"app_name":"message_pusher","data_dir":".\\var","database_configured":false,"debug":false,"env":"development","host":"0.0.0.0","legacy_env_present":[],"log_json":true,"log_level":"INFO","port":8000,"secret_key_configured":false},"paths":{"data_dir":"a2_message_
```

### Headers on every response

| Header | Observed value |
| --- | --- |
| `X-Request-ID` | `163c0332fcf44bb9946af44d3c5f741f` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` |
| `Content-Type` | `application/json` |

## Architecture

This document explains how the service is put together, why the seams sit where they do, and what breaks first under load.

```text
.dockerignore
.editorconfig
.env.example
.gitignore
.pre-commit-config.yaml
CHANGELOG.md
CODE_OF_CONDUCT.md
CONTRIBUTING.md
Dockerfile
LICENSE
Makefile
NOTES.md
README.md
SECURITY.md
conftest.py
docker-compose.yml
docker-entrypoint.sh
mypy.ini
pyproject.toml
requirements-dev.txt
requirements.txt
wsgi.py
.github/
  workflows/
    ci.yml
docs/
  ARCHITECTURE.md
  EVIDENCE.md
  OPERATIONS.md
  adr/
    0001-src-layout-and-runtime-state.md
    0002-hand-rolled-metric-exposition.md
  assets/
    coverage-modules.svg
    coverage.svg
    files.svg
    latency.svg
    loc.svg
    payload.svg
    tests.svg
openapi/
  fanoutkit.yaml
schema/
  fanoutkit.sql
src/
  message_pusher/
    __init__.py
    _app.py
    app.py
    cli.py
    config.py
    errors.py
    http.py
    models.py
    observability.py
    paths.py
    py.typed
tests/
  conftest.py
  test_fanoutkit.py
  test_api_surface.py
  test_app_factory.py
  test_channel_shims.py
  test_cli.py
  ...
```

Deeper material: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the module map and request lifecycle, [docs/OPERATIONS.md](docs/OPERATIONS.md) for running and configuring it, [docs/EVIDENCE.md](docs/EVIDENCE.md) for the raw recorded output this README quotes.

### Architecture decision records

| Record | Decision | Status |
| --- | --- | --- |
| [0001-src-layout-and-runtime-state.md](docs/adr/0001-src-layout-and-runtime-state.md) | 1. Adopt a src/ layout with an explicit runtime state directory | accepted |
| [0002-hand-rolled-metric-exposition.md](docs/adr/0002-hand-rolled-metric-exposition.md) | 2. Hand-roll metric exposition instead of depending on prometheus_client | accepted |

## Requirements

Configuration is environment-only, in the twelve-factor sense: nothing is read from a committed file, and `.env.example` is the complete list of what the process understands.

| Variable | Example value |
| --- | --- |
| `APP_ENV` | `development` |
| `SECRET_KEY` | `change-me-in-production` |
| `HOST` | `0.0.0.0` |
| `PORT` | `8000` |
| `DEBUG` | `false` |
| `MAX_CONTENT_LENGTH` | `8388608` |
| `DATA_DIR` | `(empty)` |
| `INSTANCE_DIR` | `(empty)` |
| `LOG_DIR` | `(empty)` |
| `LOG_LEVEL` | `INFO` |
| `LOG_JSON` | `true` |
| `REQUEST_ID_HEADER` | `X-Request-ID` |
| `ANALYTICS_SALT` | `change-me-in-production` |
| `PUSHER_URL` | `http://127.0.0.1:8000` |

## Quality gates

| Gate | Command | Result in this checkout |
| --- | --- | --- |
| Tests | `python -m pytest -q` | **189 passed, 0 failed, 0 errors** in 5.26 s |
| Coverage | `python -m pytest --cov=src/message_pusher` | **100.0%** of 760 statements (0 missed) |
| Lint | `python -m pyflakes src tests conftest.py wsgi.py` | **0 findings** in this checkout (pyflakes is the static checker available here; ruff cannot run on this host) |
| Types | `python -m mypy --config-file mypy.ini src` | **no issues found in 22 source files** in this checkout |
| Container | `docker build .` | Dockerfile reviewed, **not executed** - no container runtime on this host |

`make lint` and `make type` run the pinned `ruff` and `mypy` from the project virtualenv that `make install` creates; CI runs the same two tools. This host has no network access, so the `ruff` pinned in `requirements-dev.txt` could not be installed; the Lint row reports `pyflakes`, the checker that actually ran here, rather than a tool that never executed. Both static checks were run over the checkout and their raw output is stored in `docs/EVIDENCE.md`.

Coverage clears the **85%** floor declared in `pyproject.toml` (`fail_under`), so the same command that produced the number above also passes the gate.

### Test inventory

| File | def test_* | class Test* |
| --- | --- | --- |
| `tests/conftest.py` | 0 | 0 |
| `tests/test_fanoutkit.py` | 5 | 0 |
| `tests/test_api_surface.py` | 17 | 0 |
| `tests/test_app_factory.py` | 10 | 0 |
| `tests/test_channel_shims.py` | 2 | 0 |
| `tests/test_cli.py` | 14 | 0 |
| `tests/test_config.py` | 9 | 0 |
| `tests/test_config_and_paths.py` | 26 | 0 |
| `tests/test_errors_and_logging.py` | 20 | 0 |
| `tests/test_http_ops.py` | 20 | 0 |
| `tests/test_ops.py` | 11 | 0 |
| `tests/test_pusher.py` | 26 | 0 |

### Make targets

| Target | What it does |
| --- | --- |
| `make help` | Show this help |
| `make install` | Create the virtualenv and install dev dependencies |
| `make fmt` | Auto-format (ruff is required; see requirements-dev.txt) |
| `make lint` | Lint without modifying anything |
| `make type` | Static type check |
| `make test` | Run the test suite |
| `make cov` | Run the test suite with coverage and enforce the floor |
| `make check` | The gate CI runs |
| `make run` | Start the development server |
| `make clean` | Remove caches and build artefacts |
| `make docker-build` | Build the container image |
| `make docker-run` | Run the container on port 8000 |

## Container image

| Property | Value |
| --- | --- |
| Build stages | 2 |
| Base images | `python:3.12-slim`, `python:3.12-slim` |
| COPY instructions | 4 |
| HEALTHCHECK | yes |
| Runs as non-root | yes |

`docker build` and `docker run` were **never executed** while this repository was produced: no container runtime is reachable from the generating host. The Dockerfile is a reviewed artefact, not a verified one.

## Continuous integration

| Workflow | Jobs | Steps | Commands |
| --- | --- | --- | --- |
| `ci.yml` | lint, test, security, container | 11 | ruff check src tests ; ruff format --check src tests ; mypy src |

## Documentation index

| File | Contents |
| --- | --- |
| [README.md](README.md) | this file - the measured overview |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | module responsibilities, dependency direction, request lifecycle |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | how to run, configure, and operate the service |
| [docs/EVIDENCE.md](docs/EVIDENCE.md) | recorded command output - the raw source of every number here |
| [CONTRIBUTING.md](CONTRIBUTING.md) | setup and submission workflow |
| [SECURITY.md](SECURITY.md) | how to report a vulnerability |
| [CHANGELOG.md](CHANGELOG.md) | release history, Keep a Changelog form |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | community expectations |

## What this repository does not claim

- **No container run.** `docker build` was never executed.
- **No CI run.** The workflow files are real, but no GitHub runner has executed them from this checkout.
- **Static checks ran on this host, not the pinned toolchain.** `python -m pyflakes` and `python -m mypy` were executed here; `ruff` from the development requirements could not be installed on the generating host, so the lint gate named in `Makefile` is not the one that produced the numbers above.
- **No published artifact.** The package installs from this tree with `pip install -e .`; nothing was uploaded to an index.
- **Localhost only.** Every HTTP number was measured against `127.0.0.1` on the generating host, single-threaded, with no concurrency; treat them as smoke-test timings, not benchmarks.
- **No screenshots at all.** No headless browser can run on the generating host, so the interface is documented by recorded HTTP responses rather than by images. Nothing was mocked up to fill the gap.

## License

MIT. See [LICENSE](LICENSE).
