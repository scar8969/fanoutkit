"""Application factory for message_pusher.

The factory is the single seam every entry point uses (WSGI, CLI, tests). It
takes the Settings object, prepares the runtime directories, installs
structured logging, and then layers cross-cutting HTTP concerns -- correlation
ids, security headers, error envelopes and the operational endpoints -- on top
of the project's own Flask application. Existing route behaviour is untouched.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from flask import Flask

from . import http, observability, paths
from .config import Settings, get_settings

__all__ = ["create_app", "get_app"]

_APP: Flask | None = None

#: Operational paths this template publishes. A path the project already
#: answers keeps serving its historical payload -- the frozen OpenAPI document
#: describes it and the probe suite asserts it -- with the operational data
#: merged in rather than replacing it. See http.adopt_ops_paths().
_OPS_PATHS = ("/healthz", "/livez", "/readyz", "/metrics", "/version")


def readiness_checks() -> Iterable[Callable[[], Any]]:
    """Checks that must pass before the instance receives traffic.

    An empty tuple is the honest answer for a single-process service: readiness
    is then exactly "the WSGI stack imported and the app built". A project that
    gains a real dependency should add a check here.
    """
    return ()


def _legacy_config(settings: Settings) -> dict[str, Any]:
    """Configuration values the project's own factory is allowed to take.

    Only knobs that are meaningful outside the template travel here, and only
    when they were actually supplied: an unset DATABASE_URL must not blank out
    the URI the project computes for itself.
    """
    config: dict[str, Any] = {
        "MAX_CONTENT_LENGTH": settings.max_content_length,
        "SQLALCHEMY_TRACK_MODIFICATIONS": settings.sqlalchemy_track_modifications,
    }
    if settings.database_uri:
        config["SQLALCHEMY_DATABASE_URI"] = settings.database_uri
    return config


def _load_legacy_app(config: dict[str, Any]) -> Flask:
    """Build a fresh instance of the project's own Flask application."""
    from ._app import app

    if config:
        app.config.update(config)
    return app


def create_app(settings: Settings | None = None) -> Flask:
    """Build the WSGI application."""
    settings = settings or get_settings()
    paths.ensure_runtime_dirs()
    observability.configure_logging(settings.log_level, json_output=settings.log_json)
    log = observability.get_logger("message_pusher.startup")

    app = _load_legacy_app(_legacy_config(settings))

    app.config["APP_SETTINGS"] = settings
    app.config.setdefault("APP_NAME", settings.app_name)
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["DEBUG"] = settings.debug

    # The legacy application object is a module-level singleton for most
    # projects, so a second create_app() call would otherwise re-install the
    # cross-cutting layers on an app that has already served a request --
    # Flask refuses that ("setup method can no longer be called"). Install
    # them exactly once per application object.
    if not app.config.get("CROSS_CUTTING_INSTALLED"):
        taken = {rule.rule for rule in app.url_map.iter_rules()}
        # Paths this project already answers are served through the endpoint it
        # registered; the rest become new read-only rules on the blueprint.
        claimed = http.adopt_ops_paths(app, settings, taken)
        http.install_observability(app, settings)
        http.register_error_handlers(app, settings)
        app.register_blueprint(
            http.ops_blueprint(settings, readiness_checks=readiness_checks(), skip=claimed)
        )
        # Operational endpoints are read-only: refuse writes explicitly so a
        # project catch-all cannot swallow them into its own handler.
        http.guard_ops_methods(app, _OPS_PATHS)
        app.config["CROSS_CUTTING_INSTALLED"] = True

    log.info(
        "application_started",
        extra={
            "event": "application_started",
            "version": settings.app_version,
            "env": settings.env,
            "debug": settings.debug,
            "route_count": len(list(app.url_map.iter_rules())),
        },
    )
    return app


def get_app() -> Flask:
    """Process-wide singleton used by the WSGI entry point."""
    global _APP
    if _APP is None:
        _APP = create_app()
    return _APP
