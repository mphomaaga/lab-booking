"""GET /labs and GET /labs/{lab_id}/slots (US-2).

Time is frozen with `frozen_now`. Its default, 2026-01-05 08:00 UTC, is Monday 10:00 in
Africa/Johannesburg, so the booking window is Mon 2026-01-05 .. Sun 2026-01-11
(Saturday the 10th and Sunday the 11th are weekend days).
"""

from datetime import datetime

from sqlalchemy import func, select

from app.models import Slot

MONDAY = "2026-01-05"  # today under the default frozen clock
SATURDAY = "2026-01-10"
SUNDAY = "2026-01-11"
LAST_DAY = SUNDAY  # today + 6


def _slots(client, headers, lab_id, date):
    return client.get(f"/labs/{lab_id}/slots", params={"date": date}, headers=headers)


def _slot_count(session) -> int:
    return session.scalar(select(func.count()).select_from(Slot))


# ----- GET /labs ---------------------------------------------------------------------


def test_list_labs_requires_login(client):
    response = client.get("/labs")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_list_labs_ordered_by_name(client, user_factory, auth_headers, lab_factory):
    lab_factory(name="Lab C", seats=12)
    lab_factory(name="Lab A", seats=30)
    lab_factory(name="Lab B", seats=20)
    response = client.get("/labs", headers=auth_headers(user_factory()))
    assert response.status_code == 200
    assert [(lab["name"], lab["seats"]) for lab in response.json()] == [
        ("Lab A", 30),
        ("Lab B", 20),
        ("Lab C", 12),
    ]
    assert set(response.json()[0]) == {"id", "name", "seats"}


def test_list_labs_leaves_out_inactive_labs(client, user_factory, auth_headers, lab_factory):
    lab_factory(name="Lab A")
    lab_factory(name="Lab B", is_active=False)
    response = client.get("/labs", headers=auth_headers(user_factory()))
    assert [lab["name"] for lab in response.json()] == ["Lab A"]


def test_list_labs_empty(client, user_factory, auth_headers):
    response = client.get("/labs", headers=auth_headers(user_factory()))
    assert response.status_code == 200
    assert response.json() == []


def test_list_labs_admin_can_read_too(client, admin_factory, auth_headers, lab_factory):
    lab_factory()
    response = client.get("/labs", headers=auth_headers(admin_factory()))
    assert response.status_code == 200
    assert len(response.json()) == 1


# ----- check order: auth, lab, window ------------------------------------------------


def test_slots_require_login(client, frozen_now, lab_factory):
    lab = lab_factory()
    response = client.get(f"/labs/{lab.id}/slots", params={"date": MONDAY})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_slots_unknown_lab_is_404(client, frozen_now, user_factory, auth_headers):
    response = _slots(client, auth_headers(user_factory()), 999, MONDAY)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "lab_not_found"


def test_slots_inactive_lab_is_404(client, frozen_now, user_factory, auth_headers, lab_factory):
    lab = lab_factory(is_active=False)
    response = _slots(client, auth_headers(user_factory()), lab.id, MONDAY)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "lab_not_found"


def test_lab_check_comes_before_window_check(client, frozen_now, user_factory, auth_headers):
    response = _slots(client, auth_headers(user_factory()), 999, "2030-01-01")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "lab_not_found"


def test_date_before_today_is_out_of_window(client, frozen_now, user_factory, auth_headers, lab_factory):
    lab = lab_factory()
    response = _slots(client, auth_headers(user_factory()), lab.id, "2026-01-04")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "date_out_of_window"


def test_date_after_today_plus_6_is_out_of_window(client, frozen_now, user_factory, auth_headers, lab_factory):
    lab = lab_factory()
    response = _slots(client, auth_headers(user_factory()), lab.id, "2026-01-12")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "date_out_of_window"


def test_out_of_window_is_checked_before_weekend_and_closure(
    client, frozen_now, user_factory, auth_headers, lab_factory, closure_factory, session
):
    lab = lab_factory()
    closure_factory(lab=lab, date=datetime(2026, 1, 17).date())  # a Saturday, also a closure
    response = _slots(client, auth_headers(user_factory()), lab.id, "2026-01-17")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "date_out_of_window"
    assert _slot_count(session) == 0


def test_window_edges_are_today_and_today_plus_6(client, frozen_now, user_factory, auth_headers, lab_factory):
    lab = lab_factory()
    headers = auth_headers(user_factory())
    assert _slots(client, headers, lab.id, MONDAY).status_code == 200
    assert _slots(client, headers, lab.id, LAST_DAY).status_code == 200


def test_today_follows_johannesburg_not_utc(client, frozen_now, user_factory, auth_headers, lab_factory):
    # 22:30 UTC on Mon 5 Jan is 00:30 on Tue 6 Jan in Johannesburg (rule 5.16).
    frozen_now.set(datetime(2026, 1, 5, 22, 30))
    lab = lab_factory()
    headers = auth_headers(user_factory())

    before = _slots(client, headers, lab.id, "2026-01-05")
    assert before.status_code == 422
    assert before.json()["error"]["code"] == "date_out_of_window"

    first = _slots(client, headers, lab.id, "2026-01-06")
    assert first.status_code == 200
    assert first.json()["day_status"] == "open"

    last = _slots(client, headers, lab.id, "2026-01-12")
    assert last.status_code == 200
    assert _slots(client, headers, lab.id, "2026-01-13").status_code == 422


# ----- weekend and closed days -------------------------------------------------------


def test_weekend_gives_weekend_status_and_no_rows(
    client, frozen_now, user_factory, auth_headers, lab_factory, session
):
    lab = lab_factory(name="Lab A", seats=30)
    headers = auth_headers(user_factory())
    for day in (SATURDAY, SUNDAY):
        response = _slots(client, headers, lab.id, day)
        assert response.status_code == 200
        assert response.json() == {
            "lab": {"id": lab.id, "name": "Lab A", "seats": 30},
            "date": day,
            "day_status": "weekend",
            "slots": [],
        }
    assert _slot_count(session) == 0


def test_weekend_wins_over_closure(client, frozen_now, user_factory, auth_headers, lab_factory, closure_factory):
    lab = lab_factory()
    closure_factory(lab=lab, date=datetime(2026, 1, 10).date())
    response = _slots(client, auth_headers(user_factory()), lab.id, SATURDAY)
    assert response.json()["day_status"] == "weekend"


def test_closed_day_gives_closed_status_and_no_rows(
    client, frozen_now, user_factory, auth_headers, lab_factory, closure_factory, session
):
    lab = lab_factory()
    closure_factory(lab=lab, date=datetime(2026, 1, 6).date())
    response = _slots(client, auth_headers(user_factory()), lab.id, "2026-01-06")
    assert response.status_code == 200
    body = response.json()
    assert body["day_status"] == "closed"
    assert body["slots"] == []
    assert body["date"] == "2026-01-06"
    assert _slot_count(session) == 0


def test_closure_only_affects_its_own_lab_and_date(
    client, frozen_now, user_factory, auth_headers, lab_factory, closure_factory
):
    closed_lab = lab_factory()
    other_lab = lab_factory()
    closure_factory(lab=closed_lab, date=datetime(2026, 1, 6).date())
    headers = auth_headers(user_factory())
    assert _slots(client, headers, other_lab.id, "2026-01-06").json()["day_status"] == "open"
    assert _slots(client, headers, closed_lab.id, "2026-01-07").json()["day_status"] == "open"


# ----- open day ----------------------------------------------------------------------


def test_open_day_has_ten_hourly_slots_in_utc(client, frozen_now, user_factory, auth_headers, lab_factory):
    lab = lab_factory(name="Lab A", seats=30)
    response = _slots(client, auth_headers(user_factory()), lab.id, "2026-01-06")
    assert response.status_code == 200
    body = response.json()
    assert body["lab"] == {"id": lab.id, "name": "Lab A", "seats": 30}
    assert body["date"] == "2026-01-06"
    assert body["day_status"] == "open"
    slots = body["slots"]
    assert len(slots) == 10
    # Local 08:00 .. 17:00 is 06:00 .. 15:00 UTC; each slot is one hour long.
    assert [s["start_time"] for s in slots] == [f"2026-01-06T{h:02d}:00:00Z" for h in range(6, 16)]
    assert [s["end_time"] for s in slots] == [f"2026-01-06T{h:02d}:00:00Z" for h in range(7, 17)]
    assert all(set(s) == {"id", "start_time", "end_time", "seats", "free_seats", "bookable"} for s in slots)
    assert all(s["seats"] == 30 and s["free_seats"] == 30 for s in slots)
    assert len({s["id"] for s in slots}) == 10


def test_slots_are_created_on_demand_and_idempotent(
    client, frozen_now, user_factory, auth_headers, lab_factory, session
):
    lab = lab_factory()
    headers = auth_headers(user_factory())
    assert _slot_count(session) == 0
    first = _slots(client, headers, lab.id, "2026-01-06").json()
    assert _slot_count(session) == 10
    second = _slots(client, headers, lab.id, "2026-01-06").json()
    assert _slot_count(session) == 10
    assert [s["id"] for s in first["slots"]] == [s["id"] for s in second["slots"]]


def test_slots_are_per_lab_and_per_date(client, frozen_now, user_factory, auth_headers, lab_factory, session):
    lab_a = lab_factory()
    lab_b = lab_factory()
    headers = auth_headers(user_factory())
    a = _slots(client, headers, lab_a.id, "2026-01-06").json()
    b = _slots(client, headers, lab_b.id, "2026-01-06").json()
    c = _slots(client, headers, lab_a.id, "2026-01-07").json()
    assert _slot_count(session) == 30
    ids = {s["id"] for d in (a, b, c) for s in d["slots"]}
    assert len(ids) == 30


def test_existing_slot_rows_are_reused(client, frozen_now, user_factory, auth_headers, lab_factory, slot_factory, session):
    lab = lab_factory()
    existing = slot_factory(lab=lab, start_time=datetime(2026, 1, 6, 8, 0))  # local 10:00
    response = _slots(client, auth_headers(user_factory()), lab.id, "2026-01-06")
    slots = response.json()["slots"]
    assert len(slots) == 10
    assert _slot_count(session) == 10
    assert slots[2]["start_time"] == "2026-01-06T08:00:00Z"
    assert slots[2]["id"] == existing.id


# ----- free seats and bookable -------------------------------------------------------


def _first_slot(client, headers, lab, date="2026-01-06"):
    return _slots(client, headers, lab.id, date).json()["slots"][0]


def test_free_seats_count_active_bookings_only(
    client, frozen_now, user_factory, auth_headers, lab_factory, booking_factory, session
):
    lab = lab_factory(seats=5)
    headers = auth_headers(user_factory())
    slot_row = session.get(Slot, _first_slot(client, headers, lab)["id"])

    booking_factory(slot=slot_row)
    booking_factory(slot=slot_row)
    booking_factory(slot=slot_row, cancelled=True)  # cancelled bookings free the seat (rule 5.7)

    slot = _first_slot(client, headers, lab)
    assert slot["seats"] == 5
    assert slot["free_seats"] == 3
    assert slot["bookable"] is True
    # Other slots are untouched.
    others = _slots(client, headers, lab.id, "2026-01-06").json()["slots"][1:]
    assert all(s["free_seats"] == 5 for s in others)


def test_bookings_in_another_lab_do_not_use_seats(
    client, frozen_now, user_factory, auth_headers, lab_factory, booking_factory, session
):
    lab_a = lab_factory(seats=5)
    lab_b = lab_factory(seats=5)
    headers = auth_headers(user_factory())
    slot_b = session.get(Slot, _first_slot(client, headers, lab_b)["id"])
    booking_factory(slot=slot_b)
    assert _first_slot(client, headers, lab_a)["free_seats"] == 5
    assert _first_slot(client, headers, lab_b)["free_seats"] == 4


def test_full_slot_is_listed_but_not_bookable(
    client, frozen_now, user_factory, auth_headers, lab_factory, booking_factory, session
):
    lab = lab_factory(seats=2)
    headers = auth_headers(user_factory())
    slot_row = session.get(Slot, _first_slot(client, headers, lab)["id"])
    booking_factory(slot=slot_row)
    booking_factory(slot=slot_row)

    slots = _slots(client, headers, lab.id, "2026-01-06").json()["slots"]
    assert len(slots) == 10
    assert slots[0]["free_seats"] == 0
    assert slots[0]["bookable"] is False
    assert all(s["bookable"] for s in slots[1:])


def test_all_cancelled_bookings_leave_the_slot_free(
    client, frozen_now, user_factory, auth_headers, lab_factory, booking_factory, session
):
    lab = lab_factory(seats=1)
    headers = auth_headers(user_factory())
    slot_row = session.get(Slot, _first_slot(client, headers, lab)["id"])
    booking_factory(slot=slot_row, cancelled=True)
    slot = _first_slot(client, headers, lab)
    assert slot["free_seats"] == 1
    assert slot["bookable"] is True


def test_free_seats_never_below_zero(
    client, frozen_now, user_factory, auth_headers, lab_factory, booking_factory, session
):
    lab = lab_factory(seats=1)
    headers = auth_headers(user_factory())
    slot_row = session.get(Slot, _first_slot(client, headers, lab)["id"])
    booking_factory(slot=slot_row)
    booking_factory(slot=slot_row)  # more active bookings than seats (e.g. seats were reduced)
    slot = _first_slot(client, headers, lab)
    assert slot["free_seats"] == 0
    assert slot["bookable"] is False


def test_started_slots_are_listed_but_not_bookable(
    client, frozen_now, user_factory, auth_headers, lab_factory
):
    # 10:00 UTC (12:00 local): the 06:00 .. 10:00 UTC slots have started, and the 10:00
    # slot starts exactly now, which also counts as started (rule 5.8).
    frozen_now.set(datetime(2026, 1, 5, 10, 0))
    lab = lab_factory()
    slots = _slots(client, auth_headers(user_factory()), lab.id, MONDAY).json()["slots"]
    assert len(slots) == 10
    assert [s["bookable"] for s in slots] == [False] * 5 + [True] * 5
    assert slots[4]["start_time"] == "2026-01-05T10:00:00Z"
    assert all(s["free_seats"] == 30 for s in slots)


def test_slot_becomes_bookable_false_one_second_after_start(
    client, frozen_now, user_factory, auth_headers, lab_factory
):
    lab = lab_factory()
    headers = auth_headers(user_factory())
    frozen_now.set(datetime(2026, 1, 5, 9, 59, 59))
    assert _slots(client, headers, lab.id, MONDAY).json()["slots"][4]["bookable"] is True
    frozen_now.advance(seconds=1)
    assert _slots(client, headers, lab.id, MONDAY).json()["slots"][4]["bookable"] is False


def test_future_day_slots_are_all_bookable(client, frozen_now, user_factory, auth_headers, lab_factory):
    frozen_now.set(datetime(2026, 1, 5, 20, 0))  # late on the 5th: today's slots are all over
    lab = lab_factory()
    headers = auth_headers(user_factory())
    assert not any(s["bookable"] for s in _slots(client, headers, lab.id, MONDAY).json()["slots"])
    assert all(s["bookable"] for s in _slots(client, headers, lab.id, "2026-01-06").json()["slots"])


# ----- validation --------------------------------------------------------------------


def test_missing_date_is_validation_error(client, frozen_now, user_factory, auth_headers, lab_factory):
    lab = lab_factory()
    response = client.get(f"/labs/{lab.id}/slots", headers=auth_headers(user_factory()))
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"][0]["loc"] == ["query", "date"]


def test_malformed_date_is_validation_error(client, frozen_now, user_factory, auth_headers, lab_factory):
    lab = lab_factory()
    headers = auth_headers(user_factory())
    for bad in ("tomorrow", "2026-13-01", "05-01-2026", ""):
        response = _slots(client, headers, lab.id, bad)
        assert response.status_code == 422, bad
        assert response.json()["error"]["code"] == "validation_error", bad


def test_non_numeric_lab_id_is_validation_error(client, frozen_now, user_factory, auth_headers):
    response = client.get("/labs/abc/slots", params={"date": MONDAY}, headers=auth_headers(user_factory()))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
