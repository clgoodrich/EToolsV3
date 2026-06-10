"""Grid-corner reference data backed by SQLite.

Replaces the Excel ``Grid Numbers`` 2,672-row reference table the SHL /
BHL Section sheets use to convert (corner, footage) into a real-world
coordinate. The Section-sheet formulas read this table 8× per row, so
we hand them a fully populated copy at template-fill time.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "grid_numbers.sqlite"

_M_TO_FT = 3.280839895

# The 16 quarter-side names in clockwise order from the NW corner, grouped by
# boundary. Each boundary is split into 4 equal quarter-segments when we
# derive a section from its plat polygon. Matches SIDE_ORDER in sections.py.
_DERIVE_SIDE_GROUPS: tuple[tuple[str, tuple[str, str, str, str]], ...] = (
    ("North", ("North-Left2", "North-Left1", "North-Right1", "North-Right2")),
    ("East", ("East-Up2", "East-Up1", "East-Down1", "East-Down2")),
    ("South", ("South-Right2", "South-Right1", "South-Left1", "South-Left2")),
    ("West", ("West-Down2", "West-Down1", "West-Up1", "West-Up2")),
)


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
                "`python scripts/build_grid_numbers_db.py`."
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


def _bearing_to_dms_alignment(d_east: float, d_west_unused=None, *, d_north: float):
    """Convert a segment vector into (degrees, minutes, seconds, alignment).

    ``alignment`` is the surveyed quadrant code: 1=SE, 2=NE, 3=SW, 4=NW.
    The DMS magnitude is the acute angle of the line from the N–S axis,
    matching the Grid Numbers convention (a near-E/W boundary reads
    ``89°…`` in the NE quadrant; a near-N/S boundary reads ``0–1°`` in
    the SE/NW quadrant). Validated against known sections to within a few
    arc-minutes.
    """
    az = math.degrees(math.atan2(d_east, d_north)) % 360.0  # azimuth, cw from N
    if az <= 90:
        mag, align = az, 2          # NE
    elif az <= 180:
        mag, align = 180 - az, 1    # SE
    elif az <= 270:
        mag, align = az - 180, 3    # SW
    else:
        mag, align = 360 - az, 4    # NW
    deg = int(mag)
    minutes = int((mag - deg) * 60)
    seconds = int(round((mag - deg - minutes / 60.0) * 3600))
    if seconds == 60:
        seconds = 0
        minutes += 1
    if minutes == 60:
        minutes = 0
        deg += 1
    return deg, minutes, seconds, align


def _section_corners(points: list[tuple[float, float]]):
    """Pick the 4 section corners (NW, NE, SE, SW) from boundary points.

    Uses extreme E±N combinations, which is exact for grid-aligned Utah
    sections and robust for the slightly-rotated real ones.
    """
    nw = min(points, key=lambda p: (p[0] - p[1]))   # small E, large N
    se = max(points, key=lambda p: (p[0] - p[1]))   # large E, small N
    ne = max(points, key=lambda p: (p[0] + p[1]))   # large E, large N
    sw = min(points, key=lambda p: (p[0] + p[1]))   # small E, small N
    return nw, ne, se, sw


def derive_section_corners(
    *,
    section: int,
    township: int,
    township_dir: int,
    range_: int,
    range_dir: int,
    baseline: int,
    polygon_points: list[tuple[float, float]],
    north_ref: str = "G",
) -> list[GridCorner]:
    """Derive the 16 quarter-side :class:`GridCorner` rows from a plat polygon.

    For sections absent from the curated Grid Numbers reference, the plat
    polygon (UTM corner points from ``PlatRepository``) still carries the
    real geometry. We split each of the 4 boundaries into 4 equal quarter
    segments and compute each one's length + grid bearing, so the Casing
    Review section sheet's DGET lookups resolve instead of coming up
    blank. Bearings reproduce the reference data to within a few
    arc-minutes (see ``test_grid_derivation``).
    """
    if not polygon_points or len(polygon_points) < 4:
        return []
    nw, ne, se, sw = _section_corners(polygon_points)
    boundaries = {
        "North": (nw, ne),
        "East": (ne, se),
        "South": (se, sw),
        "West": (sw, nw),
    }
    out: list[GridCorner] = []
    for name, sides in _DERIVE_SIDE_GROUPS:
        a, b = boundaries[name]
        d_east = (b[0] - a[0]) / 4.0   # per-quarter delta
        d_north = (b[1] - a[1]) / 4.0
        length_ft = math.hypot(d_east, d_north) * _M_TO_FT
        deg, minutes, seconds, align = _bearing_to_dms_alignment(
            d_east, d_north=d_north
        )
        for side in sides:
            out.append(
                GridCorner(
                    section=section,
                    township=township,
                    township_dir=township_dir,
                    range=range_,
                    range_dir=range_dir,
                    baseline=baseline,
                    side=side,
                    length_ft=round(length_ft, 2),
                    degrees=deg,
                    minutes=minutes,
                    seconds=seconds,
                    alignment=align,
                    north_ref=north_ref,
                )
            )
    return out
