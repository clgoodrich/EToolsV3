"""
Well data models for EToolsV3.

This module defines data transfer objects (DTOs) for well-related data.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class WellLocation:
    """Well surface and bottomhole location data."""

    api_number: str

    # Surface location
    surface_latitude: Optional[float] = None
    surface_longitude: Optional[float] = None
    surface_easting: Optional[float] = None
    surface_northing: Optional[float] = None
    surface_elevation: Optional[float] = None

    # Bottomhole location
    bh_latitude: Optional[float] = None
    bh_longitude: Optional[float] = None
    bh_easting: Optional[float] = None
    bh_northing: Optional[float] = None

    # Township/Range/Section
    section: Optional[str] = None
    township: Optional[str] = None
    township_direction: Optional[str] = None
    range: Optional[str] = None
    range_direction: Optional[str] = None
    baseline: Optional[str] = None
    quarter: Optional[str] = None

    # Footage from section lines
    fnsl: Optional[float] = None  # Feet North/South Line
    fnsl_direction: Optional[str] = None
    fewl: Optional[float] = None  # Feet East/West Line
    fewl_direction: Optional[str] = None

    # Zone/Label
    zone_name: Optional[str] = None
    label: Optional[str] = None


@dataclass
class WellInfo:
    """General well information."""

    api_number: str
    well_name: Optional[str] = None
    well_number: Optional[str] = None
    operator_name: Optional[str] = None
    apd_number: Optional[str] = None

    # Status
    well_status: Optional[str] = None
    well_type: Optional[str] = None

    # Dates
    spud_date: Optional[datetime] = None
    completion_date: Optional[datetime] = None

    # Target formation
    target_formation: Optional[str] = None

    # Proposed depths
    proposed_depth_md: Optional[float] = None
    proposed_depth_tvd: Optional[float] = None


@dataclass
class CasingString:
    """Casing string information."""

    feature: str  # e.g., 'Surface', 'Intermediate', 'Production'

    # Casing specifications
    diameter: float  # inches
    weight: float  # lbs/ft
    grade: str  # e.g., 'P-110', 'N-80'

    # Depths
    top_depth: float  # feet
    bottom_depth: float  # feet

    # Connection
    connection_type: Optional[str] = None

    # Cement
    cement_top: Optional[float] = None
    cement_method: Optional[str] = None

    # Pressures
    internal_yield: Optional[float] = None  # psi
    collapse: Optional[float] = None  # psi
    joint_strength: Optional[float] = None  # lbs
    body_yield: Optional[float] = None  # lbs

    # Dimensions
    id: Optional[float] = None  # inches (inner diameter)
    od: Optional[float] = None  # inches (outer diameter)
    drift: Optional[float] = None  # inches
    wall_thickness: Optional[float] = None  # inches


@dataclass
class WellConstruction:
    """Well construction data including casing and completion."""

    api_number: str
    casing_strings: list[CasingString]

    # Hole sections
    hole_diameter: Optional[float] = None
    total_depth: Optional[float] = None

    # Mud weight by interval
    mud_weights: Optional[dict[float, float]] = None  # {depth: mud_weight}
