"""Filesystem layout for message_pusher.

Every path is derived from this module's own location, so the package works
identically whether it is imported from a source checkout, an editable install
or a wheel. Nothing here depends on the current working directory.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_PREFIX = "MESSAGE_PUSHER"

PACKAGE_DIR: Path = Path(__file__).resolve().parent
SRC_DIR: Path = PACKAGE_DIR.parent
PROJECT_ROOT: Path = SRC_DIR.parent

TEMPLATES_DIR: Path = PACKAGE_DIR / "templates"
STATIC_DIR: Path = PACKAGE_DIR / "static"


def _env_path(name: str, default: Path) -> Path:
    """Resolve a directory from the environment, accepting either the prefixed
    or the bare spelling of the variable."""
    raw = os.environ.get(ENV_PREFIX + name) or os.environ.get(name)
    if raw:
        return Path(raw).expanduser()
    return default


DATA_DIR: Path = _env_path("DATA_DIR", PROJECT_ROOT / "var")
INSTANCE_DIR: Path = _env_path("INSTANCE_DIR", DATA_DIR / "instance")
LOG_DIR: Path = _env_path("LOG_DIR", DATA_DIR / "log")


def ensure_runtime_dirs() -> None:
    """Create the writable runtime directories. Safe to call repeatedly."""
    for directory in (DATA_DIR, INSTANCE_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def as_dict() -> dict[str, str]:
    """Machine-readable view used by the /version endpoint."""
    return {
        "package_dir": str(PACKAGE_DIR),
        "project_root": str(PROJECT_ROOT),
        "templates_dir": str(TEMPLATES_DIR),
        "data_dir": str(DATA_DIR),
        "instance_dir": str(INSTANCE_DIR),
    }
