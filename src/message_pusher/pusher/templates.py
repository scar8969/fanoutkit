def render(channel: str, title: str, body: str) -> dict:
    text = f"{title}\n{body}" if title else body
    return {"title": title, "text": text}
