"""
Plat (section) data models for EToolsV3.

This module defines data transfer objects for PLSS (Public Land Survey System)
section boundaries and related spatial data.
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd
from shapely.geometry import Polygon, Point


@dataclass
class PlatSection:
    """PLSS section boundary information."""

    # Concatenated identifier (e.g., '02041N02WU')
    conc: str

    # Section identifiers
    section: int
    township: int
    township_direction: str  # 'N' or 'S'
    range: int
    range_direction: str  # 'E' or 'W'
    baseline: str  # 'U' for Utah, etc.

    # Geometry
    polygon: Polygon
    centroid: Point

    # Coordinates
    northing: Optional[float] = None
    easting: Optional[float] = None

    # Label for display
    label: Optional[str] = None

    # Version (for historical plats)
    version: Optional[int] = None

    @property
    def tsr_string(self) -> str:
        """Get Township-Section-Range string representation."""
        return f"{self.section:02d} {self.township:02d}{self.township_direction} {self.range:02d}{self.range_direction} {self.baseline}"

    def contains_point(self, easting: float, northing: float) -> bool:
        """Check if a point is inside this plat section."""
        point = Point(easting, northing)
        return self.polygon.contains(point)


@dataclass
class PlatBoundary:
    """Boundary segments of a plat section."""

    conc: str
    polygon: Polygon

    # Boundary segments
    north_boundary: Optional[list[tuple[float, float]]] = None
    south_boundary: Optional[list[tuple[float, float]]] = None
    east_boundary: Optional[list[tuple[float, float]]] = None
    west_boundary: Optional[list[tuple[float, float]]] = None

    # Boundary lengths (feet)
    north_length: Optional[float] = None
    south_length: Optional[float] = None
    east_length: Optional[float] = None
    west_length: Optional[float] = None


@dataclass
class AdjacentPlats:
    """Adjacent plat sections around a target plat."""

    center_plat: PlatSection
    north_plat: Optional[PlatSection] = None
    south_plat: Optional[PlatSection] = None
    east_plat: Optional[PlatSection] = None
    west_plat: Optional[PlatSection] = None
    northeast_plat: Optional[PlatSection] = None
    northwest_plat: Optional[PlatSection] = None
    southeast_plat: Optional[PlatSection] = None
    southwest_plat: Optional[PlatSection] = None

    def get_all_plats(self) -> list[PlatSection]:
        """Get list of all plats (center and adjacent)."""
        plats = [self.center_plat]
        for plat in [
            self.north_plat, self.south_plat, self.east_plat, self.west_plat,
            self.northeast_plat, self.northwest_plat,
            self.southeast_plat, self.southwest_plat
        ]:
            if plat is not None:
                plats.append(plat)
        return plats


@dataclass
class SpatialQuery:
    """Spatial query parameters for finding plats."""

    # Bounding box
    min_easting: float
    max_easting: float
    min_northing: float
    max_northing: float

    # Optional buffer distance (feet)
    buffer: float = 1000.0

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """Get bounding box tuple (minx, miny, maxx, maxy)."""
        return (
            self.min_easting - self.buffer,
            self.min_northing - self.buffer,
            self.max_easting + self.buffer,
            self.max_northing + self.buffer
        )

    @classmethod
    def from_survey_data(cls, survey_df: pd.DataFrame, buffer: float = 1000.0) -> 'SpatialQuery':
        """
        Create spatial query from survey trajectory data.

        Args:
            survey_df: DataFrame with 'easting' and 'northing' columns.
            buffer: Buffer distance in feet.

        Returns:
            SpatialQuery instance.
        """
        return cls(
            min_easting=survey_df['easting'].min(),
            max_easting=survey_df['easting'].max(),
            min_northing=survey_df['northing'].min(),
            max_northing=survey_df['northing'].max(),
            buffer=buffer
        )
