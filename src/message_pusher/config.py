"""Environment-driven configuration for message_pusher.

Configuration is read from the process environment only (twelve-factor). No
secret is committed to the repository: .env.example documents every variable and
.env is ignored by git. Settings are frozen after construction so an import
cannot silently reconfigure a running process.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

from . import paths

__all__ = ["Settings", "ConfigError", "get_settings", "reset_settings", "LEGACY_ENV_VARS"]

#: Environment reads that the application modules perform directly. They are
#: collected here so an operator can discover the whole surface in one place.
LEGACY_ENV_VARS: tuple[str, ...] = (
    'ANALYTICS_SALT',
    'PORT',
    'PUSHER_URL',
)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_LOG_LEVELS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")


class ConfigError(RuntimeError):
    """Raised when the environment cannot produce a usable configuration."""


def _as_bool(source: Mapping[str, str], name: str, default: bool) -> bool:
    raw = source.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value == "":
        return default
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ConfigError(f"{name} must be a boolean, got {raw!r}")


def _as_int(raw: str, name: str, *, minimum: int | None = None) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration."""

    app_name: str = "message_pusher"
    service_title: str = "message-pusher"
    env: str = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str = "change-me-in-production"
    secret_key_provided: bool = False
    database_uri: str = ""
    sqlalchemy_track_modifications: bool = False
    log_level: str = "INFO"
    log_json: bool = True
    data_dir: str = ""
    instance_dir: str = ""
    request_id_header: str = "X-Request-ID"
    max_content_length: int = 8 * 1024 * 1024
    extras: Mapping[str, str] = field(default_factory=dict)

    @property
    def is_production(self) -> bool:
        return self.env.lower() in {"prod", "production"}

    @property
    def app_version(self) -> str:
        from . import __version__

        return __version__

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if environ is None else environ

        def get(name: str, default: str = "") -> str:
            value = source.get(name)
            return default if value is None or value == "" else value

        secret = get("SECRET_KEY")
        env_name = get("APP_ENV", get("FLASK_ENV", "development"))

        settings = cls(
            app_name=get("APP_NAME", "message_pusher"),
            service_title=cls.service_title,
            env=env_name,
            debug=_as_bool(source, "DEBUG", False),
            host=get("HOST", "0.0.0.0"),
            port=_as_int(get("PORT", "8000"), "PORT", minimum=1),
            secret_key=secret or "change-me-in-production",
            secret_key_provided=bool(secret),
            database_uri=get("DATABASE_URL", get("SQLALCHEMY_DATABASE_URI", "")),
            sqlalchemy_track_modifications=_as_bool(
                source, "SQLALCHEMY_TRACK_MODIFICATIONS", False
            ),
            log_level=get("LOG_LEVEL", "INFO").upper(),
            log_json=_as_bool(source, "LOG_JSON", True),
            data_dir=str(paths.DATA_DIR),
            instance_dir=str(paths.INSTANCE_DIR),
            request_id_header=get("REQUEST_ID_HEADER", "X-Request-ID"),
            max_content_length=_as_int(
                get("MAX_CONTENT_LENGTH", str(8 * 1024 * 1024)), "MAX_CONTENT_LENGTH", minimum=1
            ),
            extras={name: source[name] for name in LEGACY_ENV_VARS if name in source},
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not 0 < self.port <= 65535:
            raise ConfigError(f"PORT out of range: {self.port}")
        if self.log_level not in _LOG_LEVELS:
            raise ConfigError(
                "LOG_LEVEL must be one of " + ", ".join(_LOG_LEVELS) + f", got {self.log_level!r}"
            )
        if self.is_production and not self.secret_key_provided:
            raise ConfigError(
                "SECRET_KEY must be set when APP_ENV is production; refusing to start "
                "with the development default."
            )

    def as_dict(self) -> dict[str, object]:
        """Redacted view used by /version and the startup log line."""
        return {
            "app_name": self.app_name,
            "env": self.env,
            "debug": self.debug,
            "host": self.host,
            "port": self.port,
            "log_level": self.log_level,
            "log_json": self.log_json,
            "secret_key_configured": self.secret_key_provided,
            "database_configured": bool(self.database_uri),
            "data_dir": self.data_dir,
            "legacy_env_present": sorted(self.extras),
        }


_CACHED: Settings | None = None


def get_settings(refresh: bool = False) -> Settings:
    """Return the process-wide settings, building them on first use."""
    global _CACHED
    if _CACHED is None or refresh:
        _CACHED = Settings.from_env()
    return _CACHED


def reset_settings() -> None:
    """Drop the cache. Used by tests and by reload-style deployments."""
    global _CACHED
    _CACHED = None
