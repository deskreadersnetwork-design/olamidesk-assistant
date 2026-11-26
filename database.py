"""
database.py — Database engine, session factory, and schema bootstrap.

- Creates ONE engine (connection pool) for the whole app.
- Provides `get_session()` as a context manager.
- `init_db()` creates tables if they don't exist (safe to call repeatedly).
"""

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from models import Base

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def init_db(database_url: str) -> None:
    """
    Initialize the engine and session factory, then create tables.
    Called once at startup from main.py.
    """
    global _engine, _SessionLocal

    # Railway gives URLs starting with postgres://; SQLAlchemy 2.x expects postgresql://.
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]

    # pool_pre_ping: test a connection before using it (Railway may recycle connections).
    # pool_recycle: recycle connections older than 5 minutes to avoid stale-socket errors.
    _engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        future=True,
    )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)

    Base.metadata.create_all(bind=_engine)
    logger.info("Database initialized and tables ensured.")


@contextmanager
def get_session() -> Iterator[Session]:
    """
    Context manager yielding a SQLAlchemy session.
    Commits on success, rolls back on error, always closes.
    """
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine() -> None:
    """Close all pooled connections (called on graceful shutdown)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        logger.info("Database engine disposed.")
