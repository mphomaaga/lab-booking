"""Pydantic models mirroring ``docs/api.yaml``."""

from app.schemas.admin import (
    AdminBooking,
    AdminDayBookings,
    ClosureCreated,
    CreateClosureRequest,
)
from app.schemas.auth import LoginRequest, LoginResponse, User, UserRef
from app.schemas.bookings import Booking, BookingStatus, CreateBookingRequest
from app.schemas.common import (
    Error,
    ErrorBody,
    ErrorCode,
    ErrorDetail,
    UtcDateTime,
)
from app.schemas.labs import DaySlots, DayStatus, Lab, LabRef, Slot, SlotRef

__all__ = [
    "AdminBooking",
    "AdminDayBookings",
    "Booking",
    "BookingStatus",
    "ClosureCreated",
    "CreateBookingRequest",
    "CreateClosureRequest",
    "DaySlots",
    "DayStatus",
    "Error",
    "ErrorBody",
    "ErrorCode",
    "ErrorDetail",
    "Lab",
    "LabRef",
    "LoginRequest",
    "LoginResponse",
    "Slot",
    "SlotRef",
    "User",
    "UserRef",
    "UtcDateTime",
]
