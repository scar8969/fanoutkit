"""A2 message-pusher — tests. Run: pytest test_fanoutkit.py"""


class FakeChannel:
    """Stand-in for the channel registry."""

    def __init__(self, ok=True, detail="200 ok"):
        self.ok, self.detail = ok, detail

    def send(self, payload):
        return self.ok, self.detail


def test_telegram_payload_shape():
    from message_pusher.pusher.templates import render

    p = render("telegram", "deploy failed", "build broke")
    assert p["text"] == "deploy failed\nbuild broke"


def test_retry_backoff():
    from message_pusher.pusher.retry import RetryPolicy

    rp = RetryPolicy(max_attempts=5, backoff_base=2.0, backoff_max=300.0)
    assert rp.next_delay(1) == 2.0
    assert rp.next_delay(5) == 32.0


def test_retry_capped():
    from message_pusher.pusher.retry import RetryPolicy

    rp = RetryPolicy(max_attempts=10, backoff_base=2.0, backoff_max=300.0)
    assert rp.next_delay(20) == 300.0


def test_channel_success():
    ch = FakeChannel(True, "200 ok")
    assert ch.send({"text": "x"}) == (True, "200 ok")


def test_channel_failure_retries():
    ch = FakeChannel(False, "429 rate limited")
    ok, detail = ch.send({"text": "x"})
    assert not ok and "429" in detail
