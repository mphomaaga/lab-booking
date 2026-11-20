from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db import get_session
from app.schemas import AdminDayBookings
from app.services import admin_bookings as service

router = APIRouter()


@router.get(
    "/admin/bookings",
    response_model=AdminDayBookings,
    tags=["admin"],
    operation_id="adminListBookings",
    dependencies=[Depends(require_admin)],
)
def admin_list_bookings(
    session: Annotated[Session, Depends(get_session)],
    # Taken as raw text and parsed in the service: the contract checks the lab (404)
    # before the parameters are validated (422).
    lab_id: Annotated[str | None, Query()] = None,
    date: Annotated[str | None, Query()] = None,
) -> AdminDayBookings:
    return service.list_day_bookings(session, lab_id, date)
