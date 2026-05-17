"""LLM-driven structured extraction for survey PDFs.

When the rules-based parser can't find a clean MD/INC/AZI table (e.g. the
Crescent Point packets where the "survey" is rendered as a diagram with
labels), we hand the Docling markdown to a local LLM and ask it to fill
out a Pydantic schema covering both the survey rows and the well metadata.

The schema mirrors what ``parse_survey_pdf`` returns from the rule path,
so the downstream UI doesn't care which layer succeeded.

The markdown is trimmed to a relevant window before being sent — operator
PDFs often contain 30+ pages of cover letter / regulations / attachments
around a single survey table page. Sending all of that bloats the prompt
and times out CPU inference.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from etools.core.llm import OllamaClient, extract_with_schema
from etools.logging_setup import get_logger

log = get_logger(__name__)


class LLMSurveyRow(BaseModel):
    measured_depth_ft: float = Field(description="MD in feet")
    inclination_deg: float = Field(description="Inclination in degrees, 0-180")
    azimuth_deg: float = Field(description="Azimuth in degrees, 0-360")


class LLMSurveyExtraction(BaseModel):
    """Result schema. Every field optional except ``surveys`` which may be empty."""

    well_name: Optional[str] = Field(
        None, description="Well or borehole name as stated in the document"
    )
    api_number: Optional[str] = Field(
        None, description="10-digit API well number, if present, no formatting"
    )
    operator: Optional[str] = Field(None, description="Operator company name")
    surface_latitude_deg: Optional[float] = Field(
        None, description="Surface location latitude in decimal degrees, NAD83 or WGS84"
    )
    surface_longitude_deg: Optional[float] = Field(
        None, description="Surface location longitude in decimal degrees (negative for western hemisphere)"
    )
    surface_elevation_ft: Optional[float] = Field(
        None, description="Surface elevation in feet (KB / GLE / kelly bushing if available, else ground level)"
    )
    north_reference: Optional[str] = Field(
        None, description="One of 'true', 'grid', or 'magnetic' if stated; null if unclear"
    )
    grid_convergence_deg: Optional[float] = Field(
        None, description="Grid convergence angle in degrees if stated"
    )
    magnetic_declination_deg: Optional[float] = Field(
        None, description="Magnetic declination in degrees if stated"
    )
    plss_legal: Optional[str] = Field(
        None,
        description="PLSS legal description like 'NWNW Sec 5 T3S R1E U.S.M.' if present",
    )
    surveys: list[LLMSurveyRow] = Field(
        default_factory=list,
        description=(
            "Every directional-survey station as MD/INC/AZI. "
            "Use empty list if the document does not include a survey table."
        ),
    )


_SYSTEM_PROMPT = (
    "You are a directional drilling assistant. You read PDFs of well "
    "applications, completion reports, and directional surveys, and extract "
    "structured data from them. Numeric fields must be numbers, never strings. "
    "Use null for fields the document does not state. Western longitudes are "
    "negative. Inclination is in degrees (0=vertical, 90=horizontal). Azimuth "
    "is in degrees clockwise from north (0-360)."
)


def llm_extract(markdown: str, *, client: OllamaClient | None = None) -> LLMSurveyExtraction:
    """Call the LLM with a trimmed slice of the Docling markdown.

    The LLM is used ONLY for metadata fields (well name, lat/lon, elevation,
    operator, PLSS, …). Survey-row transcription is handled deterministically
    by ``_extract_survey_rows`` running over the same markdown — a CPU-bound
    model takes 10+ minutes to output 100+ JSON rows, while regex finishes in
    milliseconds.

    We still merge in any ``surveys`` the model happens to return — if rules
    fail and the LLM produces a short table, that's a free bonus.
    """
    trimmed = _trim_to_survey_region(markdown)

    # Inject a deterministic survey extraction from the FULL markdown so the
    # caller of llm_extract sees rows even when the LLM omits them. We import
    # locally to avoid a circular import with parser.py.
    from etools.core.pdf.parser import _extract_survey_rows

    rows_df = _extract_survey_rows(markdown)
    deterministic_rows = [
        LLMSurveyRow(
            measured_depth_ft=float(r.MeasuredDepth),
            inclination_deg=float(r.Inclination),
            azimuth_deg=float(r.Azimuth),
        )
        for r in rows_df.itertuples()
    ]
    log.info(
        "llm.extract.prompt",
        original_chars=len(markdown),
        kept_chars=len(trimmed),
        deterministic_rows=len(deterministic_rows),
    )

    prompt = (
        "Extract directional-survey METADATA from this PDF (rendered as "
        "Markdown by Docling). Focus on well identification and surface "
        "location fields only — well name, API number, operator, surface "
        "latitude/longitude (decimal degrees, western longitudes negative), "
        "surface elevation in feet, north reference (true/grid/magnetic), "
        "grid convergence, magnetic declination, PLSS legal description.\n\n"
        "For the `surveys` field, return an empty list — survey rows are "
        "transcribed by a separate deterministic parser. Do NOT spend output "
        "tokens transcribing the MD/INC/AZI table.\n\n"
        f"<<<DOCUMENT>>>\n{trimmed}\n<<<END>>>\n"
    )
    result = extract_with_schema(
        prompt,
        LLMSurveyExtraction,
        client=client,
        system=_SYSTEM_PROMPT,
    )
    # Merge in the deterministic rows so callers see them regardless of mode.
    if not result.surveys and deterministic_rows:
        result.surveys = deterministic_rows
    return result


# Patterns that mark survey-relevant regions in the markdown.
_RELEVANT_PATTERNS = [
    re.compile(r"\bMD\s*\(?ft", re.I),
    re.compile(r"\bMeasured\s+Depth\b", re.I),
    re.compile(r"\bInclination\b", re.I),
    re.compile(r"\bAzim", re.I),
    re.compile(r"\bSurface\s+Location\b", re.I),
    re.compile(r"\bLat(?:itude)?\b", re.I),
    re.compile(r"\bLon(?:gitude)?\b", re.I),
    re.compile(r"\bElevation\b", re.I),
    re.compile(r"\bMagDec|Magnetic\s+Declination", re.I),
    re.compile(r"\bGrid\s+Conv", re.I),
    re.compile(r"\bWell\s*Name", re.I),
    re.compile(r"\bAPI\s*(?:Number|No|#)?", re.I),
    re.compile(r"\bOperator\b", re.I),
    re.compile(r"NWNW|NWNE|NENW|NENE|SWNW|SWNE|SENW|SENE|NWSW|NWSE|NESW|NESE|SWSW|SWSE|SESW|SESE", re.I),
]


_SURVEY_TABLE_HEADER_RE = re.compile(
    r"\bMD\s*\(?ft\)?.{0,200}?\bInc.{0,200}?\bAzim",
    re.I | re.DOTALL,
)


def _trim_to_survey_region(markdown: str, *, target_chars: int = 20_000) -> str:
    """Pull out the section of the markdown that actually contains the survey
    table.

    Real-world operator PDFs frequently include 2–3 unrelated "MD(ft)" tables
    (formation tops, casing depths) before the actual MD/INC/AZI survey
    listing. We anchor on the first place where MD, Inc, AND Azim all
    co-occur within a ~400-char window — that's the survey table header —
    and slice a ``target_chars``-wide window centered on it. If we can't find
    that, we fall back to a metadata-only window from the top of the doc.
    """
    if len(markdown) <= target_chars:
        return markdown

    anchor = _SURVEY_TABLE_HEADER_RE.search(markdown)
    if anchor is not None:
        # The rows that follow the header are what matters. Take a small
        # lead-in for metadata that often appears just above the table
        # (well name, lat/lon, KB elevation), then dump everything from
        # the header onwards up to ``target_chars``.
        lead = 400
        start = max(0, anchor.start() - lead)
        end = min(len(markdown), start + target_chars)
        return markdown[start:end]

    # No survey header found anywhere — return a metadata-rich slice using
    # the earliest set of keyword hits.
    hits: list[int] = []
    for pat in _RELEVANT_PATTERNS:
        for m in pat.finditer(markdown):
            hits.append(m.start())
    if not hits:
        return markdown[:target_chars]
    hits.sort()
    start = max(0, min(hits) - 500)
    return markdown[start : start + target_chars]


def llm_extract_from_image(
    images: list[bytes], *, client: OllamaClient | None = None
) -> LLMSurveyExtraction:
    """Vision path — for fully scanned PDFs where Docling+OCR still struggles."""
    prompt = (
        "This is one page from a directional well survey or APD packet. "
        "Look carefully for a table with columns Measured Depth (MD), "
        "Inclination (INC), and Azimuth (AZI). Transcribe EVERY row of that "
        "table into the `surveys` array — do not skip rows or summarise. "
        "Also extract any well-identification fields visible (well name, API, "
        "operator, surface latitude/longitude, surface elevation, north "
        "reference, magnetic declination, grid convergence, PLSS legal). "
        "If the page does not contain a survey table, return an empty `surveys` "
        "array but still fill in any identification fields you can see."
    )
    return extract_with_schema(
        prompt,
        LLMSurveyExtraction,
        client=client,
        system=_SYSTEM_PROMPT,
        images=images,
    )
