"""Closing a lab for one date (US-7, rules 5.10 to 5.13).

Creating a closure and cancelling the bookings it affects happen in ONE transaction:
either the closure exists and every affected booking is cancelled, or nothing changed.

How that is guaranteed:

* The closure row is inserted (flushed) **first**. The ``uq_lab_closures_lab_date`` unique
  constraint is the arbiter for rule 5.10: of two concurrent requests for the same lab and
  date, only one insert can succeed. In SQLite the insert also takes the write lock, so the
  cancelling ``UPDATE`` and its row count are computed under that lock.
* An ``IntegrityError`` on the insert is turned into 409 ``closure_exists``, the same error
  as the up-front ``is_lab_closed`` check, so the check and the constraint always agree.
* The cancelling is one bulk ``UPDATE`` whose row count is the ``cancelled_booking_count``,
  so the number reported is exactly the number of rows changed.
* Nothing is committed until both steps are done; any exception rolls the session back.
"""

from datetime import date, datetime

from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import ApiError
from app.models import Booking, Lab, LabClosure, Slot
from app.schemas.admin import ClosureCreated, CreateClosureRequest
from app.services.common import is_lab_closed


def _closure_exists() -> ApiError:
    return ApiError(409, "closure_exists", "This lab is already closed on that date.")


def parse_request(raw_body: bytes) -> CreateClosureRequest:
    """Validate the request body, raising 422 ``validation_error`` in the contract shape.

    Done by hand (not as a FastAPI body parameter) so that the contract's check order holds:
    FastAPI would report a bad body before the 401, 403 and 404 checks.
    """
    try:
        return CreateClosureRequest.model_validate_json(raw_body)
    except ValidationError as exc:
        errors = [
            {"loc": ("body", *e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
        ]
        raise RequestValidationError(errors) from None


def cancel_active_bookings(session: Session, lab_id: int, local_date: date, now: datetime) -> int:
    """Cancel every active booking in the lab whose slot starts on ``local_date`` after ``now``.

    Returns how many bookings were cancelled. Already-cancelled bookings are not matched
    (so not counted); bookings whose slot has started or finished, and those in other labs
    or on other dates, are not touched. Does not commit.
    """
    day_start, day_end = clock.local_day_bounds_utc(local_date)
    slot_ids = select(Slot.id).where(
        Slot.lab_id == lab_id,
        Slot.start_time >= day_start,
        Slot.start_time < day_end,
        Slot.start_time > now,
    )
    result = session.execute(
        update(Booking)
        .where(Booking.slot_id.in_(slot_ids), Booking.cancelled_at.is_(None))
        .values(cancelled_at=now)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount


def close_lab(session: Session, lab: Lab, local_date: date) -> ClosureCreated:
    """Close ``lab`` on ``local_date`` and cancel the affected bookings, atomically.

    Raises 422 ``closure_date_in_past`` (date before today in Africa/Johannesburg) and
    409 ``closure_exists``. On any failure nothing is closed and no booking is cancelled.
    """
    now = clock.now_utc()  # one instant for the whole request
    if local_date < clock.local_date_of(now):
        raise ApiError(422, "closure_date_in_past", "You can't close a lab for a date in the past.")

    if is_lab_closed(session, lab.id, local_date):
        raise _closure_exists()

    try:
        closure = LabClosure(lab_id=lab.id, date=local_date, created_at=now)
        session.add(closure)
        try:
            session.flush()  # the unique constraint decides concurrent attempts
        except IntegrityError:
            session.rollback()
            if is_lab_closed(session, lab.id, local_date):
                raise _closure_exists() from None
            raise
        cancelled = cancel_active_bookings(session, lab.id, local_date, now)
        result = ClosureCreated(
            id=closure.id,
            lab_id=lab.id,
            date=closure.date,
            created_at=closure.created_at,
            cancelled_booking_count=cancelled,
        )
        session.commit()
    except BaseException:
        session.rollback()
        raise
    return result
