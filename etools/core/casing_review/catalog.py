"""Casing-strength catalog backed by a local SQLite database.

Replaces the spreadsheet's 1,512-row ``Casing Strengths`` DGET lookup with
a typed Python API. The catalog is keyed on (OD, weight, grade, collar)
because the same OD+weight+grade can ship with multiple connection types
(STC vs BTC vs LTC, etc.) that yield different joint-strength values.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "casing_catalog.sqlite"


@dataclass(frozen=True)
class CasingStrength:
    od_in: float
    weight_ppf: float
    grade: str
    collar: str | None
    collapse_psi: float | None
    burst_psi: float | None
    joint_klbs: float | None  # 1000-lb
    body_klbs: float | None
    wall_in: float | None
    id_in: float | None
    drift_api_in: float | None
    drift_sd_in: float | None


class CasingCatalog:
    """Thin SQLite wrapper. One catalog per process; safe to share."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path or _CATALOG_PATH)
        if not self._path.exists():
            raise FileNotFoundError(
                f"Casing catalog DB not found at {self._path}. "
                "Build it with `python scripts/build_casing_catalog.py`."
            )
        # check_same_thread=False so we can pass the connection across
        # the NiceGUI / asyncio executor boundaries.
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def lookup(
        self,
        *,
        od_in: float,
        weight_ppf: float,
        grade: str,
        collar: str | None = None,
    ) -> CasingStrength | None:
        """Return the strength record for the requested string, or None.

        ``collar`` is optional — when omitted we return any matching row
        (useful when the APD only ships the grade without a connection).
        """
        cur = self._conn.cursor()
        if collar:
            cur.execute(
                "SELECT * FROM casing_strength "
                "WHERE ABS(od_in - ?) < 0.01 AND ABS(weight_ppf - ?) < 0.01 "
                "AND grade = ? AND collar = ? LIMIT 1",
                (od_in, weight_ppf, grade, collar),
            )
        else:
            cur.execute(
                "SELECT * FROM casing_strength "
                "WHERE ABS(od_in - ?) < 0.01 AND ABS(weight_ppf - ?) < 0.01 "
                "AND grade = ? LIMIT 1",
                (od_in, weight_ppf, grade),
            )
        row = cur.fetchone()
        if row is None:
            return None
        return CasingStrength(
            od_in=row["od_in"],
            weight_ppf=row["weight_ppf"],
            grade=row["grade"],
            collar=row["collar"],
            collapse_psi=row["collapse_psi"],
            burst_psi=row["burst_psi"],
            joint_klbs=row["joint_klbs"],
            body_klbs=row["body_klbs"],
            wall_in=row["wall_in"],
            id_in=row["id_in"],
            drift_api_in=row["drift_api_in"],
            drift_sd_in=row["drift_sd_in"],
        )

    def grades_for(self, od_in: float, weight_ppf: float) -> list[str]:
        """List grades available at the given OD + weight."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT DISTINCT grade FROM casing_strength "
            "WHERE ABS(od_in - ?) < 0.01 AND ABS(weight_ppf - ?) < 0.01 "
            "ORDER BY grade",
            (od_in, weight_ppf),
        )
        return [r[0] for r in cur.fetchall()]
