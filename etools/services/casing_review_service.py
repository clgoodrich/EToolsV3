"""Orchestrate APD parsing + casing design + Excel generation.

Two generation paths:
    * ``generate_template_only``  — legacy template fill (raw APD values).
    * ``generate``                — full pipeline through the calc engine,
                                    optionally consuming a directional
                                    survey to compute TVD at each casing
                                    set depth.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from etools.config import settings
from etools.core.casing_review.engine import (
    CasingDesignEngine,
    WelltrackPoint,
    welltrack_from_dataframe,
    welltrack_from_processed_survey,
)
from etools.core.casing_review.domain import CasingDesign
from etools.core.casing_review.writer import write_casing_review
from etools.core.pdf.apd_parser import parse_apd_pdf
from etools.logging_setup import get_logger
from etools.models import APDPdfData

log = get_logger(__name__)


@dataclass
class CasingReviewResult:
    output_path: Path
    apd_data: APDPdfData
    design: CasingDesign


class CasingReviewService:
    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = Path(output_dir or settings.output_dir)
        self._engine = CasingDesignEngine()

    def generate(
        self,
        *,
        apd_pdf_path: str | Path | None = None,
        apd_data: APDPdfData | None = None,
        survey: pd.DataFrame | None = None,
        processed_survey=None,
        output_filename: str | None = None,
        frac_gradient_override_psi_per_ft: float | None = None,
    ) -> CasingReviewResult:
        if apd_data is None:
            if not apd_pdf_path:
                raise ValueError("Need either apd_pdf_path or apd_data")
            apd_data = parse_apd_pdf(apd_pdf_path)

        if frac_gradient_override_psi_per_ft is not None:
            apd_data.frac_gradient_psi_per_ft = frac_gradient_override_psi_per_ft

        # Welltrack precedence: ProcessedSurvey (best, min-curvature)
        # → raw DataFrame (good if it carries MD/TVD) → synthetic from APD.
        welltrack: list[WelltrackPoint] | None = None
        if processed_survey is not None:
            welltrack = welltrack_from_processed_survey(processed_survey)
        elif survey is not None and not survey.empty:
            welltrack = welltrack_from_dataframe(survey)

        design = self._engine.build(apd_data, welltrack=welltrack)

        out_name = output_filename or self._default_filename(apd_data)
        out_path = self.output_dir / out_name
        locations = {L.name.lower(): L for L in apd_data.locations}
        surface_loc = locations.get("location at surface")
        producing_loc = locations.get("top of uppermost producing zone")
        td_loc = locations.get("at total depth")
        write_casing_review(
            design,
            out_path,
            surface_location=surface_loc,
            producing_interval_location=producing_loc,
            td_location=td_loc,
        )
        log.info(
            "casing_review.generated",
            path=str(out_path),
            api=apd_data.api,
            strings=len(design.strings),
            had_welltrack=welltrack is not None,
        )
        return CasingReviewResult(
            output_path=out_path,
            apd_data=apd_data,
            design=design,
        )

    def _default_filename(self, apd: APDPdfData) -> str:
        api = (apd.api or "unknown")[:14]
        name = apd.well_name or "Casing_Review"
        safe = "".join(c if c.isalnum() or c in " -_." else "_" for c in name)
        return f"Casing Review_{api}_{safe}.xlsx"
