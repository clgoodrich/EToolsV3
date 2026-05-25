"""Build an in-app SQLite catalog of casing-string strength properties.

Source: the Casing Strengths sheet of any reference Casing Review workbook
(it ships pre-populated with API Spec 5C3 strength tables for every common
OD/weight/grade/connection-type combination).

Schema (etools/data/casing_catalog.sqlite, table casing_strength):
    od_in            REAL    Outer diameter (in)
    weight_ppf       REAL    Nominal weight (lb/ft)
    grade            TEXT    e.g. "J-55", "P-110", "Q-125"
    collapse_psi     REAL    Collapse pressure rating
    burst_psi        REAL    Internal yield pressure at minimum yield (psi)
    collar           TEXT    Joint type / connection: BTC, STC, LTC, …
    joint_klbs       REAL    Joint strength (1000 lbs)
    body_klbs        REAL    Body yield strength (1000 lbs)
    wall_in          REAL    Wall thickness (in)
    id_in            REAL    Inner diameter (in)
    drift_api_in     REAL    API drift diameter (in)
    drift_sd_in      REAL    Special-drift diameter (in, may be NULL)

Usage:
    .venv/Scripts/python tools/build_casing_catalog.py [path/to/source.xlsx]
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SRC = REPO / "tests" / "Casing Review_43013537270000_Myton City UT 16-23 3-2-25-36-7H.xlsx"
DEST = REPO / "etools" / "data" / "casing_catalog.sqlite"


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC)
    if not src.exists():
        sys.exit(f"Source workbook not found: {src}")
    DEST.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.load_workbook(src, data_only=False)
    ws = wb["Casing Strengths"]

    rows = []
    # Data starts at row 8 (rows 1-7 are headers). Columns A-P.
    for r in ws.iter_rows(min_row=8, values_only=True):
        od, wt, grade, collapse, burst, _, _, _, collar, joint, _, body, wall, idia, drift_api, drift_sd = r[:16]
        if od is None or wt is None or grade is None:
            continue
        rows.append(
            (
                _f(od), _f(wt), _s(grade),
                _f(collapse), _f(burst),
                _s(collar), _f(joint), _f(body),
                _f(wall), _f(idia), _f(drift_api), _f(drift_sd),
            )
        )

    if DEST.exists():
        DEST.unlink()
    conn = sqlite3.connect(DEST)
    try:
        cur = conn.cursor()
        cur.execute(
            """CREATE TABLE casing_strength (
                od_in          REAL,
                weight_ppf     REAL,
                grade          TEXT,
                collapse_psi   REAL,
                burst_psi      REAL,
                collar         TEXT,
                joint_klbs     REAL,
                body_klbs      REAL,
                wall_in        REAL,
                id_in          REAL,
                drift_api_in   REAL,
                drift_sd_in    REAL
            )"""
        )
        cur.execute(
            "CREATE INDEX idx_lookup ON casing_strength "
            "(od_in, weight_ppf, grade, collar)"
        )
        cur.executemany(
            "INSERT INTO casing_strength VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Wrote {len(rows)} casing-strength rows -> {DEST}")


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
