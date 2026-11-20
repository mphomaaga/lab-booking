"""Login (US-1, rules 5.13, 5.14)."""

from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import create_access_token
from app.models import User
from app.passwords import hash_password, verify_password
from app.schemas.auth import LoginResponse
from app.schemas.auth import User as UserSchema

INVALID_CREDENTIALS_MESSAGE = "Student number or password is incorrect."


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A real bcrypt hash to check against when the student number is unknown.

    Doing the same bcrypt work for an unknown student number as for a wrong password
    keeps the two cases from being told apart by response time.
    """
    return hash_password("not-a-real-password")


def login(session: Session, student_number: str, password: str) -> LoginResponse:
    """Check the credentials and return a token with its owner.

    The student number is matched exactly as stored: no trimming, no case change.
    An unknown number and a wrong password give the identical 401.
    """
    user = session.scalar(select(User).where(User.student_number == student_number))
    # Always run one bcrypt check, whether or not the user exists.
    password_ok = verify_password(password, user.password_hash if user else _dummy_hash())
    if user is None or not password_ok:
        raise ApiError(401, "invalid_credentials", INVALID_CREDENTIALS_MESSAGE)

    token, expires_at = create_access_token(user.id)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_at=expires_at,
        user=UserSchema.model_validate(user),
    )
