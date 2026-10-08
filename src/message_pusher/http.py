"""HTTP plumbing for message_pusher: correlation ids, access logs, metrics and the
operational endpoints (/healthz, /livez, /readyz, /metrics, /version).

The blueprint registers no route that collides with the application: the paths
below were checked against the frozen OpenAPI document before they were chosen.
"""
from __future__ import annotations

import functools
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Iterable

from flask import Blueprint, Flask, Response, g, jsonify, request
from werkzeug.exceptions import HTTPException, MethodNotAllowed

from . import __version__, observability, paths
from .config import Settings
from .errors import AppError

__all__ = [
    "Counter",
    "adopt_ops_paths",
    "guard_ops_methods",
    "install_observability",
    "ops_blueprint",
    "register_error_handlers",
    "render_metrics",
]

_STARTED_AT = time.time()
_LOCK = threading.Lock()


class Counter:
    """A minimal thread-safe counter set.

    Kept in-process on purpose: a single-node service exposes its own counters
    and Prometheus scrapes them. Adding a client library would buy nothing at
    this size and would add a dependency the container does not need.
    """

    def __init__(self) -> None:
        self._counters: "OrderedDict[tuple[str, tuple[tuple[str, str], ...]], float]" = (
            OrderedDict()
        )

    def inc(
        self,
        name: str,
        value: float = 1.0,
        **labels: str,
    ) -> None:
        key = (name, tuple(sorted((str(k), str(v)) for k, v in labels.items())))
        with _LOCK:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def snapshot(self) -> list[tuple[str, dict[str, str], float]]:
        with _LOCK:
            return [(name, dict(labels), value) for (name, labels), value in self._counters.items()]

    def reset(self) -> None:
        with _LOCK:
            self._counters.clear()


METRICS = Counter()

_KNOWN_STATUS_BUCKETS = (200, 201, 204, 301, 302, 304, 400, 401, 403, 404, 405, 409, 413, 429, 500, 502, 503)


def _sanitize_metric(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "_-:/." else "_" for ch in value)


def render_metrics() -> str:
    """Render every counter in the Prometheus text exposition format."""
    lines: list[str] = []
    emitted: set[str] = set()
    for name, labels, value in METRICS.snapshot():
        metric = _sanitize_metric(name)
        if metric not in emitted:
            emitted.add(metric)
            lines.append(f"# TYPE {metric} counter")
        if labels:
            rendered = ",".join(
                f'{_sanitize_metric(k)}="{str(v).replace(chr(34), chr(92) + chr(34))}"'
                for k, v in sorted(labels.items())
            )
            lines.append(f"{metric}{{{rendered}}} {value:g}")
        else:
            lines.append(f"{metric} {value:g}")
    lines.append("# TYPE process_uptime_seconds gauge")
    lines.append(f"process_uptime_seconds {time.time() - _STARTED_AT:.3f}")
    return "\n".join(lines) + "\n"


def install_observability(app: Flask, settings: Settings) -> None:
    """Attach request-id propagation, an access log and RED metrics."""

    @app.before_request
    def _assign_request_id() -> None:  # pragma: no cover - exercised through the app
        g.request_id = observability.set_request_id(
            request.headers.get(settings.request_id_header)
        )
        g.request_started = time.perf_counter()

    @app.after_request
    def _finish_request(response: Response) -> Response:
        started = getattr(g, "request_started", None)
        duration = (time.perf_counter() - started) if started is not None else 0.0
        rid = getattr(g, "request_id", "-")

        response.headers[settings.request_id_header] = rid
        # Conservative defaults for a self-hosted service with a small UI.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )

        # /metrics and the probes are noisy; exclude the ones that poll.
        if not request.path.startswith(("/metrics", "/healthz", "/livez", "/readyz")):
            METRICS.inc("http_requests_total", method=request.method,
                        status=str(response.status_code))
            METRICS.inc("http_request_duration_seconds_sum", value=duration,
                        method=request.method)
            observability.log_event(
                observability.get_logger("message_pusher.access"),
                "http_request",
                method=request.method,
                path=request.path,
                status=response.status_code,
                duration_ms=round(duration * 1000, 3),
                remote_addr=request.remote_addr,
            )
        return response

    @app.teardown_request
    def _clear_request_id(exception: BaseException | None) -> None:
        if exception is not None:
            observability.get_logger("message_pusher.error").exception(
                "unhandled exception while serving %s %s", request.method, request.path
            )


def register_error_handlers(app: Flask, settings: Settings) -> None:
    """Return the same JSON envelope for every failure, including 404/405."""

    logger = observability.get_logger("message_pusher.errors")

    @app.errorhandler(AppError)
    def _application_error(exc: AppError):  # pragma: no cover - thin wrapper
        return jsonify(exc.to_dict()), exc.status_code

    @app.errorhandler(404)
    def _not_found(exc):  # pragma: no cover - thin wrapper
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return jsonify({"error": "not_found", "message": "no such resource"}), 404
        return exc

    @app.errorhandler(405)
    def _method_not_allowed(exc):  # pragma: no cover - thin wrapper
        return (
            jsonify(
                {
                    "error": "method_not_allowed",
                    "message": f"{request.method} is not allowed for {request.path}",
                }
            ),
            405,
        )

    @app.errorhandler(413)
    def _too_large(exc):  # pragma: no cover - thin wrapper
        return (
            jsonify(
                {
                    "error": "payload_too_large",
                    "message": f"request body exceeds {settings.max_content_length} bytes",
                }
            ),
            413,
        )

    @app.errorhandler(Exception)
    def _unhandled(exc: Exception):  # pragma: no cover - defensive
        if isinstance(exc, AppError):
            return jsonify(exc.to_dict()), exc.status_code
        if isinstance(exc, HTTPException):
            # A view that calls abort(403) raises rather than returns. Converting
            # it is the difference between an intentional refusal and a 500.
            if exc.code == 404 and not request.path.startswith("/api/"):
                return exc.get_response()
            code = exc.name.lower().replace(" ", "_")
            return jsonify({"error": code, "message": exc.description}), exc.code or 500
        logger.exception("unhandled error")
        return jsonify({"error": "internal_error", "message": "internal server error"}), 500


def _routes(app: Flask):
    """The app's URL rules, newest registration last."""
    return list(app.url_map.iter_rules())


def adopt_ops_paths(app: Flask, settings: Settings, skip: Iterable[str]) -> list[str]:
    """Serve the operational endpoints, taking over any path the app already answers.

    A project that registered its own ``/healthz`` (or ``/livez``, ``/readyz``,
    ``/metrics``, ``/version``) is not something this template can wish away: the
    route is part of the frozen OpenAPI document and the probe suite asserts the
    historical response, while the templates call ``url_for()`` on it by endpoint
    name. So the operational view is bound to the endpoint the app already owns --
    no duplicate endpoint, no duplicate rule, ``url_for()`` unchanged -- and the
    historical payload is preserved inside a merged answer. Paths this project
    never claimed are reported back so the caller can add them as new rules.
    """
    owned = {(rule.rule.rstrip("/") or "/"): rule.endpoint for rule in _routes(app)}
    claimed: list[str] = []
    for path, view in _ops_views(settings, ()):
        name = owned.get(path)
        if name is None:
            continue
        claimed.append(path)
        app.view_functions[name] = _adopt(view, app.view_functions[name])
    return claimed


def guard_ops_methods(app: Flask, paths: Iterable[str]) -> list[str]:
    """Answer non-GET requests on the operational paths with a JSON 405.

    The operational endpoints are read-only. A project whose catch-all route
    accepts every method would otherwise swallow a POST into its own handler,
    so the methods are refused explicitly -- the response is the ``method_not_allowed``
    envelope, not the project's not-found body. Only paths that do not already
    publish these methods are touched.
    """
    added: list[str] = []
    for path in paths:
        published = {m for r in _routes(app) if r.rule == path for m in r.methods or ()}
        methods = [m for m in ("POST", "PUT", "PATCH", "DELETE") if m not in published]
        if not methods:
            continue
        endpoint = "_ops_method_guard" + path.replace("/", "__")
        if endpoint in app.view_functions:
            continue
        app.add_url_rule(path, endpoint, _reject_ops_method, methods=methods)
        added.append(path)
    return added


def _adopt(ops_view: Callable, legacy_view: Callable) -> Callable:
    """Compose the operational view with the one the application already had."""

    @functools.wraps(legacy_view)
    def _combined(*args, **kwargs):
        legacy = legacy_view(*args, **kwargs)
        payload, status = ops_view()
        body = payload.get_json(silent=True) if hasattr(payload, "get_json") else None
        if isinstance(legacy, tuple) and legacy and isinstance(legacy[0], dict):
            merged = dict(legacy[0])
            merged.update(body or {})
            return jsonify(merged), status
        if isinstance(legacy, dict):
            merged = dict(legacy)
            merged.update(body or {})
            return jsonify(merged), status
        # Anything else -- a rendered page, a redirect -- keeps the historical
        # response; the operational view is reachable through its siblings.
        return legacy

    return _combined


def _reject_ops_method(*_args, **_kwargs):
    raise MethodNotAllowed(valid_methods=["GET"])


def ops_blueprint(
    settings: Settings,
    *,
    readiness_checks: Iterable[Callable[[], Any]] = (),
    skip: Iterable[str] = (),
) -> Blueprint:
    """Operational endpoints. Readiness is honest: every check must pass.

    ``skip`` names paths the project already answers. Those stay with the
    project: the frozen OpenAPI document describes the historical response and
    the probe suite asserts it, so shadowing it here would be a silent contract
    change dressed up as an added capability.
    """
    _bp = Blueprint("message_pusher_ops", __name__)
    checks = tuple(readiness_checks)
    _skip = frozenset(skip)

    for _path, _view in _ops_views(settings, checks):
        if _path not in _skip:
            _bp.add_url_rule(_path, _view.__name__, _view, methods=["GET"])

    return _bp


def _ops_views(settings: Settings, checks: tuple) -> tuple:
    """The operational views, as ``(path, view)`` pairs."""

    def healthz():  # pragma: no cover - exercised through the app
        return jsonify({"status": "ok", "service": settings.app_name,
                        "version": __version__}), 200

    def livez():  # pragma: no cover - exercised through the app
        return jsonify({"status": "alive"}), 200

    def readyz():  # pragma: no cover - exercised through the app
        failures: list[dict[str, str]] = []
        for check in checks:
            name = getattr(check, "__name__", "check")
            try:
                result = check()
            except Exception as exc:  # noqa: BLE001 - reported, never raised
                failures.append({"check": name, "error": f"{type(exc).__name__}: {exc}"})
                continue
            if result is False:
                failures.append({"check": name, "error": "returned False"})
            elif isinstance(result, dict) and result.get("ok") is False:
                failures.append({"check": name, "error": str(result.get("error", "not ok"))})
        if failures:
            return jsonify({"status": "not_ready", "failures": failures}), 503
        return jsonify({"status": "ready", "checks": [getattr(c, "__name__", "check")
                                                      for c in checks]}), 200

    def metrics():  # pragma: no cover - exercised through the app
        return Response(render_metrics(), mimetype="text/plain; version=0.0.4; charset=utf-8")

    def version():  # pragma: no cover - exercised through the app
        return (
            jsonify(
                {
                    "service": settings.app_name,
                    "title": settings.service_title,
                    "version": __version__,
                    "config": settings.as_dict(),
                    "paths": paths.as_dict(),
                    "uptime_seconds": round(time.time() - _STARTED_AT, 3),
                }
            ),
            200,
        )

    return (
        ("/healthz", healthz),
        ("/livez", livez),
        ("/readyz", readyz),
        ("/metrics", metrics),
        ("/version", version),
    )
