"""WCRService — legacy DB-driven WCR generation.

Kept for the existing UI flow that loads a bundle from SQL Server and uses
a clearance summary as the location source. The new primary path is
``WCRPdfService`` (PDF + surveys → 14-row WCR Excel); this service maps
the legacy ``FootageSummary`` rows (SHL/KOP/Landing/BHL) onto the same
output schema as best it can.

Naming mapping (legacy → new):
    SHL     → SHL
    KOP     → Control_Point
    Landing → Frac_Start  (best approximation when no perf table available)
    BHL     → BHL  AND  Frac_End  (no separate perf data)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from etools.config import settings
from etools.core.wcr import generate_wcr_excel
from etools.logging_setup import get_logger
from etools.models import WCRBundle, WCRLocationRow
from etools.repositories import WCRRepository

log = get_logger(__name__)


_LOCATION_MAP = {
    "SHL": "SHL",
    "KOP": "Control_Point",
    "Landing": "Frac_Start",
    "BHL": "BHL",
}


class WCRService:
    def __init__(self, repo: WCRRepository | None = None) -> None:
        self.repo = repo or WCRRepository()

    def load_bundle(self, api: str, lateral: str = "0000") -> WCRBundle:
        return self.repo.get_bundle(api, lateral)

    def generate(
        self,
        *,
        api: str,
        lateral: str,
        summary_footages: pd.DataFrame,
        bundle: WCRBundle | None = None,
        output_dir: str | Path | None = None,
    ) -> Path:
        bundle = bundle or self.load_bundle(api, lateral)
        if bundle.info is None:
            raise ValueError("Cannot generate WCR: no well info available.")
        info = bundle.info
        target_dir = Path(output_dir) if output_dir else Path(settings.output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = (info.well_name or info.api_well_no).replace(" ", "_").replace("/", "-")
        out_path = target_dir / f"{safe_name}_{info.api_well_no[:10]}_WCR.xlsx"

        rows = self._translate_summary(summary_footages)
        path = generate_wcr_excel(info=info, location_rows=rows, output_path=out_path)
        log.info("wcr.generated", path=str(path))
        return path

    @staticmethod
    def _translate_summary(summary: pd.DataFrame) -> list[WCRLocationRow]:
        if summary is None or summary.empty:
            return []
        rows: list[WCRLocationRow] = []
        bhl_row: WCRLocationRow | None = None
        for _, src in summary.iterrows():
            legacy_name = str(src.get("location", ""))
            mapped = _LOCATION_MAP.get(legacy_name, legacy_name)
            row = WCRLocationRow(
                name=mapped,
                measured_depth=_to_float(src.get("measured_depth")) or 0.0,
                tvd=_to_float(src.get("tvd")) or 0.0,
                easting=_to_float(src.get("easting")) or 0.0,
                northing=_to_float(src.get("northing")) or 0.0,
                fnl=_to_float(src.get("FNL")),
                fsl=_to_float(src.get("FSL")),
                fel=_to_float(src.get("FEL")),
                fwl=_to_float(src.get("FWL")),
                section=_to_str(src.get("Section")),
                township=_to_str(src.get("Township")),
                township_dir=_to_str(src.get("Township_Direction")),
                range=_to_str(src.get("Range")),
                range_dir=_to_str(src.get("Range_Direction")),
                baseline=_to_str(src.get("Baseline")),
            )
            rows.append(row)
            if mapped == "BHL":
                bhl_row = row
        # No real perf-end MD available from the legacy summary — reuse BHL
        # so the Frac_End row in the Excel isn't blank.
        if bhl_row is not None and not any(r.name == "Frac_End" for r in rows):
            rows.append(bhl_row.model_copy(update={"name": "Frac_End"}))
        return rows


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_str(v) -> str | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)
