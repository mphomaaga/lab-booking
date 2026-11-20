"""Booking schemas."""

from enum import StrEnum

from app.schemas.common import ApiModel, RequestModel, UtcDateTime
from app.schemas.labs import LabRef, SlotRef


class BookingStatus(StrEnum):
    active = "active"
    cancelled = "cancelled"


class CreateBookingRequest(RequestModel):
    slot_id: int


class Booking(ApiModel):
    id: int
    status: BookingStatus
    created_at: UtcDateTime
    cancelled_at: UtcDateTime | None
    cancellable: bool
    lab: LabRef
    slot: SlotRef
