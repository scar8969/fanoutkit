"""Configuration contract tests.

Environment parsing is the one place a typo in a deployment manifest becomes a
runtime failure, so every branch is asserted here rather than assumed.
"""

from __future__ import annotations

import pytest

from message_pusher.config import ConfigError, Settings


def test_defaults_are_development_safe():
    settings = Settings.from_env({})
    assert settings.env == "development"
    assert settings.port == 8000
    assert settings.log_level == "INFO"
    assert settings.secret_key_provided is False
    assert settings.is_production is False


def test_secret_is_required_in_production():
    with pytest.raises(ConfigError, match="SECRET_KEY"):
        Settings.from_env({"APP_ENV": "production"})
    settings = Settings.from_env({"APP_ENV": "production", "SECRET_KEY": "s3cret"})
    assert settings.secret_key_provided is True
    assert settings.is_production is True


def test_port_must_be_a_number_in_range():
    with pytest.raises(ConfigError, match="PORT"):
        Settings.from_env({"PORT": "not-a-port"})
    with pytest.raises(ConfigError, match="PORT"):
        Settings.from_env({"PORT": "0"})
    with pytest.raises(ConfigError, match="PORT"):
        Settings.from_env({"PORT": "70000"})


def test_booleans_accept_the_documented_spellings():
    for raw in ("1", "true", "TRUE", "Yes", "on"):
        assert Settings.from_env({"LOG_JSON": raw}).log_json is True
    for raw in ("0", "false", "No", "off"):
        assert Settings.from_env({"LOG_JSON": raw}).log_json is False
    with pytest.raises(ConfigError, match="LOG_JSON"):
        Settings.from_env({"LOG_JSON": "maybe"})


def test_log_level_is_validated():
    assert Settings.from_env({"LOG_LEVEL": "debug"}).log_level == "DEBUG"
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        Settings.from_env({"LOG_LEVEL": "chatty"})


def test_database_uri_accepts_both_spellings():
    assert Settings.from_env({"DATABASE_URL": "sqlite:///x.db"}).database_uri == "sqlite:///x.db"
    assert (
        Settings.from_env({"SQLALCHEMY_DATABASE_URI": "sqlite:///y.db"}).database_uri
        == "sqlite:///y.db"
    )


def test_as_dict_is_redacted():
    settings = Settings.from_env({"SECRET_KEY": "do-not-log-me"})
    rendered = settings.as_dict()
    assert settings.secret_key not in repr(rendered)
    assert rendered["secret_key_configured"] is True


def test_settings_are_immutable():
    settings = Settings.from_env({})
    with pytest.raises(Exception):
        settings.port = 1  # type: ignore[misc]


def test_get_settings_caches_until_reset(monkeypatch):
    from message_pusher import config

    config.reset_settings()
    monkeypatch.setenv("PORT", "9123")
    assert config.get_settings().port == 9123
    monkeypatch.setenv("PORT", "9124")
    assert config.get_settings().port == 9123
    assert config.get_settings(refresh=True).port == 9124
    config.reset_settings()
