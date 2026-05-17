"""SQLAlchemy engine factories.

Two database surfaces:
  - SQL Server (UTRBDMSNET) for wells, surveys, APD, construction.
  - SQLite (PLSS plats, casing strengths, location reference) for read-only
    geospatial reference data.
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator
from urllib.parse import quote_plus

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from etools.config import settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """SQL Server engine. Cached — one per process."""
    odbc = settings.db.odbc_connection_string()
    url = f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}"
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=settings.db.pool_recycle,
        future=True,
    )


@lru_cache(maxsize=8)
def get_sqlite_engine(path: str | Path) -> Engine:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"SQLite database not found: {path}")
    return create_engine(f"sqlite:///{path.as_posix()}", future=True)


_session_factory: sessionmaker[Session] | None = None


def _factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


@contextmanager
def sql_session() -> Iterator[Session]:
    """Transactional session context for writes; reads can use the engine directly."""
    session = _factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
