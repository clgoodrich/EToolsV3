"""WCR DTOs — well info, casing/cement, perforations & formation tops."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


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


class PerfStage(BaseModel):
    """A single completion stage from the operator's perf table (pg 3 of WCR)."""

    stage: int
    interval_top_md: float
    interval_bottom_md: float
    num_perfs: int | None = None
    size_in: float | None = None


class FormationTop(BaseModel):
    fr: int | None = None
    name: str
    top_md: float | None = None
    top_tvd: float | None = None
    description: str | None = None


class WellPositionRow(BaseModel):
    """Section 27 row: a footage citation for one feature of the wellbore."""

    name: str  # "Surface" / "Producing Interval Top" / "Producing Interval Bottom" / "Total Depth"
    fnl: float | None = None
    fsl: float | None = None
    fel: float | None = None
    fwl: float | None = None
    qtr_qtr: str | None = None
    section: str | None = None
    township: str | None = None
    township_dir: str | None = None
    range: str | None = None
    range_dir: str | None = None
    meridian: str | None = None
    utm_easting: float | None = None
    utm_northing: float | None = None


class WCRLocationRow(BaseModel):
    """A row in the final Excel output. One of: SHL, Control_Point, Frac_Start, Frac_End, BHL."""

    name: str
    measured_depth: float
    tvd: float
    easting: float
    northing: float
    fnl: float | None = None
    fsl: float | None = None
    fel: float | None = None
    fwl: float | None = None
    section: str | None = None
    township: str | None = None
    township_dir: str | None = None
    range: str | None = None
    range_dir: str | None = None
    baseline: str | None = None


# ---------------------------------------------------------------------------
# Daily Drilling Report (DDR) — extracted from the Operation Summary Report
# appendix inside a WCR PDF.
# ---------------------------------------------------------------------------


class DDRTimeLogEntry(BaseModel):
    """One row from the operator's daily drilling time log.

    Mirrors the Peloton "Operation Summary Report" column layout: every
    time-window the rig spent on a task during drilling, casing, completion,
    drillout, or frac operations gets one of these.
    """

    index: int = Field(description="0-based row index inside the DDR job")
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_hr: float | None = None
    phase: str | None = Field(
        None,
        description=(
            "High-level operation phase: 'Surface, Drill', 'Intermediate, Drill Vertical', "
            "'Production, Drill Lateral', 'Production, Casing', 'Drillout, <code2>', "
            "'Frac, <code2>', 'Toe Prep, <code2>', 'Inactive', etc."
        ),
    )
    code1: str | None = Field(
        None, description="Operation code 1 (e.g. 'Drilling - Rotate', 'Tripping', 'Frac. Job')"
    )
    code2: str | None = Field(
        None, description="Operation code 2 (short tag, e.g. 'DRL - ROTATE', 'TRIP', 'FRAC')"
    )
    ops_category: str | None = Field(
        None, description="'PT' productive, 'NPT' non-productive, '' otherwise"
    )
    start_depth_ftkb: float | None = None
    end_depth_ftkb: float | None = None
    comment: str | None = None
    plain_english: str | None = Field(
        None,
        description=(
            "Telegram-terse plain-English translation of the comment "
            "(LLM-generated; only set by the opt-in operations parse)."
        ),
    )
    trouble: list[str] = Field(
        default_factory=list,
        description=(
            "Rules-flagged problem categories found in this entry "
            "(stuck pipe, fishing, equipment failure, …). Empty = clean."
        ),
    )


KeyEventType = Literal[
    "KOP",
    "EOC",
    "Landing",
    "CasingRun",
    "CementJob",
    "FIT",
    "FormationPick",
    "PerforationGuns",
    "FracStage",
    "Plug",
    "Fish",
    "BHA",
    "NPT",
    "Other",
]


class DDRKeyEvent(BaseModel):
    """A notable operational event extracted from the time-log comments."""

    event_type: KeyEventType
    md_ft: float | None = Field(None, description="Measured depth in feet, if extractable")
    tvd_ft: float | None = None
    depth_top_ft: float | None = Field(None, description="Top of an interval (e.g. casing/perf)")
    depth_bottom_ft: float | None = None
    timestamp: datetime | None = None
    description: str = Field(description="Human-readable summary of the event")
    source_index: int = Field(description="Index into DDRRecord.entries the event came from")
    confidence: float = Field(
        default=1.0, description="0-1 confidence (rules=1.0, LLM=0.6-0.9)"
    )
    extra: dict = Field(default_factory=dict, description="Type-specific structured fields")


class DDRRecord(BaseModel):
    """All DDR content extracted from a WCR PDF, organised by job category."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    job_category: str | None = Field(
        None, description="'Drilling', 'Completion', 'Workover', etc."
    )
    well_name: str | None = None
    api: str | None = None
    pad_name: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    entries: list[DDRTimeLogEntry] = Field(default_factory=list)
    key_events: list[DDRKeyEvent] = Field(default_factory=list)
    summary: str | None = Field(
        None, description="Free-text overview of the well's drilling + completion history"
    )
    narrative: str | None = Field(
        None,
        description=(
            "Detailed plain-English walkthrough of the entire time log, "
            "day by day, with the driller's abbreviations translated. "
            "LLM-generated; only populated when the user opts into the "
            "(slow) operations parse."
        ),
    )

    # Convenience lookups.
    def find_event(self, event_type: KeyEventType) -> DDRKeyEvent | None:
        """Return the first event of ``event_type``, or None."""
        for e in self.key_events:
            if e.event_type == event_type:
                return e
        return None

    def all_events(self, event_type: KeyEventType) -> list[DDRKeyEvent]:
        return [e for e in self.key_events if e.event_type == event_type]


class WCRPdfData(BaseModel):
    """Everything the WCR PDF parser pulls out of a single DOGM form."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Header (Sections 1-26)
    well_name: str | None = None
    api: str | None = None
    operator: str | None = None
    well_type: str | None = None
    field_name: str | None = None
    county: str | None = None
    spud_date: str | None = None
    rotary_date: str | None = None
    td_date: str | None = None
    completion_date: str | None = None
    elevation_ft: float | None = None
    ground_elev_ft: float | None = None
    total_md_ft: float | None = None
    total_tvd_ft: float | None = None
    pbtd_md_ft: float | None = None
    pbtd_tvd_ft: float | None = None
    well_status: str | None = None

    # Section 27 — well position rows
    positions: list[WellPositionRow] = []

    # Section 28 — casing
    casing: list[CasingRow] = []

    # Section 32 — formation tops
    formations: list[FormationTop] = []

    # Stage perf table (pg 3+)
    perf_stages: list[PerfStage] = []

    # DDRs — Operation Summary Report appendix, one per job category (drilling, completion, ...).
    ddrs: list[DDRRecord] = Field(default_factory=list)

    # Detected form type — "wcr" (DOGM Form 8 Well Completion Report),
    # "form15" (Workover/Recompletion Tax Credit Application), or "unknown".
    # Set by the parser based on header text patterns.
    form_type: str = Field(default="unknown")

    # Provenance
    source_pdf: str | None = None
    warnings: list[str] = []

    @property
    def surface_position(self) -> WellPositionRow | None:
        for p in self.positions:
            if p.name and p.name.lower().startswith("surface"):
                return p
        return None

    @property
    def first_perf_md(self) -> float | None:
        if not self.perf_stages:
            return None
        return min(s.interval_top_md for s in self.perf_stages)

    @property
    def last_perf_md(self) -> float | None:
        if not self.perf_stages:
            return None
        return max(s.interval_bottom_md for s in self.perf_stages)
