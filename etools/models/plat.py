"""Plat (PLSS section) DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from shapely.geometry import Polygon


class PlatSection(BaseModel):
    """A PLSS section (1 sq. mile) polygon."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    conc: str
    label: str
    geometry: Polygon
    centroid_x: float
    centroid_y: float
