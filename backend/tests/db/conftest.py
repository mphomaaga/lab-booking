"""Fixtures for the db tests. Every test gets its own temporary SQLite database."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  (registers the tables)
from app.db import Base, make_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def db_engine(db_url: str) -> Iterator[Engine]:
    """Engine on a fresh database whose tables come from ``Base.metadata``."""
    engine = make_engine(db_url)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()
