from typing import Any

from flask import Flask, render_template, request

from .models import App, Message, Receipt, db
from .pusher.api import bp
from . import paths

paths.ensure_runtime_dirs()

def build_app() -> Flask:
    """Build the application: configuration, database, then routes."""
    app = Flask(__name__,
                template_folder=str(paths.TEMPLATES_DIR),
                instance_path=str(paths.INSTANCE_DIR))
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str(paths.INSTANCE_DIR / "pusher.db")
    db.init_app(app)
    with app.app_context():
        db.create_all()
    app.register_blueprint(bp)

    @app.get("/")
    def index() -> str:
        msgs = Message.query.order_by(Message.id.desc()).limit(20).all()
        apps = App.query.order_by(App.id.asc()).all()
        return render_template("index.html", apps=apps, messages=msgs,
                               counts=_counts(), channels=_channel_names(), cli=_cli_snippet())

    @app.get("/apps")
    def apps_page() -> str:
        return render_template("apps.html", apps=App.query.order_by(App.id.asc()).all(),
                               messages=Message.query.order_by(Message.id.desc()).limit(20).all(),
                               counts=_counts(), channels=_channel_names())

    @app.post("/apps")
    def apps_create() -> str:
        name = (request.form.get("name") or "").strip()
        if name and not App.query.filter_by(name=name).first():
            import hashlib
            raw = (request.form.get("key") or (name + "-key")).strip()
            app_row = App(name=name, key_hash=hashlib.sha256(raw.encode()).hexdigest(),
                          retry_max=int(request.form.get("retry_max") or 5))
            db.session.add(app_row)
            db.session.commit()
        return apps_page()

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"status": "ok", "apps": App.query.count(), "messages": Message.query.count()}

    @app.get("/messages/<int:mid>")
    def message_detail(mid: int) -> str:
        msg = db.get_or_404(Message, mid)
        return render_template("message.html", msg=msg, app_row=db.session.get(App, msg.app_id),
                               receipts=Receipt.query.filter_by(message_id=mid).all())

    @app.post("/messages/<int:mid>/retry")
    def message_retry(mid: int) -> str:
        db.get_or_404(Message, mid)
        for r in Receipt.query.filter_by(message_id=mid, status="retrying").all():
            r.status = "queued"
        db.session.commit()
        from .pusher.dispatch import dispatch_message
        dispatch_message(mid)
        return message_detail(mid)

    def _counts() -> dict[str, int]:
        return {"messages": Message.query.count(), "apps": App.query.count(),
                "queued": Message.query.filter_by(status="queued").count(),
                "delivered": Message.query.filter_by(status="delivered").count(),
                "failed": Message.query.filter_by(status="failed").count()}

    def _channel_names() -> list[str]:
        from .pusher.channels import CHANNELS
        return sorted(CHANNELS)

    def _cli_snippet() -> str:
        return (
            "curl -sS -X POST http://127.0.0.1:8000/api/push \\\n"
            "  -H 'Content-Type: application/json' -H 'X-App-Key: <your-app-key>' \\\n"
            "  -d '{\"title\":\"Deploy finished\",\"body\":\"build 42 is live\","
            "\"channels\":[\"telegram\"]}'"
        )

    return app

app = build_app()
