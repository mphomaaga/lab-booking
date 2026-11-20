"""`POST /bookings`, `DELETE /bookings/{booking_id}` and `GET /me/bookings` (US-3, US-4, US-5)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_session
from app.models import User
from app.schemas.bookings import Booking, CreateBookingRequest
from app.services import bookings as bookings_service

router = APIRouter(tags=["bookings"])


@router.post("/bookings", response_model=Booking, status_code=201, operation_id="createBooking")
def create_booking(
    body: CreateBookingRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Booking:
    return bookings_service.create_booking(session, user, body.slot_id)


@router.delete("/bookings/{booking_id}", response_model=Booking, operation_id="cancelBooking")
def cancel_booking(
    booking_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Booking:
    return bookings_service.cancel_booking(session, user, booking_id)


@router.get("/me/bookings", response_model=list[Booking], operation_id="listMyBookings")
def list_my_bookings(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[Booking]:
    return bookings_service.list_my_bookings(session, user)
