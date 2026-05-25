"""LLM-driven structured extraction for APD (DOGM Form 3) PDFs.

Companion to ``apd_parser.py``. The rules layer handles every clean
machine-generated APD we've seen (4/4 in the test corpus), but older
scanned forms and any format the operator submits as a flattened image
need the LLM fallback.

Usage pattern mirrors ``llm_wcr_extract``: call
``llm_apd_extract(text, client=...)`` to fill the schema and feed the
result back into ``apd_parser._merge_llm`` (TODO once the rules layer
exposes that hook).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from etools.core.llm import OllamaClient, extract_with_schema
from etools.logging_setup import get_logger

log = get_logger(__name__)


class LLMApdLocation(BaseModel):
    name: str = Field(
        description=(
            "One of: 'Location At Surface', 'Top of Uppermost Producing Zone', "
            "'At Total Depth'."
        )
    )
    fnl: Optional[float] = None
    fsl: Optional[float] = None
    fel: Optional[float] = None
    fwl: Optional[float] = None
    qtr_qtr: Optional[str] = Field(
        None, description="Quarter-quarter, e.g. 'SESE' or 'LOT2'"
    )
    section: Optional[str] = None
    township: Optional[str] = None
    township_dir: Optional[str] = None  # 'N' or 'S'
    range: Optional[str] = None
    range_dir: Optional[str] = None  # 'E' or 'W'
    meridian: Optional[str] = Field(None, description="Single letter, e.g. 'U' for Uintah")


class LLMApdCasing(BaseModel):
    tag: str = Field(
        description="String tag: 'Cond', 'Surf', 'I1', 'I2', 'I3', 'Prod', 'Liner'."
    )
    hole_size_in: Optional[float] = None
    casing_size_in: Optional[float] = None
    length_top_ft: Optional[float] = None
    length_bottom_ft: Optional[float] = None
    weight_ppf: Optional[float] = None
    grade: Optional[str] = Field(
        None, description="e.g. 'J-55', 'P-110' — no thread suffix"
    )
    collar: Optional[str] = Field(
        None, description="Connection type: 'BTC', 'STC', 'LTC', 'PE', 'CDC', etc."
    )
    max_mud_weight_ppg: Optional[float] = None
    cement_lead_type: Optional[str] = None
    cement_lead_sacks: Optional[int] = None
    cement_lead_yield: Optional[float] = None
    cement_lead_weight_ppg: Optional[float] = None
    cement_tail_type: Optional[str] = None
    cement_tail_sacks: Optional[int] = None
    cement_tail_yield: Optional[float] = None
    cement_tail_weight_ppg: Optional[float] = None


class LLMApdFormationTop(BaseModel):
    name: str
    tvd_ft: Optional[float] = None
    md_ft: Optional[float] = None


class LLMApdExtraction(BaseModel):
    well_name: Optional[str] = None
    api_number: Optional[str] = Field(None, description="10-digit API, digits only")
    operator: Optional[str] = None
    field_name: Optional[str] = None
    county: Optional[str] = None
    well_type: Optional[str] = None
    slant: Optional[str] = Field(None, description="VERTICAL / DIRECTIONAL / HORIZONTAL")
    proposed_md_ft: Optional[float] = None
    proposed_tvd_ft: Optional[float] = None
    ground_elev_ft: Optional[float] = None
    frac_gradient_psi_per_ft: Optional[float] = Field(
        None,
        description=(
            "Fracture gradient at production-shoe TVD, psi/ft. If the PDF "
            "shows it in ppg, multiply by 0.05194806 to convert."
        ),
    )
    locations: list[LLMApdLocation] = Field(default_factory=list)
    casing: list[LLMApdCasing] = Field(default_factory=list)
    formations: list[LLMApdFormationTop] = Field(default_factory=list)


_SYSTEM_PROMPT = (
    "You are an oil & gas regulatory analyst extracting structured data "
    "from a DOGM (Utah) Form 3 — Application for Permit to Drill. You "
    "understand:\n"
    "  - Section 20's three location rows (surface / top of producing / TD) "
    "and how FNL/FSL/FEL/FWL footages relate to quarter-quarter codes.\n"
    "  - The Hole, Casing, and Cement Information table — each row is one "
    "casing string with two cement stages (lead and tail).\n"
    "  - Casing connection types ('BTC' = buttress, 'STC' = short-thread "
    "coupling, 'LTC' = long-thread coupling, etc.).\n"
    "  - Formation tops on page 2 reported as TVD/MD pairs.\n"
    "Be exact with numbers. Leave fields null when uncertain. Never invent."
)


def llm_apd_extract(text: str, *, client: OllamaClient | None = None) -> LLMApdExtraction:
    """Send ``text`` (typically PyMuPDF or Docling output) to the LLM and
    return a parsed ``LLMApdExtraction``. Raises if the LLM is unreachable.
    """
    cli = client or OllamaClient()
    if not cli.health() or not cli.has_model():
        raise RuntimeError(
            "Ollama is not reachable or the configured model is missing"
        )
    prompt = (
        "Extract the well metadata, location rows, casing strings, and "
        "formation tops from this APD PDF text. Use null for any field you "
        "cannot find or are unsure about.\n\n"
        "----- BEGIN PDF TEXT -----\n"
        + text[:60000]  # 60 KB cap keeps prompt under CPU-inference limits
        + "\n----- END PDF TEXT -----\n"
    )
    return extract_with_schema(
        prompt, LLMApdExtraction, client=cli, system=_SYSTEM_PROMPT
    )
