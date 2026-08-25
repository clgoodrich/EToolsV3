"""PLSS section-footage geometry.

Given a section polygon (UTM zone 12N) and either a point or a set of
boundary-line footages, this module converts between the two — exactly
what the SHL/BHL Section sheets need to populate the UTM and footage
input cells without depending on the spreadsheet's trigonometric chain.

Two primary functions:

    polygon_footages(polygon, point_xy)
        → (fnl, fsl, fel, fwl) in feet, using the polygon's bounding box
          as the proxy for the four compass-direction edges.

    footages_to_xy(polygon, *, fnl=None, fsl=None, fel=None, fwl=None)
        → (x, y) in UTM meters. Caller supplies one N/S footage and one
          E/W footage (typical APD form: e.g. ``fsl=560, fel=804``).

Bounding-box approximation is exact for cardinally-aligned sections
(~95% of PLSS sections in Utah). Irregular sections with meander
corrections (gov't lots, fractional sections) have a residual error
proportional to how non-rectangular they are; for those, a follow-up
can project to the actual N/E/S/W edge segments via shapely.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry


_M_TO_FT = 3.280839895


@dataclass(frozen=True)
class SectionFootages:
    """Distances from a point inside a section to each of its 4 boundary
    lines, in feet. Sum (fnl + fsl) ≈ section height; (fel + fwl) ≈ width."""

    fnl: float
    fsl: float
    fel: float
    fwl: float


class DegenerateGeometryError(ValueError):
    """A section polygon has no usable extent.

    Subclasses ``ValueError`` on purpose: ``sections.py``, ``writer.py`` and
    ``build_section_definitions`` already catch ``ValueError`` and skip the
    offending section, which is the behavior we want. Shapely returns
    ``(nan, nan, nan, nan)`` from ``.bounds`` on an empty geometry and that
    unpacks without complaint, so without this guard the NaN flowed straight
    into the section-sheet footages -- a wrong answer rather than an error.
    """


def _checked_bounds(polygon: BaseGeometry) -> tuple[float, float, float, float]:
    """Polygon bounds, or ``DegenerateGeometryError`` if they are unusable."""
    if polygon is None:
        raise DegenerateGeometryError("No polygon supplied.")
    if getattr(polygon, "is_empty", False):
        raise DegenerateGeometryError(
            "Section polygon is empty - it most likely collapsed during "
            "geometry repair. Check the section's segment overrides."
        )
    minx, miny, maxx, maxy = polygon.bounds
    if not all(math.isfinite(v) for v in (minx, miny, maxx, maxy)):
        raise DegenerateGeometryError(
            f"Section polygon has non-finite bounds: {(minx, miny, maxx, maxy)!r}"
        )
    if maxx <= minx or maxy <= miny:
        raise DegenerateGeometryError(
            f"Section polygon has zero extent: width={maxx - minx}, "
            f"height={maxy - miny}"
        )
    return minx, miny, maxx, maxy


def polygon_footages(polygon: BaseGeometry, point_xy: tuple[float, float]) -> SectionFootages:
    """Compute (FNL, FSL, FEL, FWL) in feet for ``point_xy`` inside ``polygon``.

    Uses the polygon's bounding box as the proxy for the four cardinal
    boundary lines. Point may sit slightly outside the polygon if the
    section has meander corrections; we don't clamp because the user's
    APD footages are the authoritative input we're recreating.
    """
    minx, miny, maxx, maxy = _checked_bounds(polygon)
    px, py = point_xy
    return SectionFootages(
        fnl=(maxy - py) * _M_TO_FT,
        fsl=(py - miny) * _M_TO_FT,
        fel=(maxx - px) * _M_TO_FT,
        fwl=(px - minx) * _M_TO_FT,
    )


def footages_to_xy(
    polygon: BaseGeometry,
    *,
    fnl: float | None = None,
    fsl: float | None = None,
    fel: float | None = None,
    fwl: float | None = None,
) -> tuple[float, float]:
    """Inverse of :func:`polygon_footages`. Caller supplies exactly one
    N/S footage and exactly one E/W footage (the APD ships one of each).
    """
    if (fnl is None) == (fsl is None):
        raise ValueError("Supply exactly one of fnl / fsl")
    if (fel is None) == (fwl is None):
        raise ValueError("Supply exactly one of fel / fwl")
    minx, miny, maxx, maxy = _checked_bounds(polygon)
    if fnl is not None:
        y = maxy - (fnl / _M_TO_FT)
    else:
        y = miny + (fsl / _M_TO_FT)
    if fel is not None:
        x = maxx - (fel / _M_TO_FT)
    else:
        x = minx + (fwl / _M_TO_FT)
    return x, y


def location_footages(location) -> tuple[float | None, float | None, float | None, float | None]:
    """Pull (fnl, fsl, fel, fwl) tuple from an APD/WCR location row.
    Any missing direction is ``None`` — the APD always carries exactly
    one N/S and one E/W footage, never both."""
    return (
        getattr(location, "fnl", None),
        getattr(location, "fsl", None),
        getattr(location, "fel", None),
        getattr(location, "fwl", None),
    )
