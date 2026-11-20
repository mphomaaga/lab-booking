"""JWT creation and decoding (HS256). Claims: `sub` (user id as a string), `iat`, `exp`.

Time comes from `app.core.clock` so tests can freeze it (rule 5.15). Expiry is
checked here against that clock rather than by PyJWT, which would use real time.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core import clock
from app.core.config import get_settings

ALGORITHM = "HS256"


class InvalidTokenError(Exception):
    """The token is malformed, wrongly signed, incomplete or expired."""


def _timestamp(moment: datetime) -> int:
    """Whole seconds since the epoch for a naive UTC datetime."""
    return int(moment.replace(tzinfo=UTC).timestamp())


def create_access_token(user_id: int) -> tuple[str, datetime]:
    """Return ``(token, expires_at)``; ``expires_at`` is naive UTC (rule 5.14)."""
    settings = get_settings()
    issued_at = clock.now_utc()
    expires_at = issued_at + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    claims = {
        "sub": str(user_id),
        "iat": _timestamp(issued_at),
        "exp": _timestamp(expires_at),
    }
    token = jwt.encode(claims, settings.JWT_SECRET, algorithm=ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    """Return the claims of a valid, unexpired token or raise ``InvalidTokenError``."""
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[ALGORITHM],
            options={
                "require": ["sub", "iat", "exp"],
                "verify_exp": False,
                "verify_iat": False,
            },
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    exp = claims["exp"]
    if isinstance(exp, bool) or not isinstance(exp, int | float):
        raise InvalidTokenError("Invalid exp claim.")
    if _timestamp(clock.now_utc()) >= exp:
        raise InvalidTokenError("Token has expired.")
    return claims
