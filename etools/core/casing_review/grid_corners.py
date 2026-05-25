"""Grid-corner reference data backed by SQLite.

Replaces the Excel ``Grid Numbers`` 2,672-row reference table the SHL /
BHL Section sheets use to convert (corner, footage) into a real-world
coordinate. The Section-sheet formulas read this table 8× per row, so
we hand them a fully populated copy at template-fill time.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "grid_numbers.sqlite"


@dataclass(frozen=True)
class GridCorner:
    section: int
    township: int
    township_dir: int  # 1=N 2=S
    range: int
    range_dir: int  # 1=E 2=W
    baseline: int  # 1=Salt Lake 2=Uintah
    side: str
    length_ft: float | None
    degrees: int | None
    minutes: int | None
    seconds: int | None
    alignment: int | None
    north_ref: str | None


class GridCornerCatalog:
    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path or _DB_PATH)
        if not self._path.exists():
            raise FileNotFoundError(
                f"Grid Numbers DB not found at {self._path}. Build with "
                "`python tools/build_grid_numbers_db.py`."
            )
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def section_corners(
        self,
        *,
        section: int,
        township: int,
        township_dir: int,
        range_: int,
        range_dir: int,
        baseline: int,
    ) -> list[GridCorner]:
        """Return every corner-segment row for the given PLSS section."""
        cur = self._conn.cursor()
        cur.execute(
            """SELECT * FROM grid_corner
               WHERE section = ? AND township = ? AND township_dir = ?
               AND range_ = ? AND range_dir = ? AND baseline = ?
               ORDER BY side""",
            (section, township, township_dir, range_, range_dir, baseline),
        )
        return [
            GridCorner(
                section=r["section"],
                township=r["township"],
                township_dir=r["township_dir"],
                range=r["range_"],
                range_dir=r["range_dir"],
                baseline=r["baseline"],
                side=r["side"],
                length_ft=r["length_ft"],
                degrees=r["degrees"],
                minutes=r["minutes"],
                seconds=r["seconds"],
                alignment=r["alignment"],
                north_ref=r["north_ref"],
            )
            for r in cur.fetchall()
        ]

    def export_all(self) -> list[tuple]:
        """Dump every row — used by the Excel writer to rewrite the
        Grid Numbers sheet with our authoritative data."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT section, township, township_dir, range_, range_dir, "
            "baseline, side, length_ft, degrees, minutes, seconds, "
            "alignment, north_ref FROM grid_corner ORDER BY rowid"
        )
        return cur.fetchall()


# Helpers for converting "N"/"S"/"E"/"W" and baseline names into the
# integer codes the schema stores.
def encode_township_dir(d: str | None) -> int:
    return 2 if (d or "").upper() == "S" else 1


def encode_range_dir(d: str | None) -> int:
    return 2 if (d or "").upper() == "W" else 1


def encode_baseline(m: str | None) -> int:
    """Meridian letter → baseline code. U = Uintah → 2, S = Salt Lake → 1."""
    return 2 if (m or "").upper() == "U" else 1
