"""`GET /labs` and `GET /labs/{lab_id}/slots` (US-2)."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_session
from app.models import Lab
from app.schemas.labs import DaySlots
from app.schemas.labs import Lab as LabSchema
from app.services import slots as slots_service

router = APIRouter(tags=["labs"], dependencies=[Depends(get_current_user)])


@router.get("/labs", response_model=list[LabSchema], operation_id="listLabs")
def list_labs(session: Annotated[Session, Depends(get_session)]) -> list[Lab]:
    return slots_service.list_active_labs(session)


@router.get("/labs/{lab_id}/slots", response_model=DaySlots, operation_id="getLabSlots")
def get_lab_slots(
    lab_id: int,
    date: Annotated[dt.date, Query(description="Calendar date in Africa/Johannesburg")],
    session: Annotated[Session, Depends(get_session)],
) -> DaySlots:
    return slots_service.get_day_slots(session, lab_id, date)
