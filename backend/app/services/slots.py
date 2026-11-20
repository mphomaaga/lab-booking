"""Lab listing and slot availability for one day (US-2; rules 5.1, 5.2, 5.4, 5.5, 5.8, 5.10, 5.12)."""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import ApiError
from app.models import Booking, Lab, Slot
from app.schemas.labs import DaySlots, DayStatus
from app.schemas.labs import Lab as LabSchema
from app.schemas.labs import Slot as SlotSchema
from app.services.common import get_active_lab_or_404, is_lab_closed

SLOT_LENGTH = timedelta(hours=1)  # rule 5.2


def list_active_labs(session: Session) -> list[Lab]:
    """Active labs ordered by name (rule 5.12)."""
    return list(session.scalars(select(Lab).where(Lab.is_active.is_(True)).order_by(Lab.name, Lab.id)))


def ensure_slots(session: Session, lab: Lab, local_date: date) -> list[Slot]:
    """The ten slots of ``lab`` on ``local_date``, created if missing, ordered by start time.

    Creation relies on ``uq_slots_lab_start`` (INSERT ... ON CONFLICT DO NOTHING), so it
    is idempotent, also when two requests arrive at once.
    """
    starts = clock.slot_starts_utc(local_date)
    if not starts:
        return []
    session.execute(
        sqlite_insert(Slot)
        .values([{"lab_id": lab.id, "start_time": s, "end_time": s + SLOT_LENGTH} for s in starts])
        .on_conflict_do_nothing(index_elements=["lab_id", "start_time"])
    )
    session.commit()
    stmt = select(Slot).where(Slot.lab_id == lab.id, Slot.start_time.in_(starts)).order_by(Slot.start_time)
    return list(session.scalars(stmt))


def _active_counts(session: Session, slot_ids: list[int]) -> dict[int, int]:
    """Active (not cancelled) booking count per slot id (rules 5.4, 5.7)."""
    if not slot_ids:
        return {}
    stmt = (
        select(Booking.slot_id, func.count())
        .where(Booking.slot_id.in_(slot_ids), Booking.cancelled_at.is_(None))
        .group_by(Booking.slot_id)
    )
    return {slot_id: n for slot_id, n in session.execute(stmt)}


def get_day_slots(session: Session, lab_id: int, local_date: date) -> DaySlots:
    """Apply the contract's checks in order and build the ``DaySlots`` response."""
    lab = get_active_lab_or_404(session, lab_id)

    first, last = clock.booking_window()
    if not first <= local_date <= last:
        raise ApiError(422, "date_out_of_window", "You can only view today and the next 6 days.")

    lab_schema = LabSchema.model_validate(lab)

    if clock.is_weekend(local_date):
        return DaySlots(lab=lab_schema, date=local_date, day_status=DayStatus.weekend, slots=[])
    if is_lab_closed(session, lab.id, local_date):
        return DaySlots(lab=lab_schema, date=local_date, day_status=DayStatus.closed, slots=[])

    slots = ensure_slots(session, lab, local_date)
    counts = _active_counts(session, [s.id for s in slots])
    now = clock.now_utc()
    items = []
    for slot in slots:
        free = max(lab.seats - counts.get(slot.id, 0), 0)
        items.append(
            SlotSchema(
                id=slot.id,
                start_time=slot.start_time,
                end_time=slot.end_time,
                seats=lab.seats,
                free_seats=free,
                bookable=slot.start_time > now and free > 0,
            )
        )
    return DaySlots(lab=lab_schema, date=local_date, day_status=DayStatus.open, slots=items)
