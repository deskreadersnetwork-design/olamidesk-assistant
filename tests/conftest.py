"""
conftest.py — Shared pytest fixtures.

Tests use an in-memory SQLite database instead of PostgreSQL.
Why: tests must not require a real PostgreSQL server or real credentials.
SQLAlchemy's ORM code is the same; only the connection string differs.
"""

import sys
from pathlib import Path

# Ensure the project root is importable when running `pytest` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import database
from models import Base


@pytest.fixture()
def memory_db(monkeypatch):
    """
    Provide a fresh in-memory SQLite DB for one test.
    Monkeypatches database.init_db to use SQLite instead of PostgreSQL.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    # Replace module-level engine/session factory used by get_session().
    monkeypatch.setattr(database, "_engine", engine, raising=False)
    monkeypatch.setattr(database, "_SessionLocal", SessionLocal, raising=False)

    yield

    engine.dispose()
