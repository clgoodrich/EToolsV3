"""
Survey data models for EToolsV3.

This module defines data transfer objects (DTOs) for directional survey data.
"""

from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime
import pandas as pd


@dataclass
class SurveyHeader:
    """Survey header information."""

    api_number: str
    lateral_name: str

    # Location
    surface_latitude: float
    surface_longitude: float
    surface_elevation: float

    # References
    north_reference: Optional[str] = None  # 'True', 'Grid', 'Magnetic'
    datum: Optional[str] = None
    convergence_angle: Optional[float] = None
    magnetic_declination: Optional[float] = None

    # Survey info
    citing_type: Optional[str] = None  # 'Drilled', 'Planned', 'Projected'
    survey_company: Optional[str] = None
    survey_date: Optional[datetime] = None

    # Operator info
    operator_name: Optional[str] = None
    well_name: Optional[str] = None


@dataclass
class SurveyPoint:
    """Single survey measurement point."""

    measured_depth: float
    inclination: float
    azimuth: float

    # Calculated positions (populated by processor)
    tvd: Optional[float] = None
    northing: Optional[float] = None
    easting: Optional[float] = None

    # Additional calculated fields
    vertical_section: Optional[float] = None
    dogleg_severity: Optional[float] = None
    build_rate: Optional[float] = None
    turn_rate: Optional[float] = None

    # Coordinate transformations
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    grid_northing: Optional[float] = None
    grid_easting: Optional[float] = None


@dataclass
class ProcessedSurvey:
    """Complete processed survey data."""

    header: SurveyHeader
    data: pd.DataFrame  # Survey points with all calculated values

    # KOP (Kick-Off Point) detection results
    kop_md: Optional[float] = None
    kop_method: Optional[str] = None
    kop_confidence: Optional[float] = None

    # Survey statistics
    total_md: Optional[float] = None
    max_tvd: Optional[float] = None
    max_inclination: Optional[float] = None
    max_dogleg: Optional[float] = None

    # Calculated trajectories for different references
    true_north_trajectory: Optional[pd.DataFrame] = None
    grid_north_trajectory: Optional[pd.DataFrame] = None
    magnetic_north_trajectory: Optional[pd.DataFrame] = None

    def __post_init__(self):
        """Calculate summary statistics after initialization."""
        if not self.data.empty:
            self.total_md = self.data['measured_depth'].max()
            if 'tvd' in self.data.columns:
                self.max_tvd = self.data['tvd'].max()
            if 'inclination' in self.data.columns:
                self.max_inclination = self.data['inclination'].max()
            if 'dogleg_severity' in self.data.columns:
                self.max_dogleg = self.data['dogleg_severity'].max()


@dataclass
class RawSurveyData:
    """Raw survey data as retrieved from database."""

    api_number: str
    lateral_name: str
    citing_type: str

    # Location
    surface_latitude: float
    surface_longitude: float
    surface_elevation: float

    # North reference
    north_reference: str

    # Survey measurements
    measurements: pd.DataFrame  # Columns: measured_depth, inclination, azimuth

    def to_survey_header(self) -> SurveyHeader:
        """Convert to SurveyHeader object."""
        return SurveyHeader(
            api_number=self.api_number,
            lateral_name=self.lateral_name,
            surface_latitude=self.surface_latitude,
            surface_longitude=self.surface_longitude,
            surface_elevation=self.surface_elevation,
            north_reference=self.north_reference,
            citing_type=self.citing_type
        )


@dataclass
class KOPDetectionResult:
    """Results from kick-off point detection."""

    measured_depth: float
    tvd: float
    inclination: float
    confidence: float  # 0-1 confidence score

    # Detection method used
    method: str  # 'first_deviation', 'rate_of_change', 'moving_average', etc.

    # All candidate KOPs from different methods
    candidates: dict[str, float] = field(default_factory=dict)

    # Additional metrics
    build_rate_at_kop: Optional[float] = None
    azimuth_at_kop: Optional[float] = None
