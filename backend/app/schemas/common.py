"""Shared building blocks: the error envelope, error codes and the UTC datetime type."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer


def format_utc(value: datetime) -> str:
    """Format an instant as ``YYYY-MM-DDTHH:MM:SSZ`` (UTC, whole seconds).

    Naive datetimes are taken to be UTC (the database stores naive UTC); aware
    datetimes are converted to UTC first. Sub-second precision is dropped
    (rule 5.15, contract "Conventions").
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


UtcDateTime = Annotated[
    datetime,
    PlainSerializer(format_utc, return_type=str, when_used="always"),
]
"""A datetime that always serialises as ``2026-11-19T06:00:00Z``."""


class ApiModel(BaseModel):
    """Base for response models; can be built from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class RequestModel(BaseModel):
    """Base for request models; unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class ErrorCode(StrEnum):
    not_authenticated = "not_authenticated"
    invalid_credentials = "invalid_credentials"
    admin_required = "admin_required"
    not_your_booking = "not_your_booking"
    lab_not_found = "lab_not_found"
    slot_not_found = "slot_not_found"
    booking_not_found = "booking_not_found"
    not_found = "not_found"
    lab_closed = "lab_closed"
    already_booked = "already_booked"
    overlapping_booking = "overlapping_booking"
    daily_limit_reached = "daily_limit_reached"
    slot_full = "slot_full"
    booking_already_cancelled = "booking_already_cancelled"
    booking_already_started = "booking_already_started"
    closure_exists = "closure_exists"
    validation_error = "validation_error"
    date_out_of_window = "date_out_of_window"
    slot_in_past = "slot_in_past"
    outside_booking_window = "outside_booking_window"
    closure_date_in_past = "closure_date_in_past"
    internal_error = "internal_error"


class ErrorDetail(ApiModel):
    loc: list[str | int]
    msg: str


class ErrorBody(ApiModel):
    code: ErrorCode
    message: str
    details: list[ErrorDetail] | None = None
    """Only for ``validation_error``."""


class Error(ApiModel):
    error: ErrorBody
