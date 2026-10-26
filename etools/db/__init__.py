"""Database access layer: the bundled read-only SQLite reference files."""

from etools.db.session import get_sqlite_engine

__all__ = ["get_sqlite_engine"]
