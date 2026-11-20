"""Admin schemas."""

import datetime as dt

from pydantic import Field

from app.schemas.auth import UserRef
from app.schemas.bookings import BookingStatus
from app.schemas.common import ApiModel, RequestModel, UtcDateTime
from app.schemas.labs import Lab, SlotRef


class AdminBooking(ApiModel):
    id: int
    status: BookingStatus
    created_at: UtcDateTime
    cancelled_at: UtcDateTime | None
    slot: SlotRef
    user: UserRef


class AdminDayBookings(ApiModel):
    lab: Lab
    date: dt.date
    closed: bool
    bookings: list[AdminBooking]


class CreateClosureRequest(RequestModel):
    date: dt.date
    """Calendar date in Africa/Johannesburg, today or later."""


class ClosureCreated(ApiModel):
    id: int
    lab_id: int
    date: dt.date
    created_at: UtcDateTime
    cancelled_booking_count: int = Field(ge=0)
