"""Dependencies every guarded endpoint uses."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import InvalidTokenError, decode_access_token
from app.db import get_session
from app.models import User

# auto_error is off so a missing header gives our own 401 `not_authenticated` body.
bearer_scheme = HTTPBearer(auto_error=False)


def _not_authenticated() -> ApiError:
    return ApiError(401, "not_authenticated", "Please log in.")


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    """The logged-in user, or 401 `not_authenticated`."""
    if credentials is None:
        raise _not_authenticated()
    try:
        claims = decode_access_token(credentials.credentials)
        user_id = int(claims["sub"])
    except (InvalidTokenError, ValueError, TypeError):
        raise _not_authenticated() from None
    user = session.get(User, user_id)
    if user is None:
        raise _not_authenticated()
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    """The logged-in user if they are an admin (read from the database), else 403."""
    if not user.is_admin:
        raise ApiError(403, "admin_required", "Admins only.")
    return user
