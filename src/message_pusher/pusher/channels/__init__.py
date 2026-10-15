"""Channel registry: every channel class registers itself here by name."""
from __future__ import annotations

import json
import smtplib
import urllib.error
import urllib.request
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

CHANNELS: dict[str, type["_Base"]] = {}


def register(name: str) -> Callable[[type[_Base]], type[_Base]]:
    def deco(cls: type[_Base]) -> type[_Base]:
        CHANNELS[name] = cls
        return cls
    return deco


class _Base:
    def send(self, payload: dict[str, Any]) -> tuple[bool, str]:
        raise NotImplementedError

    def _post(self, url: str, payload: dict[str, Any],
              headers: dict[str, str] | None = None) -> tuple[bool, str]:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", **(headers or {})})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200, f"{r.status} {r.read()[:80]}"


@register("telegram")
class TelegramChannel(_Base):
    def send(self, payload: dict[str, Any]) -> tuple[bool, str]:
        cfg = payload["config"]
        return self._post(f"https://api.telegram.org/bot{cfg['token']}/sendMessage",
                          {"chat_id": cfg["chat_id"], "text": payload["text"]})


@register("discord")
class DiscordChannel(_Base):
    def send(self, payload: dict[str, Any]) -> tuple[bool, str]:
        return self._post(payload["config"]["webhook"],
                          {"content": payload["text"]})


@register("slack")
class SlackChannel(_Base):
    def send(self, payload: dict[str, Any]) -> tuple[bool, str]:
        return self._post(payload["config"]["webhook"],
                          {"blocks": [{"type": "section",
                                       "text": {"type": "mrkdwn", "text": payload["text"]}}]})


@register("email")
class EmailChannel(_Base):
    def send(self, payload: dict[str, Any]) -> tuple[bool, str]:
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
    def send(self, payload: dict[str, Any]) -> tuple[bool, str]:
        return self._post(payload["config"]["url"], {"text": payload["text"]},
                          payload["config"].get("headers", {}))


@register("ntfy")
class NtfyChannel(_Base):
    def send(self, payload: dict[str, Any]) -> tuple[bool, str]:
        cfg = payload["config"]
        req = urllib.request.Request(f"https://ntfy.sh/{cfg['topic']}",
                                     data=payload["text"].encode(),
                                     headers={"Title": payload["title"],
                                              "Authorization": f"Bearer {cfg.get('token', '')}"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200, str(r.status)


__all__ = ["CHANNELS", "register", "TelegramChannel", "DiscordChannel", "SlackChannel",
           "EmailChannel", "WebhookChannel", "NtfyChannel"]
