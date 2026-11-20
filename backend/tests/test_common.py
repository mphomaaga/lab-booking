from datetime import date

import pytest

from app.core.errors import ApiError
from app.services.common import active_booking_count, get_active_lab_or_404, is_lab_closed


def test_active_lab_is_returned(session, lab_factory):
    lab = lab_factory()
    assert get_active_lab_or_404(session, lab.id).id == lab.id


def test_missing_lab_is_404(session):
    with pytest.raises(ApiError) as exc:
        get_active_lab_or_404(session, 999)
    assert exc.value.status_code == 404
    assert exc.value.code == "lab_not_found"


def test_inactive_lab_is_404(session, lab_factory):
    lab = lab_factory(is_active=False)
    with pytest.raises(ApiError) as exc:
        get_active_lab_or_404(session, lab.id)
    assert exc.value.status_code == 404
    assert exc.value.code == "lab_not_found"


def test_active_booking_count_ignores_cancelled(session, slot_factory, booking_factory):
    slot = slot_factory()
    assert active_booking_count(session, slot.id) == 0
    booking_factory(slot=slot)
    booking_factory(slot=slot)
    booking_factory(slot=slot, cancelled=True)
    assert active_booking_count(session, slot.id) == 2


def test_active_booking_count_is_per_slot(session, lab_factory, slot_factory, booking_factory):
    lab = lab_factory()
    one = slot_factory(lab=lab)
    two = slot_factory(lab=lab, start_time=one.start_time.replace(hour=9))
    booking_factory(slot=one)
    assert active_booking_count(session, one.id) == 1
    assert active_booking_count(session, two.id) == 0


def test_closure_is_per_lab_and_per_date(session, lab_factory, closure_factory):
    lab_a, lab_b = lab_factory(), lab_factory()
    closure_factory(lab=lab_a, date=date(2026, 1, 6))
    assert is_lab_closed(session, lab_a.id, date(2026, 1, 6))
    assert not is_lab_closed(session, lab_a.id, date(2026, 1, 7))
    assert not is_lab_closed(session, lab_b.id, date(2026, 1, 6))
