from datetime import UTC, datetime, timedelta
from typing import Any


def _utcnow() -> datetime:
    """Naive UTC timestamp; the columns this is written into are naive."""
    return datetime.now(UTC).replace(tzinfo=None)


class RetryPolicy:
    def __init__(self, max_attempts: int = 5, backoff_base: float = 2.0, backoff_max: float = 300.0):
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

    def next_delay(self, attempt: int) -> float:
        return min(self.backoff_max, self.backoff_base ** attempt)

    def schedule_retry(self, receipt: Any) -> None:
        receipt.next_retry_at = _utcnow() + timedelta(seconds=self.next_delay(receipt.attempts))

    def process_due(self) -> int:
        from ..models import Receipt, db
        from .dispatch import dispatch_message

        due = Receipt.query.filter(Receipt.status == "retrying",
                                   Receipt.next_retry_at <= _utcnow()).all()
        for r in due:
            r.status = "queued"
        mids = sorted({r.message_id for r in due})
        db.session.commit()
        for mid in mids:
            dispatch_message(mid)
        return len(mids)
