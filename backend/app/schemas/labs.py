"""Lab and slot schemas."""

import datetime as dt
from enum import StrEnum

from pydantic import Field

from app.schemas.common import ApiModel, UtcDateTime


class DayStatus(StrEnum):
    open = "open"
    closed = "closed"
    weekend = "weekend"


class Lab(ApiModel):
    id: int
    name: str
    seats: int = Field(ge=1)


class LabRef(ApiModel):
    id: int
    name: str


class Slot(ApiModel):
    id: int
    start_time: UtcDateTime
    end_time: UtcDateTime
    seats: int
    free_seats: int = Field(ge=0)
    bookable: bool


class SlotRef(ApiModel):
    id: int
    start_time: UtcDateTime
    end_time: UtcDateTime


class DaySlots(ApiModel):
    lab: Lab
    date: dt.date
    day_status: DayStatus
    slots: list[Slot]
