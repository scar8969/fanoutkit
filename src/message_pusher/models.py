from datetime import UTC, datetime
from typing import Any

from flask_sqlalchemy import SQLAlchemy

# flask_sqlalchemy builds the declarative base lazily inside init_app and stores
# it as an instance attribute, so db.Model is invisible to a static checker and
# every db.Column below would be flagged. Binding it once, to a plainly
# Any-typed alias, keeps the rest of the module checkable; the
# message_pusher.models override in mypy.ini turns off disallow_subclassing_any
# for this module because the base genuinely is dynamic.
db = SQLAlchemy()
Base: Any = db.Model


def _utcnow() -> datetime:
    """Naive UTC timestamp, matching the naive DateTime columns below.

    ``datetime.utcnow()`` is deprecated since 3.12 and raises a
    ``DeprecationWarning`` on every call (verified on the 3.14 interpreter that
    runs this suite), so the default is built from an aware ``now(UTC)`` and
    stripped back to naive.
    """
    return datetime.now(UTC).replace(tzinfo=None)


class App(Base):
    __tablename__ = "apps"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    key_hash = db.Column(db.String(64), default="")
    channels_json = db.Column(db.Text, default="{}")
    retry_max = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=_utcnow)


class Message(Base):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    app_id = db.Column(db.Integer, db.ForeignKey("apps.id"))
    title = db.Column(db.String(256), default="")
    body = db.Column(db.Text, default="")
    status = db.Column(db.String(16), default="queued")  # queued|partial|delivered|failed|cancelled
    created_at = db.Column(db.DateTime, default=_utcnow)


class Receipt(Base):
    __tablename__ = "receipts"
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"))
    channel = db.Column(db.String(32), default="")
    status = db.Column(db.String(16), default="queued")  # sent|retrying|failed
    attempts = db.Column(db.Integer, default=0)
    detail = db.Column(db.String(256), default="")
    next_retry_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=_utcnow)
