"""Structured logging and request correlation for message_pusher.

One JSON object per line on stdout is what Docker, journald and every log
shipper prefer. configure_logging() is idempotent and is called by the WSGI
entry point, the CLI and the test bootstrap.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time
import uuid
from typing import Any

from . import __version__

__all__ = [
    "configure_logging",
    "get_logger",
    "log_event",
    "new_request_id",
    "request_id",
    "set_request_id",
]

_REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_CONFIGURED = False

_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str | None) -> str:
    token = value or new_request_id()
    _REQUEST_ID.set(token)
    return token


def request_id() -> str:
    return _REQUEST_ID.get()


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + ".%03dZ" % int(record.msecs),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id(),
            "service": "message_pusher",
            "version": __version__,
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = (
            time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f" level={record.levelname.lower()} logger={record.name}"
            + f" request_id={request_id()} msg={record.getMessage()!r}"
        )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


class _StdoutHandler(logging.StreamHandler[Any]):
    """Write to whatever sys.stdout is *now*.

    A handler that binds the stream it saw at construction keeps writing
    past a later replacement -- pytest swaps sys.stdout per test, and the
    capture fixture would then see nothing while the line still reached the
    file descriptor.
    """

    def __init__(self) -> None:
        super().__init__(sys.stdout)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            stream = sys.stdout
            stream.write(self.format(record) + self.terminator)
            self.flush()
        except Exception:  # pragma: no cover - mirrors logging internals
            self.handleError(record)

    def flush(self) -> None:
        stream = sys.stdout
        if hasattr(stream, "flush"):
            stream.flush()


def configure_logging(level: str = "INFO", *, json_output: bool | None = None) -> None:
    """Install the root handler. Calling it again replaces the handler."""
    global _CONFIGURED
    if json_output is None:
        json_output = (os.environ.get("LOG_JSON", "1") or "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }

    handler = _StdoutHandler()
    handler.setFormatter(_JsonFormatter() if json_output else _TextFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # The development server already logs every request; the access log below
    # carries the correlation id instead.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, /, **fields: Any) -> None:
    """Emit one structured event. The event name becomes the message field."""
    logger.info(event, extra={"event": event, **fields})
