from typing import Any


def render(channel: str, title: str, body: str) -> dict[str, Any]:
    text = f"{title}\n{body}" if title else body
    return {"title": title, "text": text}
