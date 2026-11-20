from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import Base, get_session, make_engine
from app.models import Booking, Lab, LabClosure, Slot, User



BACKEND_DIR = Path(__file__).resolve().parents[2]
TABLES = {"users", "labs", "slots", "bookings", "lab_closures"}
START = datetime(2026, 11, 23, 6, 0)  # naive UTC


# -- helpers ----------------------------------------------------------------


def make_user(session, student_number="20260001"):
    user = User(student_number=student_number, password_hash="x")
    session.add(user)
    session.commit()
    return user


def make_lab(session, name="Lab A", seats=30):
    lab = Lab(name=name, seats=seats)
    session.add(lab)
    session.commit()
    return lab


def make_slot(session, lab, start=START):
    slot = Slot(lab_id=lab.id, start_time=start, end_time=start + timedelta(hours=1))
    session.add(slot)
    session.commit()
    return slot


def alembic_config(db_url: str, monkeypatch) -> Config:
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


# -- migration --------------------------------------------------------------


def test_migration_up_and_down(db_url, monkeypatch):
    cfg = alembic_config(db_url, monkeypatch)
    engine = make_engine(db_url)

    command.upgrade(cfg, "head")
    inspector = inspect(engine)
    assert TABLES <= set(inspector.get_table_names())
    with engine.connect() as conn:
        index_sql = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE name = 'uq_bookings_active_user_slot'")
        ).scalar_one()
    assert "UNIQUE" in index_sql.upper()
    assert "cancelled_at IS NULL" in index_sql

    command.downgrade(cfg, "base")
    remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert remaining == set()
    with engine.connect() as conn:
        leftover = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'")
        ).all()
    assert leftover == []
    engine.dispose()


def test_migration_matches_models(db_url, monkeypatch):
    cfg = alembic_config(db_url, monkeypatch)
    command.upgrade(cfg, "head")
    engine = make_engine(db_url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == []


def test_migrated_database_enforces_constraints(db_url, monkeypatch):
    """The migration (not only create_all) carries the constraints."""
    cfg = alembic_config(db_url, monkeypatch)
    command.upgrade(cfg, "head")
    engine = make_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO labs (name, seats) VALUES ('Lab A', 30)"))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO labs (name, seats) VALUES ('Lab B', 0)"))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO labs (name, seats) VALUES ('Lab A', 5)"))
    engine.dispose()


# -- bookings ---------------------------------------------------------------


def test_second_active_booking_for_same_user_and_slot_is_rejected(db_session):
    user = make_user(db_session)
    slot = make_slot(db_session, make_lab(db_session))
    db_session.add(Booking(slot_id=slot.id, user_id=user.id))
    db_session.commit()

    db_session.add(Booking(slot_id=slot.id, user_id=user.id))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_rebooking_is_allowed_after_cancelling(db_session):
    user = make_user(db_session)
    slot = make_slot(db_session, make_lab(db_session))
    first = Booking(slot_id=slot.id, user_id=user.id)
    db_session.add(first)
    db_session.commit()

    first.cancelled_at = datetime(2026, 11, 22, 10, 0)
    db_session.commit()

    db_session.add(Booking(slot_id=slot.id, user_id=user.id))
    db_session.commit()  # no error

    # ...but a third active one is rejected again, and cancelled rows can pile up.
    db_session.add(Booking(slot_id=slot.id, user_id=user.id))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_different_users_can_book_same_slot(db_session):
    slot = make_slot(db_session, make_lab(db_session))
    for number in ("1", "2"):
        user = make_user(db_session, number)
        db_session.add(Booking(slot_id=slot.id, user_id=user.id))
    db_session.commit()


def test_booking_defaults(db_session):
    user = make_user(db_session)
    slot = make_slot(db_session, make_lab(db_session))
    booking = Booking(slot_id=slot.id, user_id=user.id)
    db_session.add(booking)
    db_session.commit()
    assert booking.cancelled_at is None
    assert isinstance(booking.created_at, datetime)
    assert booking.created_at.tzinfo is None


# -- closures ---------------------------------------------------------------


def test_duplicate_lab_and_date_closure_is_rejected(db_session):
    lab = make_lab(db_session)
    db_session.add(LabClosure(lab_id=lab.id, date=date(2026, 12, 25)))
    db_session.commit()

    db_session.add(LabClosure(lab_id=lab.id, date=date(2026, 12, 25)))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_same_date_for_another_lab_is_allowed_and_date_is_a_date(db_session):
    a = make_lab(db_session, "Lab A")
    b = make_lab(db_session, "Lab B")
    db_session.add_all(
        [
            LabClosure(lab_id=a.id, date=date(2026, 12, 25)),
            LabClosure(lab_id=b.id, date=date(2026, 12, 25)),
        ]
    )
    db_session.commit()
    stored = db_session.query(LabClosure).first()
    assert type(stored.date) is date


# -- slots ------------------------------------------------------------------


def test_duplicate_lab_and_start_time_slot_is_rejected(db_session):
    lab = make_lab(db_session)
    make_slot(db_session, lab)
    with pytest.raises(IntegrityError):
        make_slot(db_session, lab)


def test_same_start_time_in_another_lab_is_allowed(db_session):
    make_slot(db_session, make_lab(db_session, "Lab A"))
    make_slot(db_session, make_lab(db_session, "Lab B"))


def test_slot_end_must_be_after_start(db_session):
    lab = make_lab(db_session)
    db_session.add(Slot(lab_id=lab.id, start_time=START, end_time=START))
    with pytest.raises(IntegrityError):
        db_session.commit()


# -- users and labs ---------------------------------------------------------


def test_duplicate_student_number_is_rejected(db_session):
    make_user(db_session, "20260001")
    with pytest.raises(IntegrityError):
        make_user(db_session, "20260001")


def test_user_defaults(db_session):
    user = make_user(db_session)
    assert user.is_admin is False
    assert user.created_at.tzinfo is None


def test_zero_seats_is_rejected(db_session):
    db_session.add(Lab(name="Lab A", seats=0))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_negative_seats_is_rejected(db_session):
    db_session.add(Lab(name="Lab A", seats=-1))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_duplicate_lab_name_is_rejected(db_session):
    make_lab(db_session, "Lab A")
    with pytest.raises(IntegrityError):
        make_lab(db_session, "Lab A")


def test_lab_is_active_by_default(db_session):
    assert make_lab(db_session).is_active is True


# -- foreign keys and session ------------------------------------------------


def test_foreign_keys_are_enforced(db_session):
    db_session.add(Slot(lab_id=999, start_time=START, end_time=START + timedelta(hours=1)))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(Booking(slot_id=999, user_id=999))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(LabClosure(lab_id=999, date=date(2026, 12, 25)))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_foreign_key_pragma_is_on_for_every_connection(db_engine):
    for _ in range(2):
        with db_engine.connect() as conn:
            assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_get_session_yields_and_closes():
    gen = get_session()
    session = next(gen)
    assert session.execute(text("SELECT 1")).scalar_one() == 1
    with pytest.raises(StopIteration):
        next(gen)
