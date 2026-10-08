from ..models import App, Message, Receipt, db

from flask import Blueprint, jsonify, request
import hashlib, hmac

bp = Blueprint("api", __name__)
_hits = {}

def _app_from_key():
    key = request.headers.get("X-App-Key", "")
    h = hashlib.sha256(key.encode()).hexdigest()
    return App.query.filter_by(key_hash=h).first()

@bp.post("/api/push")
def push():
    app = _app_from_key()
    if not app:
        return jsonify({"error": "unauthorized"}), 401
    d = request.get_json(force=True, silent=True) or {}
    msg = Message(app_id=app.id, title=d.get("title", ""), body=d.get("body", ""))
    db.session.add(msg)
    db.session.flush()
    for ch in d.get("channels") or ["telegram"]:
        db.session.add(Receipt(message_id=msg.id, channel=ch))
    db.session.commit()
    # dispatch (thread)
    from .dispatch import dispatch_message
    dispatch_message(msg.id)
    return jsonify({"message_id": msg.id, "status": "queued"})

@bp.get("/api/status/<int:mid>")
def status(mid):
    msg = Message.query.get_or_404(mid)
    receipts = [{"channel": r.channel, "status": r.status, "attempts": r.attempts,
                 "detail": r.detail, "next_retry_at": r.next_retry_at.isoformat() if r.next_retry_at else ""}
                for r in Receipt.query.filter_by(message_id=mid).all()]
    return jsonify({"id": msg.id, "title": msg.title, "status": msg.status, "receipts": receipts})

@bp.post("/api/messages/<int:mid>/retry")
def retry(mid):
    for r in Receipt.query.filter_by(message_id=mid, status="retrying").all():
        r.status = "queued"
    db.session.commit()
    from .dispatch import dispatch_message
    dispatch_message(mid)
    return jsonify({"status": "queued"})
