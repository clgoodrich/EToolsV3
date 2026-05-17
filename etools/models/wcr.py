"""WCR DTOs — well info, casing/cement, perforations & formation tops."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from pydantic import BaseModel, ConfigDict


class WCRWellInfo(BaseModel):
    """Source: tblAPDWCRWellInfo joined with tblAPD."""

    api_well_no: str
    well_name: str | None = None
    operator: str | None = None
    operator_no: str | None = None
    work_type: str | None = None
    well_type: str | None = None
    well_status: str | None = None
    slant: str | None = None
    field_no: int | None = None
    county_no: int | None = None
    proposed_tvd_ft: float | None = None
    proposed_md_ft: float | None = None
    elevation_ft: float | None = None
    spud_date: datetime | None = None
    rotary_date: datetime | None = None
    td_date: datetime | None = None
    completion_date: datetime | None = None
    surface_owner: str | None = None
    mineral_lease_type: str | None = None
    mineral_lease_number: str | None = None
    legal_description: str | None = None
    apd_no: int | None = None


class CasingRow(BaseModel):
    feature: str
    top_md: float | None = None
    bottom_md: float | None = None
    diameter: float | None = None
    weight: float | None = None
    grade: str | None = None
    connection_type: str | None = None
    cement_top: float | None = None
    cement_bottom: float | None = None
    cement_type: str | None = None
    sacks: int | None = None
    yield_: float | None = None
    cement_weight: float | None = None


class PerforationRow(BaseModel):
    md: float | None = None
    tvd: float | None = None
    top: float | None = None
    bottom: float | None = None
    zone_type: str | None = None
    formation: str | None = None
    producing: str | None = None
    tds: int | None = None
    perf_date: str | None = None
    status: str | None = None
    comments: str | None = None


class WCRBundle(BaseModel):
    """Everything the Excel writer needs in one bag."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    info: WCRWellInfo | None
    casing: pd.DataFrame
    perforations: pd.DataFrame
