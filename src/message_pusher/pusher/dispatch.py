import datetime
import json

def dispatch_message(mid: int) -> None:
    from ..models import App, Message, Receipt, db
    from .channels import CHANNELS
    from .retry import RetryPolicy
    from .templates import render

    msg = Message.query.get(mid)
    if msg is None:
        return
    app = App.query.get(msg.app_id)
    channels = json.loads((app.channels_json if app else None) or "{}")
    policy = RetryPolicy(app.retry_max if app and app.retry_max else 5)
    for r in Receipt.query.filter_by(message_id=mid).all():
        if r.status != "queued":
            continue
        ch = CHANNELS.get(r.channel)
        if not ch:
            r.status, r.detail = "failed", "unknown channel"
            continue
        payload = render(r.channel, msg.title, msg.body)
        payload["config"] = channels.get(r.channel, {})
        r.attempts += 1
        try:
            ok, detail = ch().send(payload)
        except Exception as e:
            ok, detail = False, str(e)[:80]
        if ok:
            r.status, r.detail = "sent", detail
        elif r.attempts >= policy.max_attempts:
            r.status, r.detail = "failed", detail
        else:
            r.status, r.detail = "retrying", detail
            policy.schedule_retry(r)
        r.updated_at = datetime.datetime.utcnow()
    statuses = {r.status for r in Receipt.query.filter_by(message_id=mid).all()}
    if not statuses or statuses <= {"sent"}:
        msg.status = "delivered"
    elif "sent" in statuses:
        msg.status = "partial"
    elif statuses & {"queued", "retrying"}:
        msg.status = "queued"
    else:
        msg.status = "failed"
    db.session.commit()
