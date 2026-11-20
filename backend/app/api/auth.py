"""`POST /auth/login` and `GET /me` (US-1)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_session
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.auth import User as UserSchema
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=LoginResponse, operation_id="login")
def login(body: LoginRequest, session: Annotated[Session, Depends(get_session)]) -> LoginResponse:
    return auth_service.login(session, body.student_number, body.password)


@router.get("/me", response_model=UserSchema, operation_id="getMe")
def get_me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user
