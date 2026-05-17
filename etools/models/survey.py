"""Survey DTOs — raw points from the database and processed results."""

from __future__ import annotations

from enum import Enum
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class SurveyFrame(str, Enum):
    """Reference frame for processed survey output."""

    TRUE = "true"
    GRID = "grid"


class CitingType(str, Enum):
    PLANNED = "planned"
    DRILLED = "drilled"


class SurveyHeader(BaseModel):
    """One header row per (API, lateral, citing_type)."""

    pkey: int
    api: str
    lateral: str
    citing_type: str
    surface_lat: float
    surface_lon: float
    surface_elevation: float | None = None
    north_reference: str | None = None


class SurveyPoint(BaseModel):
    """Raw survey station from DirectionalSurveyData."""

    measured_depth: float
    inclination: float = Field(description="degrees")
    azimuth: float = Field(description="degrees")
    tvd: float | None = None
    north_offset: float | None = None
    east_offset: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    x: float | None = None
    y: float | None = None
    note: str | None = None


class ProcessedSurvey(BaseModel):
    """A trajectory processed in a specific reference frame.

    The actual point cloud is carried as a pandas DataFrame because downstream
    consumers (clearance calculator, plotters, Excel writer) all expect tabular
    data and copying through Pydantic for hundreds of rows is wasteful.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    api: str
    lateral: str
    citing_type: CitingType
    frame: SurveyFrame
    elevation: float
    convergence_angle: float = Field(description="degrees, grid - true")
    proposed_azimuth: float | None = None
    points: pd.DataFrame
    kop_md: float | None = None
    landing_md: float | None = None

    @property
    def label(self) -> str:
        """Stable identifier matching legacy column names (drl_df_true_dx etc.)."""
        head = "drl" if self.citing_type == CitingType.DRILLED else "pln"
        frame = "true" if self.frame == SurveyFrame.TRUE else "grid"
        return f"{head}_df_{frame}_dx"
