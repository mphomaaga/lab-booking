"""Tests for `POST /admin/labs/{lab_id}/closures` (US-7, rules 5.10 to 5.13, 5.16)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import pytest
from sqlalchemy import func, select

from app.models import Booking, LabClosure
from app.services import closures as closures_service
from app.services.common import is_lab_closed

# The frozen clock starts at 2026-01-05 08:00 UTC = 10:00 in Johannesburg (a Monday).
NOW = datetime(2026, 1, 5, 8, 0)
TODAY = date(2026, 1, 5)
TOMORROW = date(2026, 1, 6)  # Tuesday
# Local 08:00 on TOMORROW is 06:00 UTC.
TOMORROW_8AM = datetime(2026, 1, 6, 6, 0)


def url(lab) -> str:
    return f"/admin/labs/{lab.id}/closures"


@pytest.fixture
def admin(admin_factory):
    return admin_factory()


@pytest.fixture
def post(client, admin, auth_headers, frozen_now):
    """`post(lab, json)` as an admin, with the clock frozen."""

    def send(lab, json):
        return client.post(url(lab), json=json, headers=auth_headers(admin))

    return send


def cancelled_at_of(session, booking):
    session.expire_all()
    return session.get(Booking, booking.id).cancelled_at


def closure_count(session) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(LabClosure))


# --- success ---------------------------------------------------------------------------


def test_closure_is_created_and_future_bookings_are_cancelled(
    post, session, lab_factory, slot_factory, booking_factory
):
    lab = lab_factory()
    b1 = booking_factory(slot=slot_factory(lab=lab, start_time=TOMORROW_8AM))
    b2 = booking_factory(slot=slot_factory(lab=lab, start_time=datetime(2026, 1, 6, 9, 0)))
    # Two students in the same slot count separately.
    slot = slot_factory(lab=lab, start_time=datetime(2026, 1, 6, 10, 0))
    b3 = booking_factory(slot=slot)
    b4 = booking_factory(slot=slot)

    response = post(lab, {"date": "2026-01-06"})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "lab_id", "date", "created_at", "cancelled_booking_count"}
    assert body["lab_id"] == lab.id
    assert body["date"] == "2026-01-06"
    assert body["created_at"] == "2026-01-05T08:00:00Z"
    assert body["cancelled_booking_count"] == 4
    for booking in (b1, b2, b3, b4):
        assert cancelled_at_of(session, booking) == NOW
    closure = session.get(LabClosure, body["id"])
    assert (closure.lab_id, closure.date) == (lab.id, TOMORROW)


def test_closure_with_no_bookings_reports_zero(post, lab_factory):
    response = post(lab_factory(), {"date": "2026-01-06"})
    assert response.status_code == 201
    assert response.json()["cancelled_booking_count"] == 0


def test_lab_is_closed_afterwards(post, session, lab_factory):
    lab = lab_factory()
    assert not is_lab_closed(session, lab.id, TOMORROW)
    assert post(lab, {"date": "2026-01-06"}).status_code == 201
    assert is_lab_closed(session, lab.id, TOMORROW)
    assert not is_lab_closed(session, lab.id, date(2026, 1, 7))


def test_already_cancelled_bookings_are_untouched_and_not_counted(
    post, session, lab_factory, slot_factory, booking_factory
):
    lab = lab_factory()
    slot = slot_factory(lab=lab, start_time=TOMORROW_8AM)
    active = booking_factory(slot=slot)
    earlier = datetime(2026, 1, 4, 12, 0)
    already = booking_factory(slot=slot, cancelled=True, cancelled_at=earlier)

    response = post(lab, {"date": "2026-01-06"})

    assert response.json()["cancelled_booking_count"] == 1
    assert cancelled_at_of(session, active) == NOW
    assert cancelled_at_of(session, already) == earlier  # not overwritten


def test_other_dates_and_other_labs_are_untouched(
    post, session, lab_factory, slot_factory, booking_factory
):
    lab, other_lab = lab_factory(), lab_factory()
    target = booking_factory(slot=slot_factory(lab=lab, start_time=TOMORROW_8AM))
    next_day = booking_factory(slot=slot_factory(lab=lab, start_time=datetime(2026, 1, 7, 6, 0)))
    same_day_other_lab = booking_factory(slot=slot_factory(lab=other_lab, start_time=TOMORROW_8AM))

    response = post(lab, {"date": "2026-01-06"})

    assert response.json()["cancelled_booking_count"] == 1
    assert cancelled_at_of(session, target) == NOW
    assert cancelled_at_of(session, next_day) is None
    assert cancelled_at_of(session, same_day_other_lab) is None
    # The other lab is not closed either.
    assert not is_lab_closed(session, other_lab.id, TOMORROW)


def test_local_date_boundaries_use_johannesburg_time(
    post, session, lab_factory, slot_factory, booking_factory
):
    # Closing 2026-01-07 covers 2026-01-06 22:00 UTC (00:00 local) up to 2026-01-07 21:59 UTC.
    lab = lab_factory()
    times = {
        "before": datetime(2026, 1, 6, 21, 0),  # 23:00 local on the 6th
        "first": datetime(2026, 1, 6, 22, 0),  # 00:00 local on the 7th
        "last": datetime(2026, 1, 7, 21, 0),  # 23:00 local on the 7th
        "after": datetime(2026, 1, 7, 22, 0),  # 00:00 local on the 8th
    }
    bookings = {k: booking_factory(slot=slot_factory(lab=lab, start_time=t)) for k, t in times.items()}

    response = post(lab, {"date": "2026-01-07"})

    assert response.json()["cancelled_booking_count"] == 2
    assert cancelled_at_of(session, bookings["before"]) is None
    assert cancelled_at_of(session, bookings["first"]) == NOW
    assert cancelled_at_of(session, bookings["last"]) == NOW
    assert cancelled_at_of(session, bookings["after"]) is None


def test_today_is_allowed_but_started_slots_are_left_alone(
    post, frozen_now, session, lab_factory, slot_factory, booking_factory
):
    frozen_now.set(datetime(2026, 1, 5, 10, 30))  # 12:30 local
    lab = lab_factory()
    finished = booking_factory(slot=slot_factory(lab=lab, start_time=datetime(2026, 1, 5, 8, 0)))
    running = booking_factory(slot=slot_factory(lab=lab, start_time=datetime(2026, 1, 5, 10, 0)))
    starting_now = booking_factory(
        slot=slot_factory(lab=lab, start_time=datetime(2026, 1, 5, 10, 30))
    )
    later = booking_factory(slot=slot_factory(lab=lab, start_time=datetime(2026, 1, 5, 11, 0)))

    response = post(lab, {"date": "2026-01-05"})

    assert response.status_code == 201
    assert response.json()["cancelled_booking_count"] == 1
    assert cancelled_at_of(session, finished) is None
    assert cancelled_at_of(session, running) is None
    assert cancelled_at_of(session, starting_now) is None  # "starts after now" is strict
    assert cancelled_at_of(session, later) == datetime(2026, 1, 5, 10, 30)


@pytest.mark.parametrize(
    "day",
    [
        "2026-01-10",  # Saturday
        "2026-01-11",  # Sunday
        "2026-01-12",  # beyond the 7-day booking window
        "2030-12-25",  # far future, no upper limit
    ],
)
def test_weekends_and_far_dates_are_allowed(post, lab_factory, day):
    assert post(lab_factory(), {"date": day}).status_code == 201


def test_two_labs_can_close_the_same_date(post, lab_factory):
    assert post(lab_factory(), {"date": "2026-01-06"}).status_code == 201
    assert post(lab_factory(), {"date": "2026-01-06"}).status_code == 201


def test_same_lab_can_close_different_dates(post, lab_factory):
    lab = lab_factory()
    assert post(lab, {"date": "2026-01-06"}).status_code == 201
    assert post(lab, {"date": "2026-01-07"}).status_code == 201


# --- duplicate closure (rule 5.10) -----------------------------------------------------


def test_duplicate_closure_is_409_and_cancels_nothing(
    post, session, lab_factory, slot_factory, booking_factory, closure_factory
):
    lab = lab_factory()
    closure_factory(lab=lab, date=TOMORROW)
    booking = booking_factory(slot=slot_factory(lab=lab, start_time=TOMORROW_8AM))

    response = post(lab, {"date": "2026-01-06"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "closure_exists"
    assert cancelled_at_of(session, booking) is None
    assert closure_count(session) == 1


def test_closing_twice_in_a_row_is_409_the_second_time(post, session, lab_factory):
    lab = lab_factory()
    assert post(lab, {"date": "2026-01-06"}).status_code == 201
    second = post(lab, {"date": "2026-01-06"})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "closure_exists"
    assert closure_count(session) == 1


def test_losing_a_race_is_409_not_500_and_cancels_nothing(
    post, session, monkeypatch, lab_factory, slot_factory, booking_factory, closure_factory
):
    """The up-front check passes (the other request has not committed yet), then the
    unique constraint rejects the insert: the answer must still be 409 `closure_exists`."""
    lab = lab_factory()
    closure_factory(lab=lab, date=TOMORROW)
    booking = booking_factory(slot=slot_factory(lab=lab, start_time=TOMORROW_8AM))
    checks = []

    def stale_check(db, lab_id, local_date):
        # First call (the up-front check) says "not closed"; later calls tell the truth.
        checks.append(1)
        return len(checks) > 1

    monkeypatch.setattr(closures_service, "is_lab_closed", stale_check)

    response = post(lab, {"date": "2026-01-06"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "closure_exists"
    assert cancelled_at_of(session, booking) is None
    assert closure_count(session) == 1


def test_concurrent_requests_create_one_closure_and_cancel_once(
    client, admin, auth_headers, frozen_now, session, lab_factory, slot_factory, booking_factory
):
    lab = lab_factory()
    slot = slot_factory(lab=lab, start_time=TOMORROW_8AM)
    bookings = [booking_factory(slot=slot) for _ in range(3)]
    headers = auth_headers(admin)

    def attempt(_):
        return client.post(url(lab), json={"date": "2026-01-06"}, headers=headers)

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(attempt, range(4)))

    codes = sorted(r.status_code for r in responses)
    assert codes == [201, 409, 409, 409]
    created = next(r for r in responses if r.status_code == 201)
    assert created.json()["cancelled_booking_count"] == 3
    assert {r.json()["error"]["code"] for r in responses if r.status_code == 409} == {
        "closure_exists"
    }
    assert closure_count(session) == 1
    assert all(cancelled_at_of(session, b) == NOW for b in bookings)


# --- atomicity ---------------------------------------------------------------------------


def test_failure_after_cancelling_rolls_back_closure_and_bookings(
    post, session, monkeypatch, lab_factory, slot_factory, booking_factory
):
    lab = lab_factory()
    bookings = [
        booking_factory(slot=slot_factory(lab=lab, start_time=TOMORROW_8AM)),
        booking_factory(slot=slot_factory(lab=lab, start_time=datetime(2026, 1, 6, 7, 0))),
    ]
    real_cancel = closures_service.cancel_active_bookings

    def cancel_then_fail(*args, **kwargs):
        assert real_cancel(*args, **kwargs) == 2  # the UPDATE really ran...
        raise RuntimeError("boom")  # ...and then something went wrong

    monkeypatch.setattr(closures_service, "cancel_active_bookings", cancel_then_fail)

    response = post(lab, {"date": "2026-01-06"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert closure_count(session) == 0
    assert all(cancelled_at_of(session, b) is None for b in bookings)
    assert not is_lab_closed(session, lab.id, TOMORROW)


def test_failure_while_cancelling_leaves_nothing_behind(
    post, session, monkeypatch, lab_factory, slot_factory, booking_factory
):
    lab = lab_factory()
    booking = booking_factory(slot=slot_factory(lab=lab, start_time=TOMORROW_8AM))

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(closures_service, "cancel_active_bookings", fail)

    assert post(lab, {"date": "2026-01-06"}).status_code == 500
    assert closure_count(session) == 0
    assert cancelled_at_of(session, booking) is None


def test_the_closure_can_be_created_again_after_a_failed_attempt(
    post, monkeypatch, lab_factory
):
    lab = lab_factory()
    with monkeypatch.context() as m:
        m.setattr(
            closures_service,
            "cancel_active_bookings",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        assert post(lab, {"date": "2026-01-06"}).status_code == 500
    assert post(lab, {"date": "2026-01-06"}).status_code == 201


# --- date in the past ----------------------------------------------------------------------


def test_past_date_is_422(post, session, lab_factory, slot_factory, booking_factory):
    lab = lab_factory()
    booking = booking_factory(slot=slot_factory(lab=lab, start_time=datetime(2026, 1, 5, 12, 0)))

    response = post(lab, {"date": "2026-01-04"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "closure_date_in_past"
    assert closure_count(session) == 0
    assert cancelled_at_of(session, booking) is None


def test_past_is_judged_in_johannesburg_time(post, frozen_now, lab_factory):
    # 22:30 UTC on the 5th is already 00:30 on the 6th in Johannesburg.
    frozen_now.set(datetime(2026, 1, 5, 22, 30))
    lab = lab_factory()
    assert post(lab, {"date": "2026-01-05"}).json()["error"]["code"] == "closure_date_in_past"
    assert post(lab, {"date": "2026-01-06"}).status_code == 201


def test_today_in_johannesburg_is_allowed_just_before_midnight(post, frozen_now, lab_factory):
    frozen_now.set(datetime(2026, 1, 5, 21, 59))  # 23:59 local on the 5th
    assert post(lab_factory(), {"date": "2026-01-05"}).status_code == 201


# --- auth and check order ---------------------------------------------------------------------


def test_no_token_is_401(client, frozen_now, lab_factory):
    response = client.post(url(lab_factory()), json={"date": "2026-01-06"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_bad_token_is_401(client, frozen_now, lab_factory):
    response = client.post(
        url(lab_factory()), json={"date": "2026-01-06"}, headers={"Authorization": "Bearer nope"}
    )
    assert response.status_code == 401


def test_non_admin_is_403_and_nothing_changes(
    client, frozen_now, session, user_factory, auth_headers, lab_factory, slot_factory,
    booking_factory,
):
    lab = lab_factory()
    booking = booking_factory(slot=slot_factory(lab=lab, start_time=TOMORROW_8AM))
    student = user_factory()

    response = client.post(url(lab), json={"date": "2026-01-06"}, headers=auth_headers(student))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_required"
    assert closure_count(session) == 0
    assert cancelled_at_of(session, booking) is None


def test_401_comes_before_a_bad_body(client, frozen_now, lab_factory):
    response = client.post(url(lab_factory()), content=b"not json")
    assert response.status_code == 401


def test_403_comes_before_404_and_validation(client, user_factory, auth_headers):
    student = user_factory()
    response = client.post(
        "/admin/labs/999/closures", json={"nonsense": 1}, headers=auth_headers(student)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_required"


def test_missing_lab_is_404(client, admin, auth_headers, frozen_now):
    response = client.post(
        "/admin/labs/999/closures", json={"date": "2026-01-06"}, headers=auth_headers(admin)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "lab_not_found"


def test_inactive_lab_is_404(post, session, lab_factory):
    lab = lab_factory(is_active=False)
    response = post(lab, {"date": "2026-01-06"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "lab_not_found"
    assert closure_count(session) == 0


def test_404_comes_before_validation_error(client, admin, auth_headers, frozen_now):
    response = client.post(
        "/admin/labs/999/closures", json={"date": "not a date"}, headers=auth_headers(admin)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "lab_not_found"


def test_404_comes_before_past_date(client, admin, auth_headers, frozen_now):
    response = client.post(
        "/admin/labs/999/closures", json={"date": "2020-01-01"}, headers=auth_headers(admin)
    )
    assert response.status_code == 404


def test_validation_error_comes_before_the_date_checks(post, lab_factory, closure_factory):
    lab = lab_factory()
    closure_factory(lab=lab, date=TOMORROW)
    # Extra field is rejected even though the date alone would be a 409.
    response = post(lab, {"date": "2026-01-06", "reason": "holiday"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_past_date_comes_before_closure_exists(post, lab_factory, closure_factory):
    lab = lab_factory()
    closure_factory(lab=lab, date=date(2026, 1, 1))  # a closure on a past date already exists
    response = post(lab, {"date": "2026-01-01"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "closure_date_in_past"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"date": None},
        {"date": "tomorrow"},
        {"date": "2026-13-45"},
        {"date": ["2026-01-06"]},
        {"date": "2026-01-06", "extra": True},
    ],
)
def test_bad_body_is_422_validation_error(post, session, lab_factory, payload):
    response = post(lab_factory(), payload)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"] and all({"loc", "msg"} <= set(d) for d in error["details"])
    assert closure_count(session) == 0


@pytest.mark.parametrize("content", [b"", b"not json", b"[1]", b"null"])
def test_unparseable_body_is_422_validation_error(
    client, admin, auth_headers, frozen_now, lab_factory, content
):
    response = client.post(
        url(lab_factory()),
        content=content,
        headers={**auth_headers(admin), "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_bad_lab_id_is_422_validation_error(client, admin, auth_headers, frozen_now):
    response = client.post(
        "/admin/labs/abc/closures", json={"date": "2026-01-06"}, headers=auth_headers(admin)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- no undo -------------------------------------------------------------------------------


def test_there_is_no_way_to_delete_or_reopen_a_closure(
    client, admin, auth_headers, frozen_now, lab_factory, closure_factory
):
    lab = lab_factory()
    closure = closure_factory(lab=lab, date=TOMORROW)
    headers = auth_headers(admin)
    for method, path in [
        ("DELETE", url(lab)),
        ("DELETE", f"{url(lab)}/{closure.id}"),
        ("PUT", url(lab)),
        ("PATCH", url(lab)),
        ("GET", url(lab)),
    ]:
        response = client.request(method, path, headers=headers)
        assert response.status_code in (404, 405), (method, path)


def test_cancelled_bookings_stay_cancelled_in_the_database(
    post, session, lab_factory, slot_factory, booking_factory
):
    lab = lab_factory()
    booking = booking_factory(slot=slot_factory(lab=lab, start_time=TOMORROW_8AM))
    assert post(lab, {"date": "2026-01-06"}).status_code == 201
    assert cancelled_at_of(session, booking) == NOW
    # A second (rejected) attempt does not change it.
    post(lab, {"date": "2026-01-06"})
    assert cancelled_at_of(session, booking) == NOW
