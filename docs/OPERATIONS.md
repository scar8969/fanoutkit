# Operations runbook -- message-pusher

Audience: whoever is on call for this service.

---

## 1. Service summary

| Field         | Value                                                       |
| ------------- | ----------------------------------------------------------- |
| Service       | `message_pusher`                                                     |
| Entry point   | `gunicorn ... wsgi:app`                                       |
| Default port  | `8000`                                                        |
| Health        | `GET /healthz`                                                |
| Readiness     | `GET /readyz`                                                 |
| Metrics       | `GET /metrics`                                                |
| Version       | `GET /version`                                                |
| State         | `DATA_DIR` (default `<repo>/var`): SQLite database and JSON logs |
| Config source | Environment only; `.env.example` documents every key            |

---

## 2. Deploy

```sh
# build and run locally
docker compose up --build

# or run the installed distribution directly
pip install -e .
APP_ENV=production SECRET_KEY=... gunicorn --bind 0.0.0.0:8000 --workers 4 wsgi:app
```

A rollout order that avoids serving errors:

1. Apply any environment change first. A missing `SECRET_KEY` in production
   makes the process exit immediately, and the orchestrator will report that as a
   crash loop rather than what it actually is, a config error.
2. Start the new revision and wait for `/readyz` to return `200`. Be aware
   that `readiness_checks()` ships empty, so this only proves the process built
   its application; it does not prove the database is reachable.
3. Shift traffic.
4. Only then stop the old revision.

---

## 3. Rollback

The service holds no cross-version state beyond the database, and the schema is
additive, so rollback is "run the previous image tag":

```sh
docker compose down
IMAGE_TAG=previous docker compose up -d
curl -fsS localhost:8000/readyz
```

If a release added a column, the old revision ignores it; it does not fail. No
downtime migration step is required. Take a copy of the SQLite file before any
release that touches the schema -- it is one file, and that copy is the whole
backup story:

```sh
cp "$DATA_DIR"/instance/*.db "/backup/$(date +%Y%m%d-%H%M%S).db"
```

---

## 4. Alerts and what they mean

| Alert                              | First question                                            |
| ---------------------------------- | --------------------------------------------------------- |
| `/healthz` failing for over a minute | Is the process alive? Check the container exit code and logs. |
| `/readyz` failing but `/healthz` fine | A readiness check is failing; the response body names it. **Today no check is registered**, so `/readyz` cannot fail: add one in `app.readiness_checks()` before you alert on it. |
| `http_requests_total{status="5xx"}` rising | Read the traceback lines in the log; each carries a request id. |
| `http_request_duration_seconds_sum` rate rising | The exposition carries a running sum per method, not a histogram, so take `rate(..._sum)` yourself and compare it against `rate(http_requests_total)`. |
| `process_uptime_seconds` resetting | Crash loop. Look for a config error before a code error. |
| Disk filling                       | Log volume or database growth in `DATA_DIR`. Logs are JSON lines; rotate them. |

Every log line carries `request_id`, so a user-visible failure can be traced
end to end from a single identifier:

```sh
grep '"request_id":"<id>"' "$DATA_DIR"/log/*.log
```

---

## 5. Capacity

- Baseline footprint is one Python process: roughly 60 to 90 MB RSS per worker,
  plus the database page cache.
- Start with `--workers 4` and measure. Two series are exported:
  `http_requests_total{method,status}` as a counter, and
  `http_request_duration_seconds_sum{method}` as a running total of seconds.
  There is deliberately no histogram, no count and no p99; derive what you
  need from the rate of the two counters.
- SQLite backs a single writer. If write latency grows with replica count, that
  is the symptom; move `DATABASE_URL` to Postgres.
- SQLite `busy` errors mean lock contention. The fix is fewer concurrent
  writers, not more retries.

---

## 6. Common tasks

```sh
# what version is running, and with which configuration?
curl -s localhost:8000/version | python -m json.tool

# is readiness failing, and on what?
curl -s localhost:8000/readyz | python -m json.tool

# raw metric snapshot when the scraper is broken
curl -s localhost:8000/metrics
```

---

## 7. Known limitations

Stated here so that nobody discovers them during an incident:

- Metrics are in-process and reset on restart. Long-range history belongs in the
  scrape backend, not here.
- The log is the only trace store. There is no distributed tracing backend.
- There is no queue. Long-running work blocks the worker that accepted it.
- The suite's coverage floor (85%) is configured but has not been measured in
  this repository. See the honest-status table in the README.
