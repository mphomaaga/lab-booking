from datetime import UTC, date, datetime

import pytest

from app.core import clock


def test_tz_is_johannesburg():
    assert clock.TZ.key == "Africa/Johannesburg"


def test_local_8am_is_6am_utc():
    # 2026-01-05 is a Monday
    starts = clock.slot_starts_utc(date(2026, 1, 5))
    assert starts[0] == datetime(2026, 1, 5, 6, 0)
    assert all(s.tzinfo is None for s in starts)


def test_weekday_gives_ten_hourly_slots():
    starts = clock.slot_starts_utc(date(2026, 1, 6))
    assert len(starts) == 10
    assert starts[0] == datetime(2026, 1, 6, 6, 0)
    assert starts[-1] == datetime(2026, 1, 6, 15, 0)  # local 17:00
    assert [b - a for a, b in zip(starts, starts[1:])] == [starts[1] - starts[0]] * 9


@pytest.mark.parametrize("d", [date(2026, 1, 3), date(2026, 1, 4)])
def test_weekend_gives_no_slots(d):
    assert clock.is_weekend(d)
    assert clock.slot_starts_utc(d) == []


def test_is_weekend_weekdays():
    assert not any(clock.is_weekend(date(2026, 1, day)) for day in range(5, 10))


def test_today_local_is_next_date_after_22_utc(frozen_now):
    frozen_now.set(datetime(2026, 1, 5, 22, 30))
    assert clock.today_local() == date(2026, 1, 6)


def test_today_local_same_date_before_22_utc(frozen_now):
    frozen_now.set(datetime(2026, 1, 5, 21, 59))
    assert clock.today_local() == date(2026, 1, 5)


def test_local_date_of():
    assert clock.local_date_of(datetime(2026, 1, 5, 21, 59)) == date(2026, 1, 5)
    assert clock.local_date_of(datetime(2026, 1, 5, 22, 0)) == date(2026, 1, 6)


def test_local_day_bounds_utc():
    start, end = clock.local_day_bounds_utc(date(2026, 1, 6))
    assert start == datetime(2026, 1, 5, 22, 0)
    assert end == datetime(2026, 1, 6, 22, 0)
    assert start.tzinfo is None and end.tzinfo is None


def test_booking_window_is_exactly_seven_dates(frozen_now):
    frozen_now.set(datetime(2026, 1, 5, 8, 0))
    first, last = clock.booking_window()
    assert first == date(2026, 1, 5)
    assert last == date(2026, 1, 11)
    assert (last - first).days + 1 == 7


def test_booking_window_uses_local_date(frozen_now):
    frozen_now.set(datetime(2026, 1, 5, 22, 30))
    assert clock.booking_window() == (date(2026, 1, 6), date(2026, 1, 12))


def test_now_utc_is_naive_utc():
    before = datetime.now(UTC).replace(tzinfo=None)
    now = clock.now_utc()
    after = datetime.now(UTC).replace(tzinfo=None)
    assert now.tzinfo is None
    assert before <= now <= after


def test_now_utc_stays_patchable_by_name(monkeypatch):
    """Models and JWT expiry rely on patching ``app.core.clock.now_utc``."""
    from app.models._common import utcnow

    fixed = datetime(2030, 1, 1, 12, 0)
    monkeypatch.setattr(clock, "now_utc", lambda: fixed)
    assert clock.today_local() == date(2030, 1, 1)
    assert utcnow() == fixed
