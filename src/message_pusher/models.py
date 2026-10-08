from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class App(db.Model):
    __tablename__ = "apps"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    key_hash = db.Column(db.String(64), default="")
    channels_json = db.Column(db.Text, default="{}")
    retry_max = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    app_id = db.Column(db.Integer, db.ForeignKey("apps.id"))
    title = db.Column(db.String(256), default="")
    body = db.Column(db.Text, default="")
    status = db.Column(db.String(16), default="queued")  # queued|partial|delivered|failed|cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Receipt(db.Model):
    __tablename__ = "receipts"
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"))
    channel = db.Column(db.String(32), default="")
    status = db.Column(db.String(16), default="queued")  # sent|retrying|failed
    attempts = db.Column(db.Integer, default=0)
    detail = db.Column(db.String(256), default="")
    next_retry_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
