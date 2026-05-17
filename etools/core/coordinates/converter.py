"""Coordinate-system transforms used across the survey pipeline.

The legacy code reimplemented these in three places with subtle differences;
this module is the single source of truth.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
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


@lru_cache(maxsize=64)
def _aeqd_proj(lat0: float, lon0: float, units: str) -> Proj:
    return Proj(proj="aeqd", datum="WGS84", lat_0=lat0, lon_0=lon0, units=units)


def aeqd_project(
    lat: np.ndarray | list[float],
    lon: np.ndarray | list[float],
    lat0: float,
    lon0: float,
    units: str = "us-ft",
) -> tuple[np.ndarray, np.ndarray]:
    """Azimuthal-equidistant projection of (lat, lon) → (north, east).

    Centered at (``lat0``, ``lon0``) — the well's surface location — this
    preserves true distance and azimuth from the SHL, which is what survey
    calculations care about.

    Returns ``(north, east)`` arrays in the requested ``units``.
    """
    proj = _aeqd_proj(lat0, lon0, units)
    lon_arr = np.asarray(lon, dtype=float)
    lat_arr = np.asarray(lat, dtype=float)
    e, n = proj(lon_arr, lat_arr)
    return n, e
