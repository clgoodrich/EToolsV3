"""
Clearance data models for EToolsV3.

This module defines data transfer objects for wellbore clearance calculations
and results.
"""

from dataclasses import dataclass
from typing import Optional, Literal
import pandas as pd


@dataclass
class ClearancePoint:
    """Clearance measurements at a single survey point."""

    measured_depth: float
    tvd: float

    # Position
    easting: float
    northing: float

    # Section information
    section_conc: str
    section_label: str

    # Distances from section boundaries (feet)
    fnl: float  # Feet from North Line
    fsl: float  # Feet from South Line
    fel: float  # Feet from East Line
    fwl: float  # Feet from West Line

    # Minimum clearance
    min_clearance: float
    min_clearance_direction: Literal['N', 'S', 'E', 'W']

    # Status flags
    is_in_section: bool = True
    crosses_boundary: bool = False


@dataclass
class ClearanceResults:
    """Complete clearance calculation results for a wellbore."""

    api_number: str
    lateral_name: str

    # All clearance points
    clearances: pd.DataFrame  # DataFrame of ClearancePoint data

    # Summary statistics
    min_fnl: Optional[float] = None
    min_fsl: Optional[float] = None
    min_fel: Optional[float] = None
    min_fwl: Optional[float] = None
    min_overall_clearance: Optional[float] = None

    # Sections penetrated
    sections_penetrated: Optional[list[str]] = None
    num_sections: Optional[int] = None

    # Boundary crossings
    boundary_crossings: Optional[list[dict]] = None

    # Warning flags
    has_clearance_violations: bool = False
    violation_threshold: float = 50.0  # feet

    def __post_init__(self):
        """Calculate summary statistics after initialization."""
        if not self.clearances.empty:
            self.min_fnl = self.clearances['fnl'].min()
            self.min_fsl = self.clearances['fsl'].min()
            self.min_fel = self.clearances['fel'].min()
            self.min_fwl = self.clearances['fwl'].min()
            self.min_overall_clearance = self.clearances['min_clearance'].min()

            # Check for violations
            self.has_clearance_violations = self.min_overall_clearance < self.violation_threshold

            # Get unique sections
            if 'section_conc' in self.clearances.columns:
                self.sections_penetrated = self.clearances['section_conc'].unique().tolist()
                self.num_sections = len(self.sections_penetrated)


@dataclass
class FootageCalculation:
    """Footage calculations for WCR reporting."""

    section_conc: str
    section_label: str

    # Drilled footage in section
    total_footage: float
    measured_depth_in: float
    measured_depth_out: float

    # Footage by type
    vertical_footage: Optional[float] = None
    horizontal_footage: Optional[float] = None
    curved_footage: Optional[float] = None

    # Formation
    formation: Optional[str] = None


@dataclass
class SectionFootage:
    """Summary of footage calculations for all sections."""

    api_number: str
    lateral_name: str

    # Footage by section
    section_footages: list[FootageCalculation]

    # Total footage
    total_drilled: float
    total_horizontal: Optional[float] = None

    def get_section_footage(self, conc: str) -> Optional[FootageCalculation]:
        """Get footage calculation for a specific section."""
        for footage in self.section_footages:
            if footage.section_conc == conc:
                return footage
        return None


@dataclass
class WellboreSeparation:
    """
    Separation distance calculation between two wellbores.

    Used for anti-collision analysis and offset well clearances.
    """

    # Well identifiers
    well1_api: str
    well2_api: str

    # Minimum separation
    min_separation: float  # feet
    min_separation_md1: float  # MD at well 1
    min_separation_md2: float  # MD at well 2

    # Separation at specific points
    separations: pd.DataFrame  # DataFrame with MD and separation distances

    # Status
    is_collision_risk: bool = False
    risk_threshold: float = 15.0  # feet

    def __post_init__(self):
        """Determine collision risk after initialization."""
        self.is_collision_risk = self.min_separation < self.risk_threshold
