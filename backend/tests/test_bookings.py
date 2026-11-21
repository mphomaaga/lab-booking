"""Bookings: create, cancel and list (US-3, US-4, US-5; rules 5.4 to 5.10, 5.12, 5.13).

The frozen clock starts at 2026-01-05 08:00 UTC (a Monday, 10:00 in Johannesburg), so
the booking window is Monday 5 January to Sunday 11 January. `at(day, hour)` builds a
naive UTC start time on 2026-01-<day>.
"""

from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Booking, Lab, Slot, User
from app.services.common import active_booking_count

NOW = datetime(2026, 1, 5, 8, 0)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, day, hour, minute)


@pytest.fixture(autouse=True)
def _frozen(frozen_now):
    """Freeze the clock for every test in this module."""
    return frozen_now


@pytest.fixture
def alice(user_factory) -> User:
    return user_factory()


@pytest.fixture
def lab(lab_factory) -> Lab:
    return lab_factory()


def book(client, auth_headers, user: User, slot_id):
    return client.post("/bookings", json={"slot_id": slot_id}, headers=auth_headers(user))


def cancel(client, auth_headers, user: User, booking_id):
    return client.delete(f"/bookings/{booking_id}", headers=auth_headers(user))


def error_code(response) -> str:
    return response.json()["error"]["code"]


def count_bookings(session) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(Booking))


# --- POST /bookings: success -------------------------------------------------


def test_create_returns_201_booking(client, auth_headers, alice, lab, slot_factory, session):
    slot = slot_factory(lab=lab, start_time=at(5, 10))
    response = book(client, auth_headers, alice, slot.id)
    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "status": "active",
        "created_at": "2026-01-05T08:00:00Z",
        "cancelled_at": None,
        "cancellable": True,
        "lab": {"id": lab.id, "name": lab.name},
        "slot": {
            "id": slot.id,
            "start_time": "2026-01-05T10:00:00Z",
            "end_time": "2026-01-05T11:00:00Z",
        },
    }
    row = session.get(Booking, body["id"])
    assert row.user_id == alice.id and row.slot_id == slot.id and row.cancelled_at is None


def test_admin_can_book(client, auth_headers, admin_factory, lab, slot_factory):
    admin = admin_factory()
    slot = slot_factory(lab=lab, start_time=at(5, 10))
    assert book(client, auth_headers, admin, slot.id).status_code == 201


def test_booking_raises_active_count_by_one_immediately(
    client, auth_headers, alice, lab, slot_factory, session
):
    slot = slot_factory(lab=lab, start_time=at(5, 10))
    assert active_booking_count(session, slot.id) == 0
    book(client, auth_headers, alice, slot.id)
    assert active_booking_count(session, slot.id) == 1


def test_can_book_one_second_before_start(client, auth_headers, alice, lab, slot_factory):
    slot = slot_factory(lab=lab, start_time=NOW + timedelta(seconds=1))
    assert book(client, auth_headers, alice, slot.id).status_code == 201


# --- authentication and validation -------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/bookings"), ("delete", "/bookings/1"), ("get", "/me/bookings")],
)
def test_requires_token(client, method, path):
    kwargs = {"json": {"slot_id": 1}} if method == "post" else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 401
    assert error_code(response) == "not_authenticated"


@pytest.mark.parametrize(
    "body",
    [{}, {"slot_id": "abc"}, {"slot_id": None}, {"slot_id": 1, "user_id": 2}],
)
def test_create_malformed_body_is_validation_error(client, auth_headers, alice, body):
    response = client.post("/bookings", json=body, headers=auth_headers(alice))
    assert response.status_code == 422
    assert error_code(response) == "validation_error"


def test_create_without_json_body_is_validation_error(client, auth_headers, alice):
    response = client.post("/bookings", headers=auth_headers(alice))
    assert response.status_code == 422
    assert error_code(response) == "validation_error"


def test_cancel_malformed_path_is_validation_error(client, auth_headers, alice):
    response = client.delete("/bookings/abc", headers=auth_headers(alice))
    assert response.status_code == 422
    assert error_code(response) == "validation_error"


# --- POST /bookings: one test per error code ---------------------------------


def test_slot_not_found(client, auth_headers, alice):
    response = book(client, auth_headers, alice, 9999)
    assert response.status_code == 404
    assert error_code(response) == "slot_not_found"


def test_slot_in_inactive_lab_is_not_found(client, auth_headers, alice, lab_factory, slot_factory):
    slot = slot_factory(lab=lab_factory(is_active=False), start_time=at(5, 10))
    response = book(client, auth_headers, alice, slot.id)
    assert response.status_code == 404
    assert error_code(response) == "slot_not_found"


def test_slot_in_past_exactly_at_start(client, auth_headers, alice, lab, slot_factory):
    slot = slot_factory(lab=lab, start_time=NOW)
    response = book(client, auth_headers, alice, slot.id)
    assert response.status_code == 422
    assert error_code(response) == "slot_in_past"


def test_slot_in_past_during_slot(client, auth_headers, alice, lab, slot_factory):
    slot = slot_factory(lab=lab, start_time=NOW - timedelta(minutes=30))
    response = book(client, auth_headers, alice, slot.id)
    assert response.status_code == 422
    assert error_code(response) == "slot_in_past"


def test_slot_in_past_earlier_day(client, auth_headers, alice, lab, slot_factory):
    slot = slot_factory(lab=lab, start_time=NOW - timedelta(days=2))
    assert error_code(book(client, auth_headers, alice, slot.id)) == "slot_in_past"


def test_outside_booking_window_after_last_day(client, auth_headers, alice, lab, slot_factory):
    slot = slot_factory(lab=lab, start_time=at(12, 8))  # today + 7 days
    response = book(client, auth_headers, alice, slot.id)
    assert response.status_code == 422
    assert error_code(response) == "outside_booking_window"


def test_last_day_of_window_is_bookable(client, auth_headers, alice, lab, slot_factory):
    slot = slot_factory(lab=lab, start_time=at(11, 8))  # today + 6 days (a Sunday)
    assert book(client, auth_headers, alice, slot.id).status_code == 201


def test_window_uses_johannesburg_date(client, auth_headers, alice, lab, slot_factory):
    # 22:30 UTC on 11 Jan is 00:30 on 12 Jan in Johannesburg: outside the window.
    slot = slot_factory(lab=lab, start_time=at(11, 22, 30))
    assert error_code(book(client, auth_headers, alice, slot.id)) == "outside_booking_window"


def test_lab_closed(client, auth_headers, alice, lab, slot_factory, closure_factory):
    closure_factory(lab=lab, date=at(6, 0).date())
    slot = slot_factory(lab=lab, start_time=at(6, 8))
    response = book(client, auth_headers, alice, slot.id)
    assert response.status_code == 409
    assert error_code(response) == "lab_closed"


def test_closure_applies_to_that_lab_and_date_only(
    client, auth_headers, alice, lab_factory, slot_factory, closure_factory
):
    closed_lab, other_lab = lab_factory(), lab_factory()
    closure_factory(lab=closed_lab, date=at(6, 0).date())
    other_lab_slot = slot_factory(lab=other_lab, start_time=at(6, 8))
    other_day_slot = slot_factory(lab=closed_lab, start_time=at(7, 8))
    assert book(client, auth_headers, alice, other_lab_slot.id).status_code == 201
    assert book(client, auth_headers, alice, other_day_slot.id).status_code == 201


def test_lab_closed_uses_johannesburg_date(
    client, auth_headers, alice, lab, slot_factory, closure_factory
):
    # 22:30 UTC on 6 Jan is 00:30 on 7 Jan locally, so the 7 Jan closure applies.
    closure_factory(lab=lab, date=at(7, 0).date())
    slot = slot_factory(lab=lab, start_time=at(6, 22, 30))
    assert error_code(book(client, auth_headers, alice, slot.id)) == "lab_closed"


def test_already_booked(client, auth_headers, alice, lab, slot_factory, booking_factory):
    slot = slot_factory(lab=lab, start_time=at(5, 10))
    booking_factory(user=alice, slot=slot)
    response = book(client, auth_headers, alice, slot.id)
    assert response.status_code == 409
    assert error_code(response) == "already_booked"


def test_rebook_after_cancel_is_allowed(client, auth_headers, alice, lab, slot_factory, session):
    slot = slot_factory(lab=lab, start_time=at(5, 10))
    first = book(client, auth_headers, alice, slot.id).json()
    assert cancel(client, auth_headers, alice, first["id"]).status_code == 200
    second = book(client, auth_headers, alice, slot.id)
    assert second.status_code == 201
    assert second.json()["id"] != first["id"]
    # Both rows exist: one cancelled, one active; only the active one holds a seat.
    assert count_bookings(session) == 2
    assert active_booking_count(session, slot.id) == 1


def test_overlapping_booking_in_another_lab(
    client, auth_headers, alice, lab_factory, slot_factory, booking_factory
):
    lab_a, lab_b = lab_factory(), lab_factory()
    booking_factory(user=alice, slot=slot_factory(lab=lab_a, start_time=at(5, 10)))
    other = slot_factory(lab=lab_b, start_time=at(5, 10))
    response = book(client, auth_headers, alice, other.id)
    assert response.status_code == 409
    assert error_code(response) == "overlapping_booking"


def test_cancelled_booking_does_not_overlap(
    client, auth_headers, alice, lab_factory, slot_factory, booking_factory
):
    lab_a, lab_b = lab_factory(), lab_factory()
    booking_factory(user=alice, slot=slot_factory(lab=lab_a, start_time=at(5, 10)), cancelled=True)
    other = slot_factory(lab=lab_b, start_time=at(5, 10))
    assert book(client, auth_headers, alice, other.id).status_code == 201


def test_different_start_time_does_not_overlap(
    client, auth_headers, alice, lab_factory, slot_factory, booking_factory
):
    lab_a, lab_b = lab_factory(), lab_factory()
    booking_factory(user=alice, slot=slot_factory(lab=lab_a, start_time=at(5, 10)))
    other = slot_factory(lab=lab_b, start_time=at(5, 11))
    assert book(client, auth_headers, alice, other.id).status_code == 201


def test_other_users_booking_does_not_overlap(
    client, auth_headers, alice, user_factory, lab_factory, slot_factory, booking_factory
):
    lab_a, lab_b = lab_factory(), lab_factory()
    booking_factory(user=user_factory(), slot=slot_factory(lab=lab_a, start_time=at(5, 10)))
    other = slot_factory(lab=lab_b, start_time=at(5, 10))
    assert book(client, auth_headers, alice, other.id).status_code == 201


def _two_bookings_on_day(alice, lab, slot_factory, booking_factory, day=6, **kwargs):
    for hour in (8, 9):
        booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(day, hour)), **kwargs)


def test_daily_limit_reached_on_third_booking(
    client, auth_headers, alice, lab, slot_factory, booking_factory
):
    _two_bookings_on_day(alice, lab, slot_factory, booking_factory)
    third = slot_factory(lab=lab, start_time=at(6, 10))
    response = book(client, auth_headers, alice, third.id)
    assert response.status_code == 409
    assert error_code(response) == "daily_limit_reached"


def test_two_bookings_are_allowed(client, auth_headers, alice, lab, slot_factory):
    for hour in (8, 9):
        slot = slot_factory(lab=lab, start_time=at(6, hour))
        assert book(client, auth_headers, alice, slot.id).status_code == 201


def test_daily_limit_counts_all_labs(
    client, auth_headers, alice, lab_factory, slot_factory, booking_factory
):
    booking_factory(user=alice, slot=slot_factory(lab=lab_factory(), start_time=at(6, 8)))
    booking_factory(user=alice, slot=slot_factory(lab=lab_factory(), start_time=at(6, 9)))
    third = slot_factory(lab=lab_factory(), start_time=at(6, 10))
    assert error_code(book(client, auth_headers, alice, third.id)) == "daily_limit_reached"


def test_cancelled_bookings_do_not_count_towards_daily_limit(
    client, auth_headers, alice, lab, slot_factory, booking_factory
):
    _two_bookings_on_day(alice, lab, slot_factory, booking_factory, cancelled=True)
    third = slot_factory(lab=lab, start_time=at(6, 10))
    assert book(client, auth_headers, alice, third.id).status_code == 201


def test_one_cancelled_frees_a_daily_limit_place(
    client, auth_headers, alice, lab, slot_factory, booking_factory
):
    first = booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(6, 8)))
    booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(6, 9)))
    third = slot_factory(lab=lab, start_time=at(6, 10))
    assert error_code(book(client, auth_headers, alice, third.id)) == "daily_limit_reached"
    assert cancel(client, auth_headers, alice, first.id).status_code == 200
    assert book(client, auth_headers, alice, third.id).status_code == 201


def test_daily_limit_counts_bookings_that_already_started(
    client, auth_headers, alice, lab, slot_factory, booking_factory, frozen_now
):
    # Today is 5 Jan. Both bookings are at or before the current time (08:00 UTC).
    booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(5, 6)))
    booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(5, 7)))
    third = slot_factory(lab=lab, start_time=at(5, 12))
    assert error_code(book(client, auth_headers, alice, third.id)) == "daily_limit_reached"


def test_daily_limit_is_per_johannesburg_date(
    client, auth_headers, alice, lab, slot_factory, booking_factory
):
    # 22:30 UTC on 6 Jan is 00:30 on 7 Jan locally: a different day from 08:00 and 09:00 UTC.
    booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(6, 8)))
    booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(6, 9)))
    next_day = slot_factory(lab=lab, start_time=at(6, 22, 30))
    assert book(client, auth_headers, alice, next_day.id).status_code == 201
    # ...and 21:30 UTC on 6 Jan (23:30 locally) is still the 6th.
    same_day = slot_factory(lab=lab, start_time=at(6, 21, 30))
    assert error_code(book(client, auth_headers, alice, same_day.id)) == "daily_limit_reached"


def test_daily_limit_ignores_other_days_and_users(
    client, auth_headers, alice, user_factory, lab, slot_factory, booking_factory
):
    booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(7, 8)))
    booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(7, 9)))
    bob = user_factory()
    booking_factory(user=bob, slot=slot_factory(lab=lab, start_time=at(6, 8)))
    booking_factory(user=bob, slot=slot_factory(lab=lab, start_time=at(6, 9)))
    slot = slot_factory(lab=lab, start_time=at(6, 10))
    assert book(client, auth_headers, alice, slot.id).status_code == 201


def test_slot_full(client, auth_headers, alice, user_factory, lab_factory, slot_factory, booking_factory):
    small_lab = lab_factory(seats=2)
    slot = slot_factory(lab=small_lab, start_time=at(5, 10))
    booking_factory(user=user_factory(), slot=slot)
    booking_factory(user=user_factory(), slot=slot)
    response = book(client, auth_headers, alice, slot.id)
    assert response.status_code == 409
    assert error_code(response) == "slot_full"


def test_cancelled_bookings_do_not_use_seats(
    client, auth_headers, alice, user_factory, lab_factory, slot_factory, booking_factory
):
    slot = slot_factory(lab=lab_factory(seats=2), start_time=at(5, 10))
    booking_factory(user=user_factory(), slot=slot)
    booking_factory(user=user_factory(), slot=slot, cancelled=True)
    assert book(client, auth_headers, alice, slot.id).status_code == 201


def test_last_seat_can_be_booked_then_slot_is_full(
    client, auth_headers, alice, user_factory, lab_factory, slot_factory, booking_factory
):
    slot = slot_factory(lab=lab_factory(seats=2), start_time=at(5, 10))
    booking_factory(user=user_factory(), slot=slot)
    assert book(client, auth_headers, alice, slot.id).status_code == 201
    assert error_code(book(client, auth_headers, user_factory(), slot.id)) == "slot_full"


def test_cancelling_frees_the_seat_for_someone_else(
    client, auth_headers, alice, user_factory, lab_factory, slot_factory, session
):
    slot = slot_factory(lab=lab_factory(seats=1), start_time=at(5, 10))
    bob = user_factory()
    booking = book(client, auth_headers, bob, slot.id).json()
    assert error_code(book(client, auth_headers, alice, slot.id)) == "slot_full"
    cancel(client, auth_headers, bob, booking["id"])
    assert book(client, auth_headers, alice, slot.id).status_code == 201


# --- check order: when two checks fail, the earlier one decides --------------


def test_order_not_found_before_past(client, auth_headers, alice, lab_factory, slot_factory):
    slot = slot_factory(lab=lab_factory(is_active=False), start_time=NOW - timedelta(hours=1))
    assert error_code(book(client, auth_headers, alice, slot.id)) == "slot_not_found"


def test_order_past_before_window(client, auth_headers, alice, lab, slot_factory):
    # A slot two weeks ago is both in the past and outside the window.
    slot = slot_factory(lab=lab, start_time=NOW - timedelta(days=14))
    assert error_code(book(client, auth_headers, alice, slot.id)) == "slot_in_past"


def test_order_past_before_closed(client, auth_headers, alice, lab, slot_factory, closure_factory):
    closure_factory(lab=lab, date=NOW.date())
    slot = slot_factory(lab=lab, start_time=NOW - timedelta(hours=1))
    assert error_code(book(client, auth_headers, alice, slot.id)) == "slot_in_past"


def test_order_window_before_closed(client, auth_headers, alice, lab, slot_factory, closure_factory):
    closure_factory(lab=lab, date=at(14, 0).date())
    slot = slot_factory(lab=lab, start_time=at(14, 8))
    assert error_code(book(client, auth_headers, alice, slot.id)) == "outside_booking_window"


def test_order_closed_before_already_booked(
    client, auth_headers, alice, lab, slot_factory, booking_factory, closure_factory
):
    slot = slot_factory(lab=lab, start_time=at(6, 8))
    booking_factory(user=alice, slot=slot)
    closure_factory(lab=lab, date=at(6, 0).date())
    assert error_code(book(client, auth_headers, alice, slot.id)) == "lab_closed"


def test_order_already_booked_before_daily_limit(
    client, auth_headers, alice, lab, slot_factory, booking_factory
):
    # Two active bookings that day, one of them in this very slot: both checks fail.
    slot = slot_factory(lab=lab, start_time=at(6, 8))
    booking_factory(user=alice, slot=slot)
    booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(6, 9)))
    assert error_code(book(client, auth_headers, alice, slot.id)) == "already_booked"


def test_order_overlapping_before_daily_limit(
    client, auth_headers, alice, lab_factory, slot_factory, booking_factory
):
    lab_a, lab_b = lab_factory(), lab_factory()
    booking_factory(user=alice, slot=slot_factory(lab=lab_a, start_time=at(6, 8)))
    booking_factory(user=alice, slot=slot_factory(lab=lab_a, start_time=at(6, 9)))
    clash = slot_factory(lab=lab_b, start_time=at(6, 8))
    assert error_code(book(client, auth_headers, alice, clash.id)) == "overlapping_booking"


def test_order_daily_limit_before_full(
    client, auth_headers, alice, user_factory, lab_factory, slot_factory, booking_factory
):
    small_lab = lab_factory(seats=1)
    booking_factory(user=alice, slot=slot_factory(lab=small_lab, start_time=at(6, 8)))
    booking_factory(user=alice, slot=slot_factory(lab=small_lab, start_time=at(6, 9)))
    full = slot_factory(lab=small_lab, start_time=at(6, 10))
    booking_factory(user=user_factory(), slot=full)
    assert error_code(book(client, auth_headers, alice, full.id)) == "daily_limit_reached"


def test_order_already_booked_before_full(
    client, auth_headers, alice, user_factory, lab_factory, slot_factory, booking_factory
):
    slot = slot_factory(lab=lab_factory(seats=1), start_time=at(6, 8))
    booking_factory(user=alice, slot=slot)  # the only seat is alice's own
    assert error_code(book(client, auth_headers, alice, slot.id)) == "already_booked"


def test_failed_checks_write_nothing(
    client, auth_headers, alice, lab, slot_factory, booking_factory, session
):
    _two_bookings_on_day(alice, lab, slot_factory, booking_factory)
    before = count_bookings(session)
    third = slot_factory(lab=lab, start_time=at(6, 10))
    assert book(client, auth_headers, alice, third.id).status_code == 409
    assert count_bookings(session) == before == 2


# --- DELETE /bookings/{booking_id} --------------------------------------------


def test_cancel_success(client, auth_headers, alice, lab, slot_factory, booking_factory, session):
    slot = slot_factory(lab=lab, start_time=at(5, 10))
    booking = booking_factory(user=alice, slot=slot)
    assert active_booking_count(session, slot.id) == 1
    response = cancel(client, auth_headers, alice, booking.id)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == booking.id
    assert body["status"] == "cancelled"
    assert body["cancelled_at"] == "2026-01-05T08:00:00Z"
    assert body["cancellable"] is False
    assert body["lab"] == {"id": lab.id, "name": lab.name}
    assert body["slot"]["id"] == slot.id
    # The row is kept, with cancelled_at set, and the seat is free at once.
    session.expire_all()
    row = session.get(Booking, booking.id)
    assert row is not None and row.cancelled_at == NOW
    assert active_booking_count(session, slot.id) == 0


def test_cancel_one_second_before_start(client, auth_headers, alice, lab, slot_factory, booking_factory):
    booking = booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=NOW + timedelta(seconds=1)))
    assert cancel(client, auth_headers, alice, booking.id).status_code == 200


def test_cancel_not_found(client, auth_headers, alice):
    response = cancel(client, auth_headers, alice, 9999)
    assert response.status_code == 404
    assert error_code(response) == "booking_not_found"


def test_cancel_someone_elses_booking(
    client, auth_headers, alice, user_factory, lab, slot_factory, booking_factory, session
):
    booking = booking_factory(user=user_factory(), slot=slot_factory(lab=lab, start_time=at(5, 10)))
    response = cancel(client, auth_headers, alice, booking.id)
    assert response.status_code == 403
    assert error_code(response) == "not_your_booking"
    session.expire_all()
    assert session.get(Booking, booking.id).cancelled_at is None


def test_admin_cannot_cancel_someone_elses_booking(
    client, auth_headers, admin_factory, alice, lab, slot_factory, booking_factory
):
    booking = booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(5, 10)))
    response = cancel(client, auth_headers, admin_factory(), booking.id)
    assert response.status_code == 403
    assert error_code(response) == "not_your_booking"


def test_admin_can_cancel_own_booking(
    client, auth_headers, admin_factory, lab, slot_factory, booking_factory
):
    admin = admin_factory()
    booking = booking_factory(user=admin, slot=slot_factory(lab=lab, start_time=at(5, 10)))
    assert cancel(client, auth_headers, admin, booking.id).status_code == 200


def test_cancel_already_cancelled(client, auth_headers, alice, lab, slot_factory, booking_factory):
    booking = booking_factory(
        user=alice, slot=slot_factory(lab=lab, start_time=at(5, 10)), cancelled=True
    )
    response = cancel(client, auth_headers, alice, booking.id)
    assert response.status_code == 409
    assert error_code(response) == "booking_already_cancelled"


def test_cancel_twice(client, auth_headers, alice, lab, slot_factory, booking_factory):
    booking = booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(5, 10)))
    assert cancel(client, auth_headers, alice, booking.id).status_code == 200
    assert error_code(cancel(client, auth_headers, alice, booking.id)) == "booking_already_cancelled"


def test_cancel_already_started_exactly_at_start(
    client, auth_headers, alice, lab, slot_factory, booking_factory, session
):
    booking = booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=NOW))
    response = cancel(client, auth_headers, alice, booking.id)
    assert response.status_code == 409
    assert error_code(response) == "booking_already_started"
    session.expire_all()
    assert session.get(Booking, booking.id).cancelled_at is None


def test_cancel_during_slot(client, auth_headers, alice, lab, slot_factory, booking_factory):
    slot = slot_factory(lab=lab, start_time=NOW - timedelta(minutes=30))
    booking = booking_factory(user=alice, slot=slot)
    assert error_code(cancel(client, auth_headers, alice, booking.id)) == "booking_already_started"


def test_cancel_order_not_found_before_ownership(client, auth_headers, admin_factory):
    assert error_code(cancel(client, auth_headers, admin_factory(), 9999)) == "booking_not_found"


def test_cancel_order_ownership_before_cancelled(
    client, auth_headers, alice, user_factory, lab, slot_factory, booking_factory
):
    booking = booking_factory(
        user=user_factory(), slot=slot_factory(lab=lab, start_time=at(5, 10)), cancelled=True
    )
    assert error_code(cancel(client, auth_headers, alice, booking.id)) == "not_your_booking"


def test_cancel_order_cancelled_before_started(
    client, auth_headers, alice, lab, slot_factory, booking_factory
):
    booking = booking_factory(
        user=alice, slot=slot_factory(lab=lab, start_time=NOW - timedelta(hours=1)), cancelled=True
    )
    assert error_code(cancel(client, auth_headers, alice, booking.id)) == "booking_already_cancelled"


def test_cancel_order_ownership_before_started(
    client, auth_headers, alice, user_factory, lab, slot_factory, booking_factory
):
    booking = booking_factory(user=user_factory(), slot=slot_factory(lab=lab, start_time=NOW))
    assert error_code(cancel(client, auth_headers, alice, booking.id)) == "not_your_booking"


# --- GET /me/bookings ----------------------------------------------------------


def test_my_bookings_empty(client, auth_headers, alice):
    response = client.get("/me/bookings", headers=auth_headers(alice))
    assert response.status_code == 200
    assert response.json() == []


def test_my_bookings_only_own(
    client, auth_headers, alice, user_factory, lab, slot_factory, booking_factory
):
    mine = booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(5, 10)))
    booking_factory(user=user_factory(), slot=slot_factory(lab=lab, start_time=at(5, 11)))
    body = client.get("/me/bookings", headers=auth_headers(alice)).json()
    assert [b["id"] for b in body] == [mine.id]


def test_my_bookings_leave_out_ended_slots(
    client, auth_headers, alice, lab, slot_factory, booking_factory
):
    # Ended exactly now (end_time == now) is out; ended earlier is out.
    booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=NOW - timedelta(hours=1)))
    booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=NOW - timedelta(days=1)))
    still_running = booking_factory(
        user=alice, slot=slot_factory(lab=lab, start_time=NOW - timedelta(minutes=59))
    )
    body = client.get("/me/bookings", headers=auth_headers(alice)).json()
    assert [b["id"] for b in body] == [still_running.id]
    # A booking in progress can no longer be cancelled.
    assert body[0]["cancellable"] is False
    assert body[0]["status"] == "active"


def test_my_bookings_include_cancelled_and_order_by_start_then_created(
    client, auth_headers, alice, lab_factory, slot_factory, booking_factory
):
    lab_a, lab_b = lab_factory(), lab_factory()
    late = booking_factory(user=alice, slot=slot_factory(lab=lab_a, start_time=at(7, 9)))
    cancelled_early = booking_factory(
        user=alice,
        slot=slot_factory(lab=lab_a, start_time=at(6, 9)),
        created_at=at(5, 8, 5),
        cancelled=True,
        cancelled_at=at(5, 8, 6),
    )
    # Two bookings of one slot (cancelled, then re-booked): same start_time, created order.
    shared = slot_factory(lab=lab_b, start_time=at(6, 9))
    first_made = booking_factory(
        user=alice, slot=shared, created_at=at(5, 8, 1), cancelled=True, cancelled_at=at(5, 8, 2)
    )
    second_made = booking_factory(user=alice, slot=shared, created_at=at(5, 8, 3))
    body = client.get("/me/bookings", headers=auth_headers(alice)).json()
    # Ordered by slot start_time; the three bookings starting 6 Jan 09:00 UTC are
    # ordered by created_at (08:01, 08:03, 08:05); the 7 Jan booking comes last.
    assert [b["id"] for b in body] == [
        first_made.id,
        second_made.id,
        cancelled_early.id,
        late.id,
    ]
    statuses = {b["id"]: b["status"] for b in body}
    assert statuses[cancelled_early.id] == "cancelled"
    assert statuses[first_made.id] == "cancelled"
    assert statuses[second_made.id] == "active"
    assert statuses[late.id] == "active"


def test_my_bookings_include_inactive_lab_and_closure_cancelled(
    client, auth_headers, alice, lab_factory, slot_factory, booking_factory, session
):
    retired = lab_factory(name="Retired", is_active=False)
    in_retired = booking_factory(user=alice, slot=slot_factory(lab=retired, start_time=at(6, 8)))
    by_closure = booking_factory(
        user=alice,
        slot=slot_factory(lab=lab_factory(), start_time=at(7, 8)),
        cancelled=True,
        cancelled_at=at(5, 9),
    )
    body = client.get("/me/bookings", headers=auth_headers(alice)).json()
    assert [b["id"] for b in body] == [in_retired.id, by_closure.id]
    assert body[0]["lab"]["name"] == "Retired"
    assert body[1]["status"] == "cancelled"
    assert body[1]["cancelled_at"] == "2026-01-05T09:00:00Z"


def test_my_bookings_shape_and_cancellable(
    client, auth_headers, alice, lab, slot_factory, booking_factory
):
    active = booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(6, 8)))
    cancelled = booking_factory(
        user=alice, slot=slot_factory(lab=lab, start_time=at(7, 8)), cancelled=True
    )
    body = client.get("/me/bookings", headers=auth_headers(alice)).json()
    assert body[0] == {
        "id": active.id,
        "status": "active",
        "created_at": "2026-01-05T08:00:00Z",
        "cancelled_at": None,
        "cancellable": True,
        "lab": {"id": lab.id, "name": lab.name},
        "slot": {
            "id": active.slot_id,
            "start_time": "2026-01-06T08:00:00Z",
            "end_time": "2026-01-06T09:00:00Z",
        },
    }
    assert body[1]["id"] == cancelled.id
    assert body[1]["cancellable"] is False


def test_cancellable_turns_false_once_slot_starts(
    client, auth_headers, alice, lab, slot_factory, booking_factory, frozen_now
):
    booking_factory(user=alice, slot=slot_factory(lab=lab, start_time=at(5, 10)))
    url, headers = "/me/bookings", auth_headers(alice)
    assert client.get(url, headers=headers).json()[0]["cancellable"] is True
    frozen_now.set(at(5, 10))  # exactly at the start
    assert client.get(url, headers=headers).json()[0]["cancellable"] is False
    frozen_now.set(at(5, 11))  # slot has ended: no longer listed
    assert client.get(url, headers=headers).json() == []


def test_new_booking_appears_in_my_bookings(client, auth_headers, alice, lab, slot_factory):
    slot = slot_factory(lab=lab, start_time=at(5, 10))
    created = book(client, auth_headers, alice, slot.id).json()
    body = client.get("/me/bookings", headers=auth_headers(alice)).json()
    assert body == [created]
