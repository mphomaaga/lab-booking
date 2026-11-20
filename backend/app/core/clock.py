"""The only source of "now" in the backend, so tests can freeze time (rule 5.15).

Storage is naive UTC; users see Africa/Johannesburg. The local-time helpers below
convert between the two. Every helper that needs "now" calls ``now_utc()``, looked up
in this module's globals at call time, so patching ``app.core.clock.now_utc`` freezes
all of them (and the model timestamps and JWT expiry that also use it).
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Africa/Johannesburg")

OPENING_HOUR = 8  # local; first slot starts at 08:00 (rule 5.1)
SLOTS_PER_DAY = 10  # 08:00 ... 17:00, one hour each (rule 5.2)
BOOKING_WINDOW_DAYS = 7  # today plus the next 6 days (rule 5.5)


def now_utc() -> datetime:
    """Current instant as a naive UTC datetime, the form stored in the database."""
    return datetime.now(UTC).replace(tzinfo=None)


def _local_to_utc_naive(local: datetime) -> datetime:
    """Convert an aware local datetime to naive UTC."""
    return local.astimezone(UTC).replace(tzinfo=None)


def local_date_of(utc_naive: datetime) -> date:
    """The Africa/Johannesburg calendar date of a naive UTC instant."""
    return utc_naive.replace(tzinfo=UTC).astimezone(TZ).date()


def today_local() -> date:
    """Today's date in Africa/Johannesburg, from ``now_utc()``."""
    return local_date_of(now_utc())


def local_day_bounds_utc(d: date) -> tuple[datetime, datetime]:
    """Start (inclusive) and end (exclusive) of local date ``d`` as naive UTC."""
    start = datetime.combine(d, time(0, 0), tzinfo=TZ)
    end = datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=TZ)
    return _local_to_utc_naive(start), _local_to_utc_naive(end)


def booking_window() -> tuple[date, date]:
    """First and last bookable local dates: today and today + 6 days (rule 5.5)."""
    today = today_local()
    return today, today + timedelta(days=BOOKING_WINDOW_DAYS - 1)


def is_weekend(d: date) -> bool:
    """True on Saturday and Sunday (labs are closed, rule 5.1)."""
    return d.weekday() >= 5


def slot_starts_utc(d: date) -> list[datetime]:
    """Naive UTC start times of the ten slots on local date ``d`` (rules 5.1, 5.2).

    Local 08:00, 09:00, ..., 17:00; an empty list on Saturday and Sunday.
    """
    if is_weekend(d):
        return []
    return [
        _local_to_utc_naive(datetime.combine(d, time(OPENING_HOUR + i, 0), tzinfo=TZ))
        for i in range(SLOTS_PER_DAY)
    ]
