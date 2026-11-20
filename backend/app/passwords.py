"""Password hashing with bcrypt (US-1)."""

import bcrypt


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of ``plain`` as a string (fits VARCHAR(255))."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """True if ``plain`` matches ``hashed``; False for a wrong password or a malformed hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False
