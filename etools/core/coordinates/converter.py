"""Coordinate-system transforms used across the survey pipeline.

The legacy code reimplemented these in three places with subtle differences;
this module is the single source of truth.
"""

from __future__ import annotations

from functools import lru_cache

import utm
from pyproj import CRS, Proj


@lru_cache(maxsize=128)
def _spcs_proj(crs_string: str) -> Proj:
    return Proj(CRS(crs_string))


def grid_convergence(lat: float, lon: float, crs: str = "EPSG:32043") -> float:
    """Meridian convergence angle (degrees) between grid north and true north.

    Default CRS is Utah Central Zone (NAD27 State Plane), matching the legacy
    pipeline. Positive = grid north is east of true north.
    """
    proj = _spcs_proj(crs)
    factors = proj.get_factors(lon, lat, radians=False, errcheck=True)
    return float(factors.meridian_convergence)


def latlon_to_utm(lat: float, lon: float) -> tuple[float, float, int, str]:
    """Returns (easting, northing, zone_number, zone_letter)."""
    e, n, zn, zl = utm.from_latlon(lat, lon)
    return float(e), float(n), int(zn), str(zl)


def utm_to_latlon(easting: float, northing: float, zone_number: int, zone_letter: str) -> tuple[float, float]:
    lat, lon = utm.to_latlon(easting, northing, zone_number, zone_letter)
    return float(lat), float(lon)


def dms_to_decimal(part: str) -> float:
    """One coordinate component: decimal, or deg/min/sec with optional NSEW suffix."""
    import re

    part = part.strip()
    if not part:
        raise ValueError("empty coordinate")
    sign = -1.0 if part.startswith("-") or re.search(r"[SWsw]\s*$", part) else 1.0
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", part)]
    if not nums:
        raise ValueError(f"no number in {part!r}")
    value = nums[0]
    if len(nums) > 1:
        value += nums[1] / 60.0
    if len(nums) > 2:
        value += nums[2] / 3600.0
    return sign * value


def parse_coord_pair(raw: str | None) -> tuple[float, float]:
    """``"a, b"`` -> UTM 12N (easting, northing) in metres.

    Accepts UTM metres directly, decimal lat/lon, or DMS lat/lon
    (suffix S/W or a leading minus for southern/western values).
    Lat/lon is detected by magnitude (|a| <= 90 and |b| <= 180).
    """
    import re

    if not raw or not raw.strip():
        raise ValueError("missing coordinate")
    parts = re.split(r"[,;]", raw)
    if len(parts) != 2:
        raise ValueError("expected two comma-separated values")
    a, b = (dms_to_decimal(p) for p in parts)
    if abs(a) <= 90 and abs(b) <= 180:
        e, n, _zone, _letter = latlon_to_utm(a, b)
        return float(e), float(n)
    return a, b
