"""DTOs for the DOGM Form 3 — Application for Permit to Drill."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class APDCasingString(BaseModel):
    """One row of the APD's Hole, Casing, and Cement Information table."""

    # String tag as it appears in the PDF: "Cond" / "Surf" / "I1" / "I2" /
    # "Prod" / "Liner". We keep the raw token so the generator can map it to
    # the correct STRING N block in the Casing Review template.
    tag: str
    hole_size_in: Optional[float] = None
    casing_size_in: Optional[float] = None
    length_top_ft: Optional[float] = None
    length_bottom_ft: Optional[float] = None
    weight_ppf: Optional[float] = None
    grade: Optional[str] = None  # e.g. "J-55"
    collar: Optional[str] = None  # e.g. "BTC", "STC", "LTC"
    max_mud_weight_ppg: Optional[float] = None
    # Cement entries — typically two stages: lead (top) and tail (shoe).
    cement_lead_type: Optional[str] = None
    cement_lead_sacks: Optional[int] = None
    cement_lead_yield: Optional[float] = None
    cement_lead_weight_ppg: Optional[float] = None
    cement_tail_type: Optional[str] = None
    cement_tail_sacks: Optional[int] = None
    cement_tail_yield: Optional[float] = None
    cement_tail_weight_ppg: Optional[float] = None


class APDFormationTop(BaseModel):
    name: str
    md_ft: Optional[float] = None
    tvd_ft: Optional[float] = None


class APDLocationRow(BaseModel):
    """One row from Section 20 (Location of Well)."""

    name: str  # "Surface" / "Top of Uppermost Producing Zone" / "At Total Depth"
    fnl: Optional[float] = None
    fsl: Optional[float] = None
    fel: Optional[float] = None
    fwl: Optional[float] = None
    # Measured / true-vertical depth of this location, when the APD prints it
    # (e.g. the "KOP: 7965' MD, 7865' TVD" line for the kickoff row).
    measured_depth: Optional[float] = None
    tvd_ft: Optional[float] = None
    qtr_qtr: Optional[str] = None
    section: Optional[str] = None
    township: Optional[str] = None
    township_dir: Optional[str] = None
    range: Optional[str] = None
    range_dir: Optional[str] = None
    meridian: Optional[str] = None


class APDPdfData(BaseModel):
    """Everything the APD parser extracts from a Form 3 PDF."""

    well_name: Optional[str] = None
    api: Optional[str] = None
    operator: Optional[str] = None
    field_name: Optional[str] = None
    county: Optional[str] = None
    well_type: Optional[str] = None
    slant: Optional[str] = None
    proposed_md_ft: Optional[float] = None
    proposed_tvd_ft: Optional[float] = None
    # Document-stated kickoff point, when the APD prints "KOP: <md>' MD,
    # <tvd>' TVD". Authoritative — preferred over survey-based KOP detection.
    kop_md_ft: Optional[float] = None
    kop_tvd_ft: Optional[float] = None
    ground_elev_ft: Optional[float] = None
    # Frac gradient at the production-string shoe (psi/ft). From the
    # page-2 Safety Factors table when the parser can find it.
    frac_gradient_psi_per_ft: Optional[float] = None
    # BOP working-pressure rating stated in the permit's "Minimum
    # Specifications for Pressure Control" section (e.g. "A 5,000 psi BOP
    # system or better will be used"). Authoritative when present — the
    # BOPE review shows it as-is rather than inferring a rating.
    bope_system_psi: Optional[float] = None

    locations: list[APDLocationRow] = Field(default_factory=list)
    casing: list[APDCasingString] = Field(default_factory=list)
    formations: list[APDFormationTop] = Field(default_factory=list)

    source_pdf: Optional[str] = None
    form_type: str = Field(default="unknown")  # "apd" / "unknown"
    warnings: list[str] = Field(default_factory=list)
