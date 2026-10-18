"""Tests for the application factory seams in *message_pusher.app*.

The factory is exercised indirectly by every other module in this suite; these
tests pin the two behaviours an indirect run cannot observe -- exactly which
configuration values travel down to the project's own factory, and the
process-wide singleton the WSGI entry point relies on.
"""

from __future__ import annotations

import logging

from flask import Flask

from message_pusher import app as app_module
from message_pusher import observability
from message_pusher.config import Settings


def test_an_unset_database_url_does_not_blank_the_projects_own_uri():
    """An empty database_uri must leave the key out entirely.

    The project computes a URI for itself; forwarding an empty string would
    overwrite that default with something Flask-SQLAlchemy cannot parse.
    """
    settings = Settings(env="test", secret_key="k")
    config = app_module._legacy_config(settings)

    assert "SQLALCHEMY_DATABASE_URI" not in config
    assert config["MAX_CONTENT_LENGTH"] == settings.max_content_length
    assert config["SQLALCHEMY_TRACK_MODIFICATIONS"] is False


def test_a_supplied_database_url_travels_without_being_rewritten():
    settings = Settings(
        env="test",
        secret_key="k",
        database_uri="sqlite:///./explicit.db",
    )

    forwarded = app_module._legacy_config(settings)

    assert forwarded["SQLALCHEMY_DATABASE_URI"] == "sqlite:///./explicit.db"


def test_readiness_checks_start_empty_for_a_single_process_service():
    assert tuple(app_module.readiness_checks()) == ()


def test_load_legacy_app_returns_the_module_application_untouched():
    """With nothing to apply, the project's own application comes back as is."""
    application = app_module._load_legacy_app({})

    assert isinstance(application, Flask)


def test_load_legacy_app_applies_the_configuration_it_is_given():
    application = app_module._load_legacy_app({"PROBE_KEY": "probe-value"})
    try:
        assert application.config["PROBE_KEY"] == "probe-value"
    finally:
        application.config.pop("PROBE_KEY", None)


def test_create_app_forwards_the_database_url_to_the_application(settings):
    """The factory is a seam: what it is handed reaches the Flask application."""
    configured = Settings(
        env="test",
        secret_key="k",
        database_uri="sqlite:///./factory-probe.db",
        max_content_length=4096,
    )

    application = app_module.create_app(configured)

    assert application.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///./factory-probe.db"
    assert application.config["MAX_CONTENT_LENGTH"] == 4096
    # Restore the value the session fixture installed so no later test inherits
    # this probe URI.
    app_module.create_app(settings)
    assert application.config["MAX_CONTENT_LENGTH"] == settings.max_content_length


def test_create_app_defaults_to_the_process_settings(monkeypatch):
    """Called with no argument, the factory asks the process for its settings."""
    sentinel = Settings(env="test", secret_key="sentinel-secret", app_name="sentinel")
    monkeypatch.setattr(app_module, "get_settings", lambda: sentinel)
    declared = app_module._load_legacy_app({}).config.get("APP_NAME")

    application = app_module.create_app()

    assert application.config["APP_SETTINGS"] is sentinel
    assert application.config["SECRET_KEY"] == "sentinel-secret"
    # APP_NAME is applied with setdefault semantics: a name the project already
    # declared on its own application object wins over the template default.
    assert application.config["APP_NAME"] == declared


def test_get_app_builds_once_and_reuses_the_instance(monkeypatch):
    """The WSGI entry point must not rebuild the application per call."""
    sentinel = Flask("get_app_probe")
    calls = []

    def _fake_create_app(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(app_module, "_APP", None)
    monkeypatch.setattr(app_module, "create_app", _fake_create_app)

    assert app_module.get_app() is sentinel
    assert app_module.get_app() is sentinel
    assert len(calls) == 1


def test_get_app_returns_the_real_application_without_a_patch():
    first = app_module.get_app()

    assert isinstance(first, Flask)
    assert app_module.get_app() is first


def test_the_stdout_handler_tolerates_a_stream_without_flush(monkeypatch):
    """A replaced stdout that cannot flush must not break logging."""

    class _NoFlushStream:
        def __init__(self) -> None:
            self.written = ""

        def write(self, text: str) -> None:
            self.written += text

    stream = _NoFlushStream()
    handler = observability._StdoutHandler()
    record = logging.LogRecord(
        "message_pusher.probe", logging.INFO, __file__, 1, "hello", None, None
    )

    monkeypatch.setattr(observability.sys, "stdout", stream)
    handler.handle(record)

    assert "hello" in stream.written
