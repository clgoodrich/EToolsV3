"""SQLAlchemy engine factory for the bundled SQLite reference databases
(PLSS plats). ETools reads well data only from the PDFs themselves and these
local files; it has no server database connection.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine


@lru_cache(maxsize=8)
def get_sqlite_engine(path: str | Path) -> Engine:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"SQLite database not found: {path}")
    return create_engine(f"sqlite:///{path.as_posix()}", future=True)
