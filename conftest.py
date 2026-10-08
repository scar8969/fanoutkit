"""Pytest bootstrap for the message_pusher test suite.

The distribution uses a src/ layout, so a fresh checkout is not importable
until it is installed. Adding src/ to sys.path here means pytest works straight
from the repository, whether or not the package has been installed.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    """Deterministic settings for the whole session."""
    from message_pusher.config import Settings, reset_settings

    reset_settings()
    return Settings.from_env(
        {
            "APP_ENV": "test",
            "SECRET_KEY": "test-secret-key",
            # INFO, not WARNING: the access-log contract test asserts the
            # structured line is actually emitted, and the root handler
            # honours this level.
            "LOG_LEVEL": "INFO",
            "LOG_JSON": "1",
        }
    )


@pytest.fixture()
def client(settings):
    """Flask test client bound to the factory-built application."""
    from message_pusher.app import create_app

    app = create_app(settings)
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    with app.test_client() as test_client:
        yield test_client
