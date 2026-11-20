"""Lookups shared by several endpoint areas."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import Booking, Lab, LabClosure


def get_active_lab_or_404(session: Session, lab_id: int) -> Lab:
    """Return the lab, or raise 404 ``lab_not_found`` if it is missing or inactive (rule 5.12)."""
    lab = session.get(Lab, lab_id)
    if lab is None or not lab.is_active:
        raise ApiError(404, "lab_not_found", "Lab not found")
    return lab


def active_booking_count(session: Session, slot_id: int) -> int:
    """Number of bookings on the slot that are not cancelled."""
    stmt = (
        select(func.count())
        .select_from(Booking)
        .where(Booking.slot_id == slot_id, Booking.cancelled_at.is_(None))
    )
    return session.scalar(stmt) or 0


def is_lab_closed(session: Session, lab_id: int, local_date: date) -> bool:
    """True if the lab has a closure on this local date (rule 5.10)."""
    stmt = select(LabClosure.id).where(LabClosure.lab_id == lab_id, LabClosure.date == local_date)
    return session.scalar(stmt) is not None
