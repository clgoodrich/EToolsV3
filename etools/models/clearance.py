"""Clearance DTOs — distances from survey points to PLSS section boundaries."""

from __future__ import annotations

from pydantic import BaseModel


class ClearanceRow(BaseModel):
    """One survey point's clearance to its containing section's four boundaries."""

    point_index: int
    measured_depth: float
    label: str
    fnl: float
    fsl: float
    fel: float
    fwl: float


class FootageSummary(BaseModel):
    """SHL / KOP / Landing / BHL footages — the row that goes onto the WCR."""

    location: str
    measured_depth: float
    azimuth: float
    fnl: float
    fsl: float
    fel: float
    fwl: float
