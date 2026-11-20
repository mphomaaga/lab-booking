"""Create, cancel and list bookings (US-3, US-4, US-5; rules 5.4 to 5.10, 5.12, 5.13).

Every time-dependent rule reads "now" through ``clock.now_utc()`` (looked up on the
module at call time) and every date through the clock helpers, so tests can freeze time.
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import ApiError
from app.models import Booking as BookingRow
from app.models import Lab, Slot, User
from app.schemas.bookings import Booking, BookingStatus
from app.schemas.labs import LabRef, SlotRef
from app.services import common

MAX_BOOKINGS_PER_DAY = 2  # rule 5.6


def to_schema(booking: BookingRow, slot: Slot, lab: Lab) -> Booking:
    """Render a booking row with its slot and lab as the contract `Booking`."""
    active = booking.cancelled_at is None
    return Booking(
        id=booking.id,
        status=BookingStatus.active if active else BookingStatus.cancelled,
        created_at=booking.created_at,
        cancelled_at=booking.cancelled_at,
        # US-5: only an active booking that has not started can be cancelled.
        cancellable=active and slot.start_time > clock.now_utc(),
        lab=LabRef(id=lab.id, name=lab.name),
        slot=SlotRef(id=slot.id, start_time=slot.start_time, end_time=slot.end_time),
    )


def create_booking(session: Session, user: User, slot_id: int) -> Booking:
    """Book one seat in the slot for ``user``, running the checks in the contract's order.

    The checks and the insert share one transaction: nothing is written until every
    check has passed, and the single commit at the end writes the booking.
    """
    now = clock.now_utc()

    # 1. Slot missing, or its lab inactive (rule 5.12).
    slot = session.get(Slot, slot_id)
    lab = session.get(Lab, slot.lab_id) if slot is not None else None
    if slot is None or lab is None or not lab.is_active:
        raise ApiError(404, "slot_not_found", "Slot not found.")

    # 2. Already started (rule 5.8): bookable only until the start time.
    if slot.start_time <= now:
        raise ApiError(422, "slot_in_past", "This slot has already started.")

    # 3. Outside today + 6 days (rule 5.5).
    local_date = clock.local_date_of(slot.start_time)
    first, last = clock.booking_window()
    if not first <= local_date <= last:
        raise ApiError(
            422, "outside_booking_window", "You can only book today and the next 6 days."
        )

    # 4. Lab closed on that date (rule 5.10).
    if common.is_lab_closed(session, lab.id, local_date):
        raise ApiError(409, "lab_closed", "This lab is closed on that day.")

    # 5. Same slot already booked by the caller (rule 5.7). Active bookings only,
    #    matching the partial unique index on (user_id, slot_id) WHERE cancelled_at IS NULL.
    already = session.scalar(
        select(BookingRow.id).where(
            BookingRow.user_id == user.id,
            BookingRow.slot_id == slot.id,
            BookingRow.cancelled_at.is_(None),
        )
    )
    if already is not None:
        raise ApiError(409, "already_booked", "You have already booked this slot.")

    # 6. Another lab's slot at the same time (rule 5.7).
    overlap = session.scalar(
        select(BookingRow.id)
        .join(Slot, Slot.id == BookingRow.slot_id)
        .where(
            BookingRow.user_id == user.id,
            BookingRow.cancelled_at.is_(None),
            Slot.start_time == slot.start_time,
            Slot.id != slot.id,
        )
        .limit(1)
    )
    if overlap is not None:
        raise ApiError(
            409, "overlapping_booking", "You already have a booking at this time in another lab."
        )

    # 7. Two active bookings that local date, all labs, started or not (rule 5.6).
    day_start, day_end = clock.local_day_bounds_utc(local_date)
    on_that_day = session.scalar(
        select(func.count())
        .select_from(BookingRow)
        .join(Slot, Slot.id == BookingRow.slot_id)
        .where(
            BookingRow.user_id == user.id,
            BookingRow.cancelled_at.is_(None),
            Slot.start_time >= day_start,
            Slot.start_time < day_end,
        )
    )
    if (on_that_day or 0) >= MAX_BOOKINGS_PER_DAY:
        raise ApiError(409, "daily_limit_reached", "You already have 2 bookings on this day.")

    # 8. No free seat (rules 5.4, 5.8).
    if common.active_booking_count(session, slot.id) >= lab.seats:
        raise ApiError(409, "slot_full", "This slot is full.")

    booking = BookingRow(user_id=user.id, slot_id=slot.id, created_at=now)
    session.add(booking)
    try:
        session.commit()
    except IntegrityError:
        # A concurrent request inserted the same active (user, slot) pair after check 5.
        session.rollback()
        raise ApiError(409, "already_booked", "You have already booked this slot.") from None
    return to_schema(booking, slot, lab)


def cancel_booking(session: Session, user: User, booking_id: int) -> Booking:
    """Cancel the caller's own booking before it starts (rule 5.9), in the contract's order."""
    now = clock.now_utc()

    # 1. Missing booking.
    booking = session.get(BookingRow, booking_id)
    if booking is None:
        raise ApiError(404, "booking_not_found", "Booking not found.")

    # 2. Someone else's booking; admins included (US-5).
    if booking.user_id != user.id:
        raise ApiError(403, "not_your_booking", "You can only cancel your own bookings.")

    # 3. Already cancelled.
    if booking.cancelled_at is not None:
        raise ApiError(409, "booking_already_cancelled", "This booking is already cancelled.")

    # 4. Slot has started.
    slot = session.get(Slot, booking.slot_id)
    lab = session.get(Lab, slot.lab_id)
    if slot.start_time <= now:
        raise ApiError(
            409,
            "booking_already_started",
            "This booking has already started and can't be cancelled.",
        )

    booking.cancelled_at = now
    session.commit()
    return to_schema(booking, slot, lab)


def list_my_bookings(session: Session, user: User) -> list[Booking]:
    """The caller's bookings whose slot has not ended, active and cancelled (US-4)."""
    now = clock.now_utc()
    rows = session.execute(
        select(BookingRow, Slot, Lab)
        .join(Slot, Slot.id == BookingRow.slot_id)
        .join(Lab, Lab.id == Slot.lab_id)
        .where(BookingRow.user_id == user.id, Slot.end_time > now)
        .order_by(Slot.start_time, BookingRow.created_at, BookingRow.id)
    ).all()
    return [to_schema(booking, slot, lab) for booking, slot, lab in rows]
