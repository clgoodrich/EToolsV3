"""Build a fully-computed ``CasingDesign`` from APD + survey inputs.

The engine is the single source of truth: it owns the catalog lookup,
TVD-at-MD interpolation against the welltrack, and the cross-string
linking that makes MASP / burst-load formulas resolve. Once it returns
a ``CasingDesign`` every downstream consumer (Excel writer, UI panels,
Vertical WBD chart, JSON export) just reads computed properties.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

import pandas as pd

from etools.core.casing_review.catalog import CasingCatalog
from etools.core.casing_review.domain import CasingDesign, CasingStringDesign
from etools.logging_setup import get_logger
from etools.models import APDCasingString, APDPdfData

log = get_logger(__name__)


# Mapping APD casing tags → human-readable string labels and ordinal index
# into the Casing Review's 4 STRING blocks (Surface / Intermediate /
# Production / Liner).
_TAG_TO_LABEL = {
    "Cond": ("Conductor", -1),
    "Surf": ("Surface", 0),
    "I1": ("Intermediate", 1),
    "I2": ("Intermediate 2", 2),
    "I3": ("Intermediate 3", 3),
    "Prod": ("Production", 2),
    "Prod1": ("Production", 2),
    "Prod2": ("Production 2", 3),
    "Liner": ("Liner", 3),
}


@dataclass
class WelltrackPoint:
    md_ft: float
    tvd_ft: float


class CasingDesignEngine:
    """Build CasingDesigns. Catalog is cached across calls."""

    def __init__(self, catalog: CasingCatalog | None = None) -> None:
        self._catalog = catalog or CasingCatalog()

    def build(
        self,
        apd: APDPdfData,
        welltrack: list[WelltrackPoint] | None = None,
    ) -> CasingDesign:
        design = CasingDesign(
            company=apd.operator,
            well_name=apd.well_name,
            api=apd.api,
            frac_gradient_psi_per_ft=apd.frac_gradient_psi_per_ft or 1.0,
        )
        # When no real welltrack is provided, synthesise a 2-point fallback
        # using the APD's proposed (MD, TVD) and a 1:1 vertical from surface.
        # This is enough for vertical strings to match the spreadsheet and
        # keeps the production string from claiming TVD = MD (which inflates
        # collapse/burst loads on horizontal wells).
        if not welltrack and apd.proposed_md_ft and apd.proposed_tvd_ft:
            welltrack = _synthetic_welltrack(
                apd.proposed_md_ft, apd.proposed_tvd_ft
            )

        # Skip Conductor — engineering review covers Surface and deeper.
        slots: list[CasingStringDesign | None] = [None] * 4
        for cs in apd.casing:
            mapping = _TAG_TO_LABEL.get(cs.tag)
            if mapping is None:
                continue
            label, idx = mapping
            if idx < 0 or idx >= 4 or slots[idx] is not None:
                continue
            slots[idx] = self._build_string(cs, label, welltrack, idx == 0)
        design.strings = [s for s in slots if s is not None]
        design.finalize()
        return design

    def _build_string(
        self,
        cs: APDCasingString,
        label: str,
        welltrack: list[WelltrackPoint] | None,
        is_surface: bool,
    ) -> CasingStringDesign:
        set_depth = cs.length_bottom_ft or 0.0
        tvd = (
            _interpolate_tvd(welltrack, set_depth)
            if welltrack
            else set_depth  # vertical assumption
        )
        s = CasingStringDesign(
            label=label,
            hole_size_in=cs.hole_size_in or 0.0,
            od_in=cs.casing_size_in or 0.0,
            set_depth_md_ft=set_depth,
            set_depth_tvd_ft=tvd,
            weight_ppf=cs.weight_ppf or 0.0,
            grade=cs.grade or "",
            collar=cs.collar,
            cement_lead_sacks=cs.cement_lead_sacks,
            cement_lead_yield=cs.cement_lead_yield,
            cement_lead_weight_ppg=cs.cement_lead_weight_ppg,
            cement_tail_sacks=cs.cement_tail_sacks,
            cement_tail_yield=cs.cement_tail_yield,
            cement_tail_weight_ppg=cs.cement_tail_weight_ppg,
            mud_weight_ppg=cs.max_mud_weight_ppg or 9.0,
            hole_washout_pct=10.0 if is_surface else 4.0,
            internal_gradient_psi_per_ft=0.12 if is_surface else 0.22,
            backup_mud_ppg=0.0,
            internal_mud_ppg=0.0,
            buoyed=True,
        )

        # Catalog lookup — match on OD + weight + grade (+ collar if known).
        if s.od_in > 0 and s.weight_ppf > 0 and s.grade:
            rec = self._catalog.lookup(
                od_in=s.od_in,
                weight_ppf=s.weight_ppf,
                grade=s.grade,
                collar=s.collar,
            )
            if rec is None and s.collar:
                # Fall back to grade-only lookup if the connection isn't catalogued.
                rec = self._catalog.lookup(
                    od_in=s.od_in, weight_ppf=s.weight_ppf, grade=s.grade
                )
            if rec is not None:
                s.collapse_psi = rec.collapse_psi
                s.burst_psi = rec.burst_psi
                s.joint_klbs = rec.joint_klbs
                s.body_klbs = rec.body_klbs
                s.id_in = rec.id_in
            else:
                log.warning(
                    "casing.catalog.miss",
                    od=s.od_in, weight=s.weight_ppf,
                    grade=s.grade, collar=s.collar,
                )

        return s


# ---------------------------------------------------------------------------
# Welltrack helpers
# ---------------------------------------------------------------------------


def welltrack_from_processed_survey(processed) -> list[WelltrackPoint]:
    """Convert a ``ProcessedSurvey`` into the minimal MD/TVD point list."""
    from etools.models import SurveyFrame

    points = processed.frames[SurveyFrame.TRUE].points
    return [WelltrackPoint(md_ft=p.md, tvd_ft=p.tvd) for p in points]


def welltrack_from_dataframe(df: pd.DataFrame) -> list[WelltrackPoint]:
    """Best-effort conversion from an arbitrary survey DataFrame.

    Looks for columns named ``md`` / ``tvd`` (case-insensitive). For
    full-precision min-curvature interpolation use the processed survey.
    """
    cols = {c.lower(): c for c in df.columns}
    md_col = cols.get("md") or cols.get("md_ft")
    tvd_col = cols.get("tvd") or cols.get("tvd_ft")
    if not md_col or not tvd_col:
        return []
    return [
        WelltrackPoint(md_ft=float(r[md_col]), tvd_ft=float(r[tvd_col]))
        for _, r in df.iterrows()
        if pd.notna(r[md_col]) and pd.notna(r[tvd_col])
    ]


def _synthetic_welltrack(
    proposed_md_ft: float, proposed_tvd_ft: float
) -> list[WelltrackPoint]:
    """2-segment welltrack: vertical to ``proposed_tvd``, then build/hold
    to ``proposed_md`` at constant TVD. Good enough to keep production-
    string burst/collapse from blowing up when no real survey is loaded.
    """
    if proposed_md_ft <= proposed_tvd_ft:
        return [
            WelltrackPoint(md_ft=0.0, tvd_ft=0.0),
            WelltrackPoint(md_ft=proposed_md_ft, tvd_ft=proposed_md_ft),
        ]
    return [
        WelltrackPoint(md_ft=0.0, tvd_ft=0.0),
        WelltrackPoint(md_ft=proposed_tvd_ft, tvd_ft=proposed_tvd_ft),
        WelltrackPoint(md_ft=proposed_md_ft, tvd_ft=proposed_tvd_ft),
    ]


def _interpolate_tvd(
    welltrack: list[WelltrackPoint], target_md: float
) -> float | None:
    """Linear-interpolate TVD at ``target_md`` along ``welltrack``."""
    if not welltrack:
        return None
    mds = [p.md_ft for p in welltrack]
    if target_md <= mds[0]:
        return welltrack[0].tvd_ft
    if target_md >= mds[-1]:
        return welltrack[-1].tvd_ft
    idx = bisect.bisect_left(mds, target_md)
    a = welltrack[idx - 1]
    b = welltrack[idx]
    if b.md_ft == a.md_ft:
        return a.tvd_ft
    t = (target_md - a.md_ft) / (b.md_ft - a.md_ft)
    return a.tvd_ft + t * (b.tvd_ft - a.tvd_ft)
