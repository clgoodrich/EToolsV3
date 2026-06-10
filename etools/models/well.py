"""Well-related DTOs.

Mirrors columns the legacy code actually consumes from `DirectionalSurveyHeader`
and `tblAPD`. Only the fields used downstream are surfaced — extra columns are
ignored to keep DTOs stable when the schema evolves.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WellLookup(BaseModel):
    """User-supplied identifier — 10-digit API plus 4-char lateral suffix."""

    api: str = Field(min_length=10, max_length=10, pattern=r"^\d{10}$")
    lateral: str = Field(default="0000", max_length=4)

    @property
    def full_api(self) -> str:
        return f"{self.api}{self.lateral}"


class WellHeader(BaseModel):
    """Source: DirectionalSurveyHeader (one or more rows per API+lateral)."""

    model_config = ConfigDict(from_attributes=True)

    pkey: int
    api: str
    lateral: str
    well_name: str | None = None
    operator: str | None = None
    citing_type: str | None = None
    survey_company: str | None = None
    survey_type: str | None = None
    surface_elevation: float | None = None
    elevation_reference: str | None = None
    north_reference: str | None = None
    grid_convergence: float | None = None
    grid_scale_factor: float | None = None
    surface_lat: float | None = None
    surface_lon: float | None = None
    surface_x: float | None = None
    surface_y: float | None = None
    utm_zone: str | None = None
    plss_location: str | None = None
    upload_filename: str | None = None
    upload_datetime: datetime | None = None
