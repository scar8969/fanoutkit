# 2. Hand-roll metric exposition instead of depending on prometheus_client

- Status: accepted
- Date: 2026-10-08
- Deciders: maintainers

## Context

The service must expose `/metrics` in Prometheus text exposition format. The
obvious choice is the `prometheus_client` library. It was not installable in
the environment that produced this project, and adding an undeclared,
unverified dependency would mean shipping code that has never executed.

## Decision

Implement the minimal useful subset in `message_pusher.http`: a thread-safe
`Counter`, a small registry, and a renderer that emits valid exposition text
plus `process_uptime_seconds`. Counters are labelled by HTTP method and
status class.

## Consequences

**Positive**

- Zero dependencies for observability. The metrics endpoint cannot break because
  a third-party package changed.
- The exposition format is verified by a test that asserts every emitted line is
  a valid sample.
- The subset is small enough to audit: there is no dynamic collector, no
  multiprocess mode, and no hidden global state.

**Negative**

- No histogram or summary type, so request duration is exported only as a
  running `http_request_duration_seconds_sum{method}` counter: there is no
  count, no bucket and no p99. A scraper that wants percentiles must derive
  them from the rate of that sum, which is an approximation.
- No `prometheus_client` multiprocess support. Metrics are per worker, which
  is correct for the scrape model but means per-process values must not be summed
  as if they were cluster totals.
- If the project later needs histograms or exemplars, this module should be
  replaced rather than extended.

## Alternatives considered

- **Depend on `prometheus_client`.** Preferred in principle, but unavailable
  and unverifiable here.
- **Expose metrics as JSON and let a bridge convert them.** Adds a moving part in
  production and gives up the standard scrape contract.
