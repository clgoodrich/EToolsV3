"""Extract the Grid Numbers reference sheet into a SQLite DB.

Source: the Grid Numbers sheet of any reference Casing Review workbook —
2,674 rows of per-section corner data used by the SHL/BHL Section sheets
to convert footages-from-corner into UTM/State-Plane coordinates.

Schema (etools/data/grid_numbers.sqlite, table grid_corner):
    section          INTEGER   1-36
    township         INTEGER   township number (no direction)
    township_dir     INTEGER   2 = S, 1 = N
    range            INTEGER   range number (no direction)
    range_dir        INTEGER   2 = W, 1 = E
    baseline         INTEGER   2 = Uintah, 1 = Salt Lake
    side             TEXT      "West-Up1", "South-Right2", etc. — one row per corner segment
    length_ft        REAL      Corner segment length
    degrees          INTEGER   Bearing degrees
    minutes          INTEGER   Bearing minutes
    seconds          INTEGER   Bearing seconds
    alignment        INTEGER   1 = SE, 2 = NE, 3 = SW, 4 = NW
    north_ref        TEXT      "G" (Grid) or "T" (True)

Usage:
    .venv/Scripts/python scripts/build_grid_numbers_db.py [path/to/source.xlsx]
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SRC = (
    REPO / "tests" / "fixtures" / "reference" / "Casing Review_43013537270000_Myton City UT 16-23 3-2-25-36-7H.xlsx"
)
DEST = REPO / "etools" / "data" / "grid_numbers.sqlite"


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC)
    if not src.exists():
        sys.exit(f"Source workbook not found: {src}")
    DEST.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.load_workbook(src, data_only=False)
    ws = wb["Grid Numbers"]

    rows = []
    # Data starts at row 3 (rows 1-2 are headers).
    for r in ws.iter_rows(min_row=3, values_only=True):
        section, twp, twp_dir, rng, rng_dir, baseline, side, length, deg, mn, sec, align, north_ref = r[:13]
        if section is None or side is None:
            continue
        rows.append(
            (
                _i(section), _i(twp), _i(twp_dir), _i(rng), _i(rng_dir),
                _i(baseline), _s(side), _f(length), _i(deg), _i(mn),
                _i(sec), _i(align), _s(north_ref),
            )
        )

    if DEST.exists():
        DEST.unlink()
    conn = sqlite3.connect(DEST)
    try:
        cur = conn.cursor()
        cur.execute(
            """CREATE TABLE grid_corner (
                section        INTEGER,
                township       INTEGER,
                township_dir   INTEGER,
                range_         INTEGER,
                range_dir      INTEGER,
                baseline       INTEGER,
                side           TEXT,
                length_ft      REAL,
                degrees        INTEGER,
                minutes        INTEGER,
                seconds        INTEGER,
                alignment      INTEGER,
                north_ref      TEXT
            )"""
        )
        cur.execute(
            "CREATE INDEX idx_section ON grid_corner "
            "(section, township, township_dir, range_, range_dir, baseline)"
        )
        cur.executemany(
            "INSERT INTO grid_corner VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Wrote {len(rows)} grid-corner rows -> {DEST}")


def _i(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _f(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _s(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


if __name__ == "__main__":
    main()
