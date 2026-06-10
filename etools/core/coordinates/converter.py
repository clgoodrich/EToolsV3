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
