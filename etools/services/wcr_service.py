"""WCRService — legacy DB-driven WCR generation.

Kept for the existing UI flow that loads a bundle from SQL Server and uses
a clearance summary as the location source. The new primary path is
``WCRPdfService`` (PDF + surveys → 14-row WCR Excel); this service maps
the legacy ``FootageSummary`` rows (SHL/KOP/Landing/BHL) onto the same
output schema as best it can.

Naming mapping (legacy → new):
    SHL     → SHL
    KOP     → Control_Point
    Landing → Frac_Start  (only when no perf table is available)
    BHL     → BHL

When the bundle carries perforation records (vwDM_ConstructPerf) and the
caller passes the full clearance ``points`` frame, Frac_Start / Frac_End
are anchored to the actual perf top/bottom MDs instead — same convention
as the PDF pipeline. The perf block (E1:G2) and the casing/cement table
(row 16+) are written from the bundle, matching the hand-made workbooks.
"""

from __future__ import annotations

import re
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

# "14 2S 5W U" — the plat repository's section label format.
_LABEL_RE = re.compile(r"^\s*(\d+)\s+(\d+)([NS])\s+(\d+)([EW])\s+(\w)\s*$", re.I)


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
        points: pd.DataFrame | None = None,
        output_dir: str | Path | None = None,
    ) -> Path:
        """``points`` is the full clearance points frame (every survey station
        with tvd/easting/northing/footages/label). When provided alongside DB
        perforations, the Frac rows are picked from it at the perf MDs."""
        bundle = bundle or self.load_bundle(api, lateral)
        if bundle.info is None:
            raise ValueError("Cannot generate WCR: no well info available.")
        info = bundle.info
        target_dir = Path(output_dir) if output_dir else Path(settings.output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = (info.well_name or info.api_well_no).replace(" ", "_").replace("/", "-")
        out_path = target_dir / f"{safe_name}_{info.api_well_no[:10]}_WCR.xlsx"

        # The processed trajectory's TVD is absolute (elevation + depth);
        # the WCR convention wants depth below surface.
        tvd_offset = info.elevation_ft or 0.0

        perf_top, perf_bottom, perf_date = _perf_summary(bundle.perforations)
        rows = self._translate_summary(summary_footages, tvd_offset=tvd_offset)

        if points is not None and not points.empty and perf_top is not None:
            # Replace the Landing approximation with real perf-anchored rows.
            rows = [r for r in rows if r.name not in ("Frac_Start", "Frac_End")]
            rows.append(_row_from_points(points, perf_top, "Frac_Start", tvd_offset))
            if perf_bottom is not None:
                rows.append(_row_from_points(points, perf_bottom, "Frac_End", tvd_offset))
        elif not any(r.name == "Frac_End" for r in rows):
            # No perf data at all — reuse BHL so Frac_End isn't blank.
            bhl = next((r for r in rows if r.name == "BHL"), None)
            if bhl is not None:
                rows.append(bhl.model_copy(update={"name": "Frac_End"}))

        path = generate_wcr_excel(
            info=info,
            location_rows=rows,
            output_path=out_path,
            perf_top_md=perf_top,
            perf_bottom_md=perf_bottom,
            perf_date=perf_date,
            casing=bundle.casing,
        )
        log.info("wcr.generated", path=str(path))
        return path

    @staticmethod
    def _translate_summary(
        summary: pd.DataFrame, *, tvd_offset: float = 0.0
    ) -> list[WCRLocationRow]:
        if summary is None or summary.empty:
            return []
        rows: list[WCRLocationRow] = []
        for _, src in summary.iterrows():
            legacy_name = str(src.get("location", ""))
            mapped = _LOCATION_MAP.get(legacy_name, legacy_name)
            rows.append(_make_row(src, mapped, tvd_offset))
        return rows


def _make_row(src, name: str, tvd_offset: float) -> WCRLocationRow:
    plss = _parse_label(src.get("label")) if pd.isna(src.get("Section", None)) or src.get("Section") is None else {}
    tvd = _to_float(src.get("tvd"))
    return WCRLocationRow(
        name=name,
        measured_depth=_to_float(src.get("measured_depth")) or 0.0,
        tvd=(tvd - tvd_offset) if tvd is not None else 0.0,
        easting=_to_float(src.get("easting")) or 0.0,
        northing=_to_float(src.get("northing")) or 0.0,
        fnl=_to_float(src.get("FNL")),
        fsl=_to_float(src.get("FSL")),
        fel=_to_float(src.get("FEL")),
        fwl=_to_float(src.get("FWL")),
        section=_to_str(src.get("Section")) or plss.get("section"),
        township=_to_str(src.get("Township")) or plss.get("township"),
        township_dir=_to_str(src.get("Township_Direction")) or plss.get("township_dir"),
        range=_to_str(src.get("Range")) or plss.get("range"),
        range_dir=_to_str(src.get("Range_Direction")) or plss.get("range_dir"),
        baseline=_to_str(src.get("Baseline")) or plss.get("baseline"),
    )


def _row_from_points(points: pd.DataFrame, target_md: float, name: str, tvd_offset: float) -> WCRLocationRow:
    """Pick the survey station nearest ``target_md`` from the clearance frame."""
    idx = (points["measured_depth"] - target_md).abs().idxmin()
    return _make_row(points.loc[idx], name, tvd_offset)


def _parse_label(label) -> dict[str, str]:
    """``"14 2S 5W U"`` → section/township/range parts. Empty dict if malformed."""
    if not isinstance(label, str):
        return {}
    m = _LABEL_RE.match(label)
    if not m:
        return {}
    sec, twp, twp_dir, rng, rng_dir, baseline = m.groups()
    return {
        "section": sec,
        "township": twp,
        "township_dir": twp_dir.upper(),
        "range": rng,
        "range_dir": rng_dir.upper(),
        "baseline": baseline.upper(),
    }


def _perf_summary(perfs: pd.DataFrame | None) -> tuple[float | None, float | None, str | None]:
    """(top MD, bottom MD, latest perf date "m/d/YYYY") from the repository frame.

    The vwDM_ConstructPerf view mixes actual perforations with formation
    tops (which carry 0/0 intervals) — only Zone Type = Perforations counts.
    """
    if perfs is None or perfs.empty:
        return None, None, None
    if "ZoneType" in perfs.columns:
        perfs = perfs[perfs["ZoneType"].astype(str).str.strip().str.lower() == "perforations"]
    if perfs.empty:
        return None, None, None
    tops = pd.to_numeric(perfs.get("Top_MD", pd.Series(dtype=float)), errors="coerce")
    bottoms = pd.to_numeric(perfs.get("Bottom_MD", pd.Series(dtype=float)), errors="coerce")
    top = _to_float(tops[tops > 0].min())
    bottom = _to_float(bottoms[bottoms > 0].max())
    date_str = None
    if "PerfDate" in perfs.columns:
        dates = pd.to_datetime(perfs["PerfDate"], errors="coerce").dropna()
        if not dates.empty:
            d = dates.max()
            date_str = f"{d.month}/{d.day}/{d.year}"
    return top, bottom, date_str


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
