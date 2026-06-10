"""Split a PLSS section polygon's edges into N/S/E/W groups.

A regular Utah PLSS section is approximately a 1-mile square aligned to grid
north. Its boundary edges fall into four directional groups based on the
azimuth of the edge segment:

* North boundary  — edges that run roughly east-west on the north side
* South boundary  — edges that run east-west on the south side
* East boundary   — edges that run north-south on the east side
* West boundary   — edges that run north-south on the west side

We classify each edge by:
1. Its bearing — east-west edges have azimuth ≈ 90° or 270° (within 45°),
   north-south edges have azimuth ≈ 0° or 180°.
2. Its position relative to the section centroid — north vs. south for
   east-west edges, east vs. west for north-south edges.

Sections with non-orthogonal boundaries (bordering rivers, surveys with
unusual breaks) classify their edges by majority direction, which works for
the regulatory FNL/FSL/FEL/FWL convention used by Utah DOGM.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from shapely.geometry import LineString, Point, Polygon

Side = Literal["N", "S", "E", "W"]


@dataclass(slots=True)
class SectionBoundary:
    """A section's perimeter split by cardinal direction."""

    conc: str
    label: str
    centroid: tuple[float, float]
    edges_by_side: dict[Side, list[LineString]] = field(default_factory=dict)

    def line(self, side: Side) -> LineString | None:
        """Return the side as a single MultiLineString-equivalent (joined)."""
        edges = self.edges_by_side.get(side, [])
        if not edges:
            return None
        if len(edges) == 1:
            return edges[0]
        # Join collinear-ish edges into one logical boundary line for distance ops.
        merged_coords: list[tuple[float, float]] = []
        for e in edges:
            for c in e.coords:
                if not merged_coords or merged_coords[-1] != c:
                    merged_coords.append(c)
        return LineString(merged_coords) if len(merged_coords) >= 2 else edges[0]


def segment_section(polygon: Polygon, conc: str = "", label: str = "") -> SectionBoundary:
    """Split ``polygon``'s exterior into N/S/E/W edge collections."""
    cx, cy = polygon.centroid.x, polygon.centroid.y
    coords = list(polygon.exterior.coords)
    edges_by_side: dict[Side, list[LineString]] = {"N": [], "S": [], "E": [], "W": []}

    for (x1, y1), (x2, y2) in zip(coords[:-1], coords[1:]):
        if (x1, y1) == (x2, y2):
            continue
        side = _classify_edge(x1, y1, x2, y2, cx, cy)
        edges_by_side[side].append(LineString([(x1, y1), (x2, y2)]))

    return SectionBoundary(
        conc=conc, label=label, centroid=(cx, cy), edges_by_side=edges_by_side
    )


def _classify_edge(x1: float, y1: float, x2: float, y2: float, cx: float, cy: float) -> Side:
    """Bucket a single edge by its bearing + position relative to the centroid."""
    dx, dy = x2 - x1, y2 - y1
    # Edge midpoint vs centroid tells us which side of the polygon we're on.
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    # Bearing of edge as compass azimuth (0 = north, 90 = east). For deciding
    # "is this an east-west edge or a north-south edge", we use the angle from
    # vertical (north) of the segment direction.
    angle_from_north = math.degrees(math.atan2(dx, dy)) % 180.0  # 0..180
    is_east_west = 45.0 <= angle_from_north <= 135.0

    if is_east_west:
        return "N" if my >= cy else "S"
    return "E" if mx >= cx else "W"


def perpendicular_distance(point_x: float, point_y: float, line: LineString) -> float:
    """Shortest distance from a point to a line, in the line's CRS units (meters here)."""
    if line is None:
        return float("nan")
    return float(line.distance(Point(point_x, point_y)))


# Convenience for the calculator: produce all four distances at once.
def distances_to_sides(
    point_x: float, point_y: float, boundary: SectionBoundary
) -> dict[Side, float]:
    return {
        side: perpendicular_distance(point_x, point_y, boundary.line(side))  # type: ignore[arg-type]
        for side in ("N", "S", "E", "W")
    }


__all__ = [
    "SectionBoundary",
    "Side",
    "distances_to_sides",
    "perpendicular_distance",
    "segment_section",
]
