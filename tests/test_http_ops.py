"""The cross-cutting HTTP layer, exercised on isolated Flask applications.

The production app installs the layer once, on a module-level singleton, so a
second call would not re-register the hooks: Flask refuses to add request hooks
to an application that has already served a request. These tests therefore build
their own small applications and install the layer on each of them, which is the
only way to drive the production-only branches (HSTS, for one) and the adoption
of a path an application already answers.
"""
from __future__ import annotations

import logging
import re

import pytest
from flask import Flask, jsonify, request

from message_pusher import http, observability
from message_pusher.config import Settings


@pytest.fixture(autouse=True)
def restore_root_logging():
    """install_observability rewrites the root handler; put it back afterwards."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    configured = observability._CONFIGURED
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)
    observability._CONFIGURED = configured


def _build(settings, *, with_error_handlers=True):
    """A minimal application carrying the cross-cutting layer."""
    app = Flask("a2_probe")
    app.config["PROPAGATE_EXCEPTIONS"] = True
    app.config["TESTING"] = True
    observability.configure_logging("INFO", json_output=True)
    http.install_observability(app, settings)
    if with_error_handlers:
        http.register_error_handlers(app, settings)

    @app.get("/echo")
    def echo():
        return jsonify({"ok": True})

    return app


def _explode():
    raise ValueError("the database went away")


@pytest.fixture()
def production_settings():
    return Settings(env="production", secret_key="a-real-secret", secret_key_provided=True)


@pytest.fixture()
def probe_app(production_settings):
    app = _build(production_settings)
    yield app
    http.METRICS.reset()


# --------------------------------------------------------------------------
# the counter and the exposition format
# --------------------------------------------------------------------------


def test_the_counter_resets_and_snapshots():
    counter = http.Counter()
    assert counter.snapshot() == []

    counter.inc("http_requests_total", status="200")
    counter.inc("http_requests_total", status="200")
    counter.inc("http_requests_total", value=2.5, method="POST")

    assert counter.snapshot() == [
        ("http_requests_total", {"status": "200"}, 2.0),
        ("http_requests_total", {"method": "POST"}, 2.5),
    ]

    counter.reset()
    assert counter.snapshot() == []


def _render(metrics):
    original, http.METRICS = http.METRICS, metrics
    try:
        return http.render_metrics()
    finally:
        http.METRICS = original


def test_render_metrics_emits_the_exposition_format():
    metrics = http.Counter()
    metrics.inc("http_requests_total", method="GET", status="200")
    metrics.inc("bare_counter")
    metrics.inc("odd name/with space", note='say "hi"')

    text = _render(metrics)

    assert "# TYPE http_requests_total counter" in text
    assert 'http_requests_total{method="GET",status="200"} 1' in text
    assert "bare_counter 1" in text
    assert 'odd_name/with_space{note="say \\"hi\\""} 1' in text
    assert "# TYPE process_uptime_seconds gauge" in text
    assert re.search(r"^process_uptime_seconds \d+\.\d{3}$", text, re.M)
    assert text.endswith("\n")


def test_each_metric_is_typed_once_however_many_series_it_has():
    metrics = http.Counter()
    metrics.inc("http_requests_total", method="GET", status="200")
    metrics.inc("http_requests_total", method="GET", status="404")

    text = _render(metrics)

    assert text.count("# TYPE http_requests_total counter") == 1
    assert 'http_requests_total{method="GET",status="200"} 1' in text
    assert 'http_requests_total{method="GET",status="404"} 1' in text


# --------------------------------------------------------------------------
# the request hooks
# --------------------------------------------------------------------------


def test_a_production_answer_carries_the_security_headers(probe_app):
    response = probe_app.test_client().get("/echo")

    assert response.status_code == 200
    assert (
        response.headers["Strict-Transport-Security"]
        == "max-age=63072000; includeSubDomains"
    )
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response.headers["Permissions-Policy"] == "geolocation=(), microphone=(), camera=()"
    assert response.headers["X-Request-ID"]


def test_a_development_answer_omits_hsts():
    app = _build(Settings(env="development"))

    response = app.test_client().get("/echo")

    assert response.status_code == 200
    assert "Strict-Transport-Security" not in response.headers


def test_the_correlation_id_is_echoed_back(probe_app):
    client = probe_app.test_client()

    supplied = client.get("/echo", headers={"X-Request-ID": "abc-123"})
    assert supplied.headers["X-Request-ID"] == "abc-123"

    generated = client.get("/echo")
    assert generated.headers["X-Request-ID"] not in ("", "-")


def test_requests_are_counted_and_the_probes_are_excluded(probe_app):
    http.METRICS.reset()
    client = probe_app.test_client()
    client.get("/echo")
    client.get("/echo")
    client.get("/healthz")

    counted = {
        (name, tuple(sorted(labels.items()))): value
        for name, labels, value in http.METRICS.snapshot()
    }
    assert counted[("http_requests_total", (("method", "GET"), ("status", "200")))] == 2.0
    assert counted[("http_request_duration_seconds_sum", (("method", "GET"),))] > 0


class _Recorder(logging.Handler):
    """Collects formatted records, because the root logger writes to stdout."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.messages: list[str] = []
        self.exc_info: list[bool] = []

    def emit(self, record):
        self.messages.append(record.getMessage())
        self.exc_info.append(record.exc_info is not None)


def test_an_exception_during_a_request_is_logged_by_teardown(production_settings):
    app = _build(production_settings, with_error_handlers=False)

    @app.get("/boom")
    def boom():
        _explode()

    recorder = _Recorder()
    root = logging.getLogger()
    root.addHandler(recorder)
    try:
        with pytest.raises(ValueError, match="the database went away"):
            app.test_client().get("/boom")
    finally:
        root.removeHandler(recorder)

    assert "unhandled exception while serving GET /boom" in recorder.messages
    assert any(recorder.exc_info), "the traceback must travel with the record"


# --------------------------------------------------------------------------
# the method guard
# --------------------------------------------------------------------------


def test_the_guard_refuses_writes_on_a_read_only_path():
    app = _build(Settings(env="test"))
    http.register_error_handlers(app, Settings(env="test"))

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    assert http.guard_ops_methods(app, ["/healthz"]) == ["/healthz"]

    client = app.test_client()
    assert client.get("/healthz").status_code == 200
    refused = client.post("/healthz")
    assert refused.status_code == 405
    assert refused.get_json()["error"] == "method_not_allowed"
    assert refused.get_json()["message"] == "POST is not allowed for /healthz"


def test_a_path_that_already_publishes_the_write_methods_is_left_alone():
    app = _build(Settings(env="test"))

    @app.route("/healthz", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def healthz():
        return jsonify({"status": "ok"})

    assert http.guard_ops_methods(app, ["/healthz"]) == []
    assert app.test_client().post("/healthz").status_code == 200


def test_a_path_whose_guard_endpoint_is_already_taken_is_skipped():
    app = _build(Settings(env="test"))

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    app.view_functions["_ops_method_guard__healthz"] = lambda: ("reserved", 200)

    assert http.guard_ops_methods(app, ["/healthz"]) == []


def _catch_all_app(*, guarded):
    """An application whose catch-all route accepts every HTTP method."""
    settings = Settings(env="test")
    app = _build(settings)
    http.register_error_handlers(app, settings)

    @app.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def catch_all(path):
        return jsonify({"swallowed": request.method, "path": path})

    if guarded:
        assert http.guard_ops_methods(app, ["/metrics"]) == ["/metrics"]
    return app


def test_without_the_guard_a_catch_all_swallows_the_write():
    """The failure the guard exists to prevent, shown on an unguarded app.

    Flask refuses add_url_rule once an application has handled a request, so the
    before-and-after states cannot share one application object. They are two
    applications built the same way, one with the guard installed and one
    without.
    """
    response = _catch_all_app(guarded=False).test_client().post("/metrics")

    assert response.status_code == 200
    assert response.get_json() == {"swallowed": "POST", "path": "metrics"}


def test_the_guard_refuses_the_write_and_leaves_the_read_alone():
    client = _catch_all_app(guarded=True).test_client()

    refused = client.post("/metrics")
    assert refused.status_code == 405
    assert refused.get_json() == {
        "error": "method_not_allowed",
        "message": "POST is not allowed for /metrics",
    }

    # The read still reaches the project's own handling of the path.
    assert client.get("/metrics").get_json() == {"swallowed": "GET", "path": "metrics"}


def test_a_guarded_path_with_no_get_route_of_its_own_answers_405():
    """A guarded path with nothing else on it reports the method, not 404.

    The shipped wiring cannot reach this state -- every operational path is
    either claimed by the project or registered by the blueprint -- but the
    guard is a standalone function and this is its documented behaviour, so it
    is pinned here rather than left to a future caller to discover.
    """
    settings = Settings(env="test")
    app = _build(settings)
    http.register_error_handlers(app, settings)

    assert http.guard_ops_methods(app, ["/metrics"]) == ["/metrics"]

    client = app.test_client()
    assert client.post("/metrics").status_code == 405
    assert client.get("/metrics").status_code == 405
    assert client.get("/metrics").get_json()["error"] == "method_not_allowed"


# --------------------------------------------------------------------------
# adoption of a path the application already answers
# --------------------------------------------------------------------------


def test_adoption_merges_the_operational_payload_into_a_tuple_response():
    app = Flask("a2_adopted")
    app.config["TESTING"] = True
    settings = Settings(env="test")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "project": "message_pusher"}, 200

    assert http.adopt_ops_paths(app, settings, ()) == ["/healthz"]

    payload = app.test_client().get("/healthz").get_json()
    assert payload["project"] == "message_pusher"
    assert payload["service"] == settings.app_name
    assert payload["version"]
    assert payload["status"] == "ok"


def test_adoption_merges_into_a_bare_dict_response():
    app = Flask("a2_adopted_dict")
    app.config["TESTING"] = True
    settings = Settings(env="test")

    @app.get("/livez")
    def livez():
        return {"status": "alive", "project": "message_pusher"}

    assert http.adopt_ops_paths(app, settings, ()) == ["/livez"]

    assert app.test_client().get("/livez").get_json() == {
        "status": "alive",
        "project": "message_pusher",
    }


def test_adoption_keeps_a_rendered_page_verbatim():
    app = Flask("a2_adopted_page")
    app.config["TESTING"] = True
    settings = Settings(env="test")

    @app.get("/readyz")
    def readyz():
        return "<html>the project readiness page</html>", 200, {"X-Project": "message_pusher"}

    assert http.adopt_ops_paths(app, settings, ()) == ["/readyz"]

    response = app.test_client().get("/readyz")
    assert response.get_data(as_text=True) == "<html>the project readiness page</html>"
    assert response.headers["X-Project"] == "message_pusher"


def test_a_path_the_application_never_claimed_is_left_for_the_blueprint():
    app = Flask("a2_untouched")
    app.config["TESTING"] = True
    settings = Settings(env="test")

    assert http.adopt_ops_paths(app, settings, ()) == []
    assert app.test_client().get("/healthz").status_code == 404


# --------------------------------------------------------------------------
# the blueprint
# --------------------------------------------------------------------------


def test_the_blueprint_serves_the_probes_and_refuses_writes():
    settings = Settings(env="prod", secret_key="s3cret", secret_key_provided=True)

    def healthy():
        return True

    app = Flask("a2_ops")
    app.config["TESTING"] = True
    http.register_error_handlers(app, settings)
    app.register_blueprint(
        http.ops_blueprint(settings, readiness_checks=(healthy,), skip=("/version",))
    )
    guarded = http.guard_ops_methods(app, ("/healthz", "/livez", "/readyz", "/metrics"))
    assert guarded == ["/healthz", "/livez", "/readyz", "/metrics"]

    client = app.test_client()
    assert client.get("/healthz").get_json()["status"] == "ok"
    assert client.get("/livez").get_json() == {"status": "alive"}
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.get_json() == {"status": "ready", "checks": ["healthy"]}

    # Skipped: the blueprint leaves the path to the project, so nothing is
    # registered for it here.
    assert client.get("/version").status_code == 404

    metrics = client.get("/metrics")
    assert metrics.mimetype == "text/plain"
    assert "process_uptime_seconds" in metrics.get_data(as_text=True)

    refused = client.post("/healthz")
    assert refused.status_code == 405
    assert refused.get_json()["error"] == "method_not_allowed"
    assert client.delete("/metrics").status_code == 405


def test_readiness_reports_every_way_a_check_can_fail():
    def returns_false():
        return False

    def raises():
        raise RuntimeError("the database went away")

    def returns_not_ok():
        return {"ok": False, "error": "the queue is backed up"}

    app = Flask("a2_not_ready")
    app.config["TESTING"] = True
    app.register_blueprint(
        http.ops_blueprint(
            Settings(env="test"),
            readiness_checks=(returns_false, raises, returns_not_ok),
        )
    )

    response = app.test_client().get("/readyz")

    assert response.status_code == 503
    assert response.get_json()["status"] == "not_ready"
    failures = response.get_json()["failures"]
    assert [failure["check"] for failure in failures] == [
        "returns_false",
        "raises",
        "returns_not_ok",
    ]
    assert failures[0]["error"] == "returned False"
    assert failures[1]["error"] == "RuntimeError: the database went away"
    assert failures[2]["error"] == "the queue is backed up"
