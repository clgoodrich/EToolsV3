"""Magnetic field lookup via pygeomag (World Magnetic Model).

The legacy code subclassed welleng.SurveyHeader to override ``_get_mag_data``
because welleng's bundled magnetic calculation is slow. We don't need to
subclass — we just hand welleng pre-computed declination/dip/B_total via the
``SurveyHeader`` constructor instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from pygeomag import GeoMag


@dataclass(slots=True, frozen=True)
class MagneticField:
    declination: float  # degrees, positive = east
    inclination: float  # magnetic dip, degrees
    total_intensity: float  # nT


def decimal_year(when: datetime | None = None) -> float:
    """Decimal year for WMM lookups (e.g., 2026.34)."""
    when = when or datetime.now()
    start = datetime(when.year, 1, 1)
    end = datetime(when.year + 1, 1, 1)
    return when.year + (when - start).total_seconds() / (end - start).total_seconds()


@lru_cache(maxsize=1)
def _geomag() -> GeoMag:
    """WMM-2025 model (valid 2025–2030).

    pygeomag's default ``WMM.COF`` still points at the 2020 model whose
    life span ended 2025-01-01, so we ask explicitly for the 2025 release.
    The path is relative to the pygeomag package — that quirk is required
    by pygeomag's loader.
    """
    return GeoMag(coefficients_file="wmm/WMM_2025.COF")


def lookup_magnetic_field(
    lat: float,
    lon: float,
    altitude_m: float = 0.0,
    when: float | datetime | None = None,
) -> MagneticField:
    """WMM lookup. ``when`` may be a decimal year, a datetime, or None for today."""
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError(
            f"magnetic-field lookup needs finite lat/lon, got ({lat}, {lon})"
        )
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError(
            f"magnetic-field lookup lat/lon out of range: ({lat}, {lon})"
        )
    if when is None:
        when_dec = decimal_year()
    elif isinstance(when, datetime):
        when_dec = decimal_year(when)
    else:
        when_dec = float(when)

    res = _geomag().calculate(glat=lat, glon=lon, alt=altitude_m, time=when_dec)
    return MagneticField(
        declination=float(res.dec),
        inclination=float(res.inclination),
        total_intensity=float(res.total_intensity),
    )
