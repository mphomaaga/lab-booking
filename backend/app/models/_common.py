from datetime import UTC, datetime


def utcnow() -> datetime:
    """Naive UTC now, the storage convention for every datetime column (rule 5.15)."""
    return datetime.now(UTC).replace(tzinfo=None)
