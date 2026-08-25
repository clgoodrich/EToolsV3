"""Coordinate-system transforms used across the survey pipeline.

The legacy code reimplemented these in three places with subtle differences;
this module is the single source of truth.
"""

from __future__ import annotations

import math
from functools import lru_cache

import utm
from pyproj import CRS, Proj


def _validate_latlon(lat: float, lon: float) -> None:
    """Reject non-finite or out-of-range lat/lon before they reach pyproj/utm.

    Without this, ``NaN`` slips through ``grid_convergence`` as ``inf`` (poisoning
    every downstream azimuth/clearance) and an out-of-range latitude surfaces as
    a cryptic raw ``ProjError``/``OutOfRangeError`` instead of an actionable
    message.
    """
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError(
            f"latitude/longitude must be finite numbers, got ({lat}, {lon})"
        )
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"latitude {lat} out of range [-90, 90]")
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"longitude {lon} out of range [-180, 180]")


@lru_cache(maxsize=128)
def _spcs_proj(crs_string: str) -> Proj:
    return Proj(CRS(crs_string))


def grid_convergence(lat: float, lon: float, crs: str = "EPSG:32043") -> float:
    """Meridian convergence angle (degrees) between grid north and true north.

    Default CRS is Utah Central Zone (NAD27 State Plane), matching the legacy
    pipeline. Positive = grid north is east of true north.
    """
    _validate_latlon(lat, lon)
    proj = _spcs_proj(crs)
    factors = proj.get_factors(lon, lat, radians=False, errcheck=True)
    return float(factors.meridian_convergence)


def latlon_to_utm(lat: float, lon: float) -> tuple[float, float, int, str]:
    """Returns (easting, northing, zone_number, zone_letter)."""
    _validate_latlon(lat, lon)
    e, n, zn, zl = utm.from_latlon(lat, lon)
    return float(e), float(n), int(zn), str(zl)


def utm_to_latlon(easting: float, northing: float, zone_number: int, zone_letter: str) -> tuple[float, float]:
    """Project a UTM coordinate back to WGS84 lat/lon.

    Raises ``ValueError`` on anything unusable, matching ``_validate_latlon``
    and ``dms_to_decimal`` so callers only ever need one except clause.

    ``utm`` already raises ``OutOfRangeError`` (which *is* a ``ValueError``)
    for an out-of-range easting, northing or zone. What it does not normalise
    is non-numeric input: a string reaches numpy and raises ``UFuncTypeError``
    and ``None`` raises ``TypeError``, neither of which is a ``ValueError``.
    """
    try:
        e = float(easting)
        n = float(northing)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"UTM easting/northing must be numbers; got {easting!r}, {northing!r}"
        ) from exc
    try:
        lat, lon = utm.to_latlon(e, n, zone_number, zone_letter)
    except Exception as exc:
        raise ValueError(
            f"Not a valid UTM coordinate: easting={e}, northing={n}, "
            f"zone={zone_number}{zone_letter} ({exc})"
        ) from exc
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
        if not 0.0 <= nums[1] < 60.0:
            raise ValueError(f"minutes must be in [0, 60), got {nums[1]} in {part!r}")
        value += nums[1] / 60.0
    if len(nums) > 2:
        if not 0.0 <= nums[2] < 60.0:
            raise ValueError(f"seconds must be in [0, 60), got {nums[2]} in {part!r}")
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
