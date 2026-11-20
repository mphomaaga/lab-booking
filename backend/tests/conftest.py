"""Shared fixtures: an isolated database per test, the API client, a frozen clock and factories.

JWT_SECRET is set here, at module top level and before anything imports `app`, because
`app.core.config.get_settings` is cached and `app.main` reads settings at import time.
A per-test `monkeypatch.setenv` would therefore be too late. Importing `app` is also
done lazily inside fixtures so that the db tests never load `app.main`.
"""

import os

os.environ["JWT_SECRET"] = "test-secret-for-lab-booking-tests-0123456789"

from collections.abc import Callable, Iterator  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402
from itertools import count  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

import app.models  # noqa: E402, F401  (registers the tables on Base.metadata)
from app.db import Base, get_session, make_engine  # noqa: E402
from app.models import Booking, Lab, LabClosure, Slot, User  # noqa: E402

DEFAULT_PASSWORD = "password"
DEFAULT_START = datetime(2026, 1, 5, 8, 0)  # naive UTC, a Monday


@pytest.fixture
def app_engine(tmp_path: Path) -> Iterator[Engine]:
    """Engine on a fresh SQLite file whose tables come from `Base.metadata`."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(app_engine: Engine) -> Iterator[Session]:
    """A session for arranging and checking data in a test."""
    db = sessionmaker(bind=app_engine, autoflush=False, expire_on_commit=False)()
    yield db
    db.close()


@pytest.fixture
def client(app_engine: Engine) -> Iterator[TestClient]:
    """TestClient whose requests use the test database (a new session per request)."""
    from app.main import app

    factory = sessionmaker(bind=app_engine, autoflush=False, expire_on_commit=False)

    def override_get_session() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_session, None)


class FrozenClock:
    """The frozen "now" (naive UTC). Change it with `set` or `advance`."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def set(self, now: datetime) -> None:
        self.now = now

    def advance(self, **kwargs: float) -> datetime:
        self.now += timedelta(**kwargs)
        return self.now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def frozen_now(monkeypatch: pytest.MonkeyPatch) -> FrozenClock:
    """Patch `app.core.clock.now_utc` to return a fixed time (default 2026-01-05 08:00 UTC)."""
    from app.core import clock

    frozen = FrozenClock(DEFAULT_START)
    monkeypatch.setattr(clock, "now_utc", frozen)
    return frozen


_default_hash: str | None = None


def _hash(password: str) -> str:
    """bcrypt is slow, so hash the default password only once per test run."""
    global _default_hash
    from app.passwords import hash_password

    if password != DEFAULT_PASSWORD:
        return hash_password(password)
    if _default_hash is None:
        _default_hash = hash_password(password)
    return _default_hash


@pytest.fixture
def user_factory(session: Session) -> Callable[..., User]:
    """`user_factory(student_number=None, password="password", is_admin=False)`."""
    numbers = count(1)

    def make(
        student_number: str | None = None,
        password: str = DEFAULT_PASSWORD,
        is_admin: bool = False,
    ) -> User:
        user = User(
            student_number=student_number or f"2026{next(numbers):04d}",
            password_hash=_hash(password),
            is_admin=is_admin,
        )
        session.add(user)
        session.commit()
        return user

    return make


@pytest.fixture
def admin_factory(user_factory: Callable[..., User]) -> Callable[..., User]:
    """`admin_factory(student_number=None, password="password")` makes an admin."""

    def make(student_number: str | None = None, password: str = DEFAULT_PASSWORD) -> User:
        return user_factory(student_number=student_number, password=password, is_admin=True)

    return make


@pytest.fixture
def auth_headers() -> Callable[[User], dict[str, str]]:
    """`auth_headers(user)` returns the Authorization header for a valid token."""
    from app.core.security import create_access_token

    def make(user: User) -> dict[str, str]:
        token, _ = create_access_token(user.id)
        return {"Authorization": f"Bearer {token}"}

    return make


@pytest.fixture
def lab_factory(session: Session) -> Callable[..., Lab]:
    """`lab_factory(name=None, seats=30, is_active=True)`."""
    numbers = count(1)

    def make(name: str | None = None, seats: int = 30, is_active: bool = True) -> Lab:
        lab = Lab(name=name or f"Lab {next(numbers)}", seats=seats, is_active=is_active)
        session.add(lab)
        session.commit()
        return lab

    return make


@pytest.fixture
def slot_factory(session: Session, lab_factory: Callable[..., Lab]) -> Callable[..., Slot]:
    """`slot_factory(lab=None, start_time=None, end_time=None)`; one hour long by default."""

    def make(
        lab: Lab | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> Slot:
        lab = lab or lab_factory()
        start = start_time or DEFAULT_START
        slot = Slot(
            lab_id=lab.id,
            start_time=start,
            end_time=end_time or start + timedelta(hours=1),
        )
        session.add(slot)
        session.commit()
        return slot

    return make


@pytest.fixture
def booking_factory(
    session: Session,
    user_factory: Callable[..., User],
    slot_factory: Callable[..., Slot],
) -> Callable[..., Booking]:
    """`booking_factory(user=None, slot=None, cancelled=False, created_at=None)`.

    A booking is active while `cancelled_at` is NULL; `cancelled=True` sets it
    (to `cancelled_at` if given, otherwise to the booking's creation time).
    """

    def make(
        user: User | None = None,
        slot: Slot | None = None,
        cancelled: bool = False,
        created_at: datetime | None = None,
        cancelled_at: datetime | None = None,
    ) -> Booking:
        user = user or user_factory()
        slot = slot or slot_factory()
        created = created_at or DEFAULT_START
        booking = Booking(
            user_id=user.id,
            slot_id=slot.id,
            created_at=created,
            cancelled_at=(cancelled_at or created) if cancelled else None,
        )
        session.add(booking)
        session.commit()
        return booking

    return make


@pytest.fixture
def closure_factory(session: Session, lab_factory: Callable[..., Lab]) -> Callable[..., LabClosure]:
    """`closure_factory(lab=None, date=None)`; the date defaults to 2026-01-05."""

    def make(lab: Lab | None = None, date: date | None = None) -> LabClosure:  # noqa: F811
        lab = lab or lab_factory()
        closure = LabClosure(lab_id=lab.id, date=date or DEFAULT_START.date())
        session.add(closure)
        session.commit()
        return closure

    return make
