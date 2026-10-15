"""Operational endpoint contract tests.

These assert the interfaces an operator or an orchestrator depends on:
liveness, readiness, the metric exposition format, and a version document that
never leaks a secret.
"""
from __future__ import annotations

import json


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["service"] == "message_pusher"
    assert body["version"]


def test_livez(client):
    response = client.get("/livez")
    assert response.status_code == 200
    assert response.get_json() == {"status": "alive"}


def test_readyz(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ready"


def test_version_hides_the_secret(client):
    response = client.get("/version")
    assert response.status_code == 200
    body = response.get_json()
    assert body["version"]
    assert "config" in body and "paths" in body
    assert "test-secret-key" not in json.dumps(body)
    assert body["config"]["secret_key_configured"] is True


def test_metrics_is_prometheus_text(client):
    client.get("/healthz")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    # Exactly one charset: the media type carries the Prometheus version
    # parameter, and Werkzeug must not append a second one.
    assert response.headers["Content-Type"] == (
        "text/plain; version=0.0.4; charset=utf-8"
    )
    text = response.get_data(as_text=True)
    assert "# TYPE process_uptime_seconds gauge" in text
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        assert " " in line, "not a Prometheus sample: %r" % line


def test_request_id_is_echoed(client):
    response = client.get("/healthz", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_request_id_is_generated_when_absent(client):
    response = client.get("/healthz")
    assert len(response.headers["X-Request-ID"]) == 32


def test_security_headers_are_present(client):
    response = client.get("/healthz")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_unknown_api_path_returns_json_envelope(client):
    response = client.get("/api/definitely-not-a-route")
    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"


def test_method_not_allowed_returns_json_envelope(client):
    response = client.post("/healthz")
    assert response.status_code == 405
    assert response.get_json()["error"] == "method_not_allowed"


def test_access_log_is_json(client, capsys):
    client.get("/healthz")
    client.get("/version")
    captured = capsys.readouterr()
    lines = [line for line in (captured.out + captured.err).splitlines() if line.startswith("{")]
    assert lines, "expected at least one structured log line"
    record = json.loads(lines[-1])
    assert "request_id" in record and "service" in record
