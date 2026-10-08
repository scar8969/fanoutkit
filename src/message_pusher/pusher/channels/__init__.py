"""Channel registry: every channel class registers itself here by name."""
import json
import smtplib
import urllib.request
import urllib.error
from email.message import EmailMessage

CHANNELS = {}

def register(name):
    def deco(cls):
        CHANNELS[name] = cls
        return cls
    return deco

class _Base:
    def _post(self, url, payload, headers=None):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", **(headers or {})})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200, f"{r.status} {r.read()[:80]}"

@register("telegram")
class TelegramChannel(_Base):
    def send(self, payload):
        cfg = payload["config"]
        return self._post(f"https://api.telegram.org/bot{cfg['token']}/sendMessage",
                          {"chat_id": cfg["chat_id"], "text": payload["text"]})

@register("discord")
class DiscordChannel(_Base):
    def send(self, payload):
        return self._post(payload["config"]["webhook"],
                          {"content": payload["text"]})

@register("slack")
class SlackChannel(_Base):
    def send(self, payload):
        return self._post(payload["config"]["webhook"],
                          {"blocks": [{"type": "section",
                                       "text": {"type": "mrkdwn", "text": payload["text"]}}]})

@register("email")
class EmailChannel(_Base):
    def send(self, payload):
        cfg = payload["config"]
        msg = EmailMessage()
        msg["Subject"] = payload["title"]
        msg["From"] = cfg["from"]
        msg["To"] = cfg["to"]
        msg.set_content(payload["text"])
        try:
            with smtplib.SMTP(cfg["host"], int(cfg.get("port", 587)), timeout=10) as s:
                s.starttls()
                if cfg.get("user"):
                    s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
            return True, "250 queued"
        except Exception as e:
            return False, str(e)[:80]

@register("webhook")
class WebhookChannel(_Base):
    def send(self, payload):
        return self._post(payload["config"]["url"], {"text": payload["text"]},
                          payload["config"].get("headers", {}))

@register("ntfy")
class NtfyChannel(_Base):
    def send(self, payload):
        cfg = payload["config"]
        req = urllib.request.Request(f"https://ntfy.sh/{cfg['topic']}",
                                     data=payload["text"].encode(),
                                     headers={"Title": payload["title"],
                                              "Authorization": f"Bearer {cfg.get('token', '')}"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200, str(r.status)

__all__ = ["CHANNELS", "register", "TelegramChannel", "DiscordChannel", "SlackChannel",
           "EmailChannel", "WebhookChannel", "NtfyChannel"]
