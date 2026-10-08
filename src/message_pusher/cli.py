"""message-pusher CLI — queue a push, inspect status, retry a message.

The client only needs the standard library, so `python cli.py --help` works
in a bare interpreter with no third-party packages installed. Commands that
touch the database import Flask-SQLAlchemy lazily, inside the handler.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from . import paths

BASE = os.environ.get("PUSHER_URL", "http://127.0.0.1:8000")

def _request(path, payload=None, key=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-App-Key"] = key
    req = urllib.request.Request(BASE + path, data=data, method=method or ("POST" if data else "GET"),
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except urllib.error.URLError as e:
        return 0, json.dumps({"error": "cannot reach %s: %s" % (BASE, e.reason)})

def cmd_push(args):
    status, body = _request("/api/push",
                            {"title": args.title, "body": args.body, "channels": args.channel},
                            key=args.key)
    print("%s %s" % (status, body))
    return 0 if status == 200 else 1

def cmd_status(args):
    status, body = _request("/api/status/%d" % args.message_id)
    if status == 200:
        doc = json.loads(body)
        print("message %s  title=%r  status=%s" % (doc["id"], doc["title"], doc["status"]))
        for r in doc["receipts"]:
            print("  %-9s %-9s attempts=%s  %s" % (r["channel"], r["status"], r["attempts"], r["detail"]))
    else:
        print("%s %s" % (status, body))
    return 0 if status == 200 else 1

def cmd_retry(args):
    status, body = _request("/api/messages/%d/retry" % args.message_id, {}, method="POST")
    print("%s %s" % (status, body))
    return 0 if status == 200 else 1

def cmd_apps(args):
    # Read-only inspection straight off the local SQLite file via the models.
    sys.path.insert(0, str(paths.PROJECT_ROOT))
    from .models import App, Message  # noqa: E402  (needs Flask-SQLAlchemy)
    import os as _os
    root = _os.path.dirname(_os.path.abspath(__file__))
    from flask import Flask
    app = Flask(__name__, instance_path=_str(paths.INSTANCE_DIR))
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + _str(paths.INSTANCE_DIR / "pusher.db")
    from .models import db
    db.init_app(app)
    with app.app_context():
        for a in App.query.order_by(App.id).all():
            print("app   %-3s %-16s max_attempts=%s" % (a.id, a.name, a.retry_max))
        for m in Message.query.order_by(Message.id).all():
            print("msg   %-3s %-9s %s" % (m.id, m.status, (m.title or "")[:48]))
    return 0

def build_parser():
    p = argparse.ArgumentParser(prog="pusher", description="message-pusher CLI")
    p.add_argument("--url", help="base URL of a running instance (default $PUSHER_URL or %s)" % BASE)
    sub = p.add_subparsers(dest="cmd")

    ps = sub.add_parser("push", help="queue a message fan-out")
    ps.add_argument("title")
    ps.add_argument("body")
    ps.add_argument("--app", help="app name, for the record printed by --verbose")
    ps.add_argument("--key", required=True, help="app key sent as X-App-Key")
    ps.add_argument("--channel", action="append", default=None,
                    help="repeatable; defaults to telegram")
    ps.add_argument("--verbose", action="store_true")
    ps.set_defaults(func=cmd_push)

    pt = sub.add_parser("status", help="show a message and its delivery receipts")
    pt.add_argument("message_id", type=int)
    pt.set_defaults(func=cmd_status)

    pr = sub.add_parser("retry", help="re-queue retrying receipts for a message")
    pr.add_argument("message_id", type=int)
    pr.set_defaults(func=cmd_retry)

    pa = sub.add_parser("apps", help="list apps and messages from the local database")
    pa.set_defaults(func=cmd_apps)
    return p

def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)
    global BASE
    if getattr(args, "url", None):
        BASE = args.url
    if not getattr(args, "cmd", None):
        p.print_help()
        return 0
    if args.cmd == "push" and not args.channel:
        args.channel = ["telegram"]
    return args.func(args)
