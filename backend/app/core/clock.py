"""The only source of "now" in the backend, so tests can freeze time (rule 5.15)."""

from datetime import UTC, datetime


def now_utc() -> datetime:
    """Current instant as a naive UTC datetime, the form stored in the database."""
    return datetime.now(UTC).replace(tzinfo=None)
