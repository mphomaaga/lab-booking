"""GET /admin/bookings: every booking for one lab on one local date (US-6)."""

from datetime import date, datetime

import pytest

# Africa/Johannesburg is UTC+2, so local Monday 2026-01-05 08:00 is 06:00 UTC.
DAY = "2026-01-05"
SLOT_8 = datetime(2026, 1, 5, 6, 0)
SLOT_9 = datetime(2026, 1, 5, 7, 0)
SLOT_10 = datetime(2026, 1, 5, 8, 0)


@pytest.fixture
def admin(admin_factory):
    return admin_factory("admin0001")


@pytest.fixture
def get(client, admin, auth_headers):
    def call(**params):
        return client.get("/admin/bookings", params=params, headers=auth_headers(admin))

    return call


def _error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


# --- 401, 403, 404, 422 ---------------------------------------------------------------


def test_requires_login(client, lab_factory):
    lab = lab_factory()
    response = client.get("/admin/bookings", params={"lab_id": lab.id, "date": DAY})
    _error(response, 401, "not_authenticated")


def test_rejects_non_admin(client, user_factory, auth_headers, lab_factory):
    lab = lab_factory()
    response = client.get(
        "/admin/bookings",
        params={"lab_id": lab.id, "date": DAY},
        headers=auth_headers(user_factory()),
    )
    _error(response, 403, "admin_required")


def test_non_admin_gets_403_even_for_unknown_lab_and_bad_params(
    client, user_factory, auth_headers
):
    headers = auth_headers(user_factory())
    _error(
        client.get("/admin/bookings", params={"lab_id": 999, "date": DAY}, headers=headers),
        403,
        "admin_required",
    )
    _error(client.get("/admin/bookings", headers=headers), 403, "admin_required")


def test_unknown_lab_is_404(get):
    _error(get(lab_id=999, date=DAY), 404, "lab_not_found")


def test_inactive_lab_is_404(get, lab_factory):
    lab = lab_factory(is_active=False)
    _error(get(lab_id=lab.id, date=DAY), 404, "lab_not_found")


def test_unknown_lab_is_404_before_a_bad_date_is_validated(get):
    # Contract check order: lab_not_found before validation_error.
    _error(get(lab_id=999, date="not-a-date"), 404, "lab_not_found")
    _error(get(lab_id=999), 404, "lab_not_found")


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"date": DAY},  # lab_id missing
        {"lab_id": "abc", "date": DAY},
        {"lab_id": "", "date": DAY},
    ],
)
def test_bad_lab_id_is_422(get, params):
    response = get(**params)
    _error(response, 422, "validation_error")


@pytest.mark.parametrize(
    "value",
    [None, "", "not-a-date", "2026-13-01", "2026-02-30", "05-01-2026", "20260105", "2026-1-5"],
)
def test_missing_or_malformed_date_is_422(get, lab_factory, value):
    lab = lab_factory()
    params = {"lab_id": lab.id}
    if value is not None:
        params["date"] = value
    response = get(**params)
    _error(response, 422, "validation_error")
    assert any(d["loc"] == ["query", "date"] for d in response.json()["error"]["details"])


# --- 200 ------------------------------------------------------------------------------


def test_empty_day_returns_empty_list(get, lab_factory):
    lab = lab_factory(name="Chem 1", seats=12)
    response = get(lab_id=lab.id, date=DAY)
    assert response.status_code == 200
    assert response.json() == {
        "lab": {"id": lab.id, "name": "Chem 1", "seats": 12},
        "date": DAY,
        "closed": False,
        "bookings": [],
    }


def test_booking_shape_with_student_number(
    get, lab_factory, slot_factory, user_factory, booking_factory
):
    lab = lab_factory()
    slot = slot_factory(lab, SLOT_8)
    student = user_factory("20261234")
    booking = booking_factory(
        student, slot, created_at=datetime(2026, 1, 2, 9, 30, 15, 999999)
    )

    response = get(lab_id=lab.id, date=DAY)

    assert response.status_code == 200
    assert response.json()["bookings"] == [
        {
            "id": booking.id,
            "status": "active",
            "created_at": "2026-01-02T09:30:15Z",
            "cancelled_at": None,
            "slot": {
                "id": slot.id,
                "start_time": "2026-01-05T06:00:00Z",
                "end_time": "2026-01-05T07:00:00Z",
            },
            "user": {"id": student.id, "student_number": "20261234"},
        }
    ]


def test_active_and_cancelled_bookings_are_both_listed(
    get, lab_factory, slot_factory, user_factory, booking_factory
):
    lab = lab_factory()
    slot = slot_factory(lab, SLOT_8)
    active = booking_factory(
        user_factory("20260001"), slot, created_at=datetime(2026, 1, 1, 8, 0)
    )
    cancelled = booking_factory(
        user_factory("20260002"),
        slot,
        cancelled=True,
        created_at=datetime(2026, 1, 2, 8, 0),
        cancelled_at=datetime(2026, 1, 3, 12, 0, 5),
    )

    bookings = get(lab_id=lab.id, date=DAY).json()["bookings"]

    assert [(b["id"], b["status"], b["cancelled_at"]) for b in bookings] == [
        (active.id, "active", None),
        (cancelled.id, "cancelled", "2026-01-03T12:00:05Z"),
    ]
    assert [b["user"]["student_number"] for b in bookings] == ["20260001", "20260002"]


def test_ordered_by_slot_start_then_created_at(
    get, lab_factory, slot_factory, user_factory, booking_factory
):
    lab = lab_factory()
    s8, s9, s10 = (slot_factory(lab, t) for t in (SLOT_8, SLOT_9, SLOT_10))
    # Created in an order that differs from the expected result order.
    b10 = booking_factory(user_factory(), s10, created_at=datetime(2026, 1, 1, 8, 0))
    b9_late = booking_factory(user_factory(), s9, created_at=datetime(2026, 1, 3, 8, 0))
    b8 = booking_factory(user_factory(), s8, created_at=datetime(2026, 1, 4, 8, 0))
    b9_early = booking_factory(user_factory(), s9, created_at=datetime(2026, 1, 2, 8, 0))

    bookings = get(lab_id=lab.id, date=DAY).json()["bookings"]

    assert [b["id"] for b in bookings] == [b8.id, b9_early.id, b9_late.id, b10.id]


def test_ties_on_created_at_are_ordered_by_id(
    get, lab_factory, slot_factory, user_factory, booking_factory
):
    lab = lab_factory()
    slot = slot_factory(lab, SLOT_8)
    same = datetime(2026, 1, 2, 8, 0)
    first = booking_factory(user_factory(), slot, created_at=same)
    second = booking_factory(user_factory(), slot, created_at=same)

    bookings = get(lab_id=lab.id, date=DAY).json()["bookings"]

    assert [b["id"] for b in bookings] == [first.id, second.id]


def test_other_labs_are_excluded(get, lab_factory, slot_factory, booking_factory):
    lab = lab_factory()
    other = lab_factory()
    mine = booking_factory(slot=slot_factory(lab, SLOT_8))
    booking_factory(slot=slot_factory(other, SLOT_8))

    bookings = get(lab_id=lab.id, date=DAY).json()["bookings"]

    assert [b["id"] for b in bookings] == [mine.id]


def test_other_dates_are_excluded(get, lab_factory, slot_factory, booking_factory):
    lab = lab_factory()
    mine = booking_factory(slot=slot_factory(lab, SLOT_8))
    booking_factory(slot=slot_factory(lab, datetime(2026, 1, 6, 6, 0)))
    booking_factory(slot=slot_factory(lab, datetime(2026, 1, 4, 6, 0)))

    bookings = get(lab_id=lab.id, date=DAY).json()["bookings"]

    assert [b["id"] for b in bookings] == [mine.id]


def test_local_date_boundary(get, lab_factory, slot_factory, booking_factory):
    """Johannesburg is UTC+2: local midnight is 22:00 UTC the evening before (rule 5.16)."""
    lab = lab_factory()
    # Local Sunday 2026-01-04 23:59 is still Jan 4 locally, though it is Jan 4 21:59 UTC.
    before = booking_factory(slot=slot_factory(lab, datetime(2026, 1, 4, 21, 59)))
    # Local Monday 00:00 is Jan 4 22:00 UTC: the UTC date is the 4th, the local date the 5th.
    first = booking_factory(slot=slot_factory(lab, datetime(2026, 1, 4, 22, 0)))
    # Local Monday 23:59 is Jan 5 21:59 UTC.
    last = booking_factory(slot=slot_factory(lab, datetime(2026, 1, 5, 21, 59)))
    # Local Tuesday 00:00 is Jan 5 22:00 UTC.
    after = booking_factory(slot=slot_factory(lab, datetime(2026, 1, 5, 22, 0)))

    monday = [b["id"] for b in get(lab_id=lab.id, date="2026-01-05").json()["bookings"]]
    sunday = [b["id"] for b in get(lab_id=lab.id, date="2026-01-04").json()["bookings"]]
    tuesday = [b["id"] for b in get(lab_id=lab.id, date="2026-01-06").json()["bookings"]]

    assert monday == [first.id, last.id]
    assert sunday == [before.id]
    assert tuesday == [after.id]


def test_any_date_is_accepted_past_or_future(
    get, frozen_now, lab_factory, slot_factory, booking_factory
):
    lab = lab_factory()
    past = booking_factory(slot=slot_factory(lab, datetime(2020, 3, 2, 6, 0)))
    future = booking_factory(slot=slot_factory(lab, datetime(2031, 3, 3, 6, 0)))

    assert [b["id"] for b in get(lab_id=lab.id, date="2020-03-02").json()["bookings"]] == [
        past.id
    ]
    assert [b["id"] for b in get(lab_id=lab.id, date="2031-03-03").json()["bookings"]] == [
        future.id
    ]
    response = get(lab_id=lab.id, date="1999-01-01")
    assert response.status_code == 200
    assert response.json()["bookings"] == []


def test_weekend_date_with_no_slots_is_empty(get, lab_factory):
    lab = lab_factory()
    response = get(lab_id=lab.id, date="2026-01-03")  # a Saturday
    assert response.status_code == 200
    assert response.json()["bookings"] == []


def test_closed_flag(get, lab_factory, closure_factory, slot_factory, booking_factory):
    lab = lab_factory()
    other = lab_factory()
    booking = booking_factory(slot=slot_factory(lab, SLOT_8), cancelled=True)
    assert get(lab_id=lab.id, date=DAY).json()["closed"] is False

    closure_factory(other, date(2026, 1, 5))  # another lab's closure does not count
    closure_factory(lab, date(2026, 1, 6))  # nor does another date
    assert get(lab_id=lab.id, date=DAY).json()["closed"] is False

    closure_factory(lab, date(2026, 1, 5))
    body = get(lab_id=lab.id, date=DAY).json()
    assert body["closed"] is True
    assert [b["id"] for b in body["bookings"]] == [booking.id]  # still lists its bookings
