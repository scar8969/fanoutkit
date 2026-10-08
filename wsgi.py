"""WSGI entry point for message_pusher.

Production:

    gunicorn --bind 0.0.0.0:8000 --workers 4 wsgi:app

Development:

    python wsgi.py

This shim exists so an uninstalled source checkout is importable. Once the
distribution is installed the package factory can be pointed at directly and
this file can be deleted.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from message_pusher.app import get_app  # noqa: E402  (sys.path must be set up first)

app = get_app()


if __name__ == "__main__":  # pragma: no cover - manual entry point
    from message_pusher.config import get_settings

    _settings = get_settings()
    app.run(host=_settings.host, port=_settings.port, debug=_settings.debug)
