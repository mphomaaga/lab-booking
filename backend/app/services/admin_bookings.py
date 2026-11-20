"""Admin view of one lab's bookings on one local date (US-6)."""

import re
from datetime import date
from typing import Any

from fastapi.exceptions import RequestValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import local_day_bounds_utc
from app.models import Booking, Slot, User
from app.schemas import AdminBooking, AdminDayBookings, BookingStatus, Lab, SlotRef, UserRef
from app.services.common import get_active_lab_or_404, is_lab_closed

_INT_RE = re.compile(r"-?\d+")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _bad(field: str, msg: str, type_: str) -> dict[str, Any]:
    return {"loc": ("query", field), "msg": msg, "type": type_}


def parse_lab_id(raw: str | None) -> tuple[int | None, dict[str, Any] | None]:
    """The lab id, or a validation detail if it is missing or not an integer."""
    if raw is None:
        return None, _bad("lab_id", "Field required", "missing")
    if not _INT_RE.fullmatch(raw):
        return None, _bad("lab_id", "Input should be a valid integer", "int_parsing")
    return int(raw), None


def parse_date(raw: str | None) -> tuple[date | None, dict[str, Any] | None]:
    """The date (YYYY-MM-DD), or a validation detail if it is missing or malformed."""
    if raw is None:
        return None, _bad("date", "Field required", "missing")
    if _DATE_RE.fullmatch(raw):
        try:
            return date.fromisoformat(raw), None
        except ValueError:
            pass
    return None, _bad("date", "Input should be a valid date (YYYY-MM-DD)", "date_parsing")


def list_day_bookings(
    session: Session, raw_lab_id: str | None, raw_date: str | None
) -> AdminDayBookings:
    """Every booking, active and cancelled, for the lab's slots starting on the local date.

    Check order follows the contract: 404 ``lab_not_found`` (rule 5.12) before 422
    ``validation_error``. A lab_id that is missing or malformed cannot be looked up, so
    it is reported as a 422 together with any date problem.
    """
    lab_id, lab_problem = parse_lab_id(raw_lab_id)
    lab = get_active_lab_or_404(session, lab_id) if lab_id is not None else None
    day, date_problem = parse_date(raw_date)
    problems = [p for p in (lab_problem, date_problem) if p is not None]
    if problems:
        raise RequestValidationError(problems)
    assert lab is not None and day is not None

    start, end = local_day_bounds_utc(day)  # the local day as a UTC range (rule 5.16)
    rows = session.execute(
        select(Booking, Slot, User)
        .join(Slot, Booking.slot_id == Slot.id)
        .join(User, Booking.user_id == User.id)
        .where(Slot.lab_id == lab.id, Slot.start_time >= start, Slot.start_time < end)
        .order_by(Slot.start_time, Booking.created_at, Booking.id)
    ).all()

    bookings = [
        AdminBooking(
            id=booking.id,
            status=(
                BookingStatus.active if booking.cancelled_at is None else BookingStatus.cancelled
            ),
            created_at=booking.created_at,
            cancelled_at=booking.cancelled_at,
            slot=SlotRef.model_validate(slot),
            user=UserRef.model_validate(user),
        )
        for booking, slot, user in rows
    ]
    return AdminDayBookings(
        lab=Lab.model_validate(lab),
        date=day,
        closed=is_lab_closed(session, lab.id, day),
        bookings=bookings,
    )
