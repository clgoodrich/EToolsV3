"""ClearanceService — orchestrates plat lookup → spatial join → footage math."""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import pandas as pd

from etools.core.clearance import calculate_clearances
from etools.core.plat import locate_points
from etools.logging_setup import get_logger
from etools.models import ProcessedSurvey
from etools.repositories import PlatRepository

log = get_logger(__name__)


@dataclass(slots=True)
class ClearanceResult:
    """Per-survey clearance output."""

    citing_type: str
    points: pd.DataFrame  # processed survey + Conc/label/FNL/FSL/FEL/FWL
    sections: gpd.GeoDataFrame
    summary: pd.DataFrame  # FNL/FSL/FEL/FWL at SHL/KOP/Landing/BHL


class ClearanceService:
    def __init__(self, plat_repo: PlatRepository | None = None) -> None:
        self.plat_repo = plat_repo or PlatRepository()

    def calculate(
        self,
        processed: ProcessedSurvey,
        *,
        kop_md: float | None = None,
        landing_md: float | None = None,
    ) -> ClearanceResult:
        """Run plat lookup + clearance for a single processed survey."""
        df = processed.points
        log.debug(
            "clearance.calculate.entry",
            citing=processed.citing_type.value,
            points=len(df),
            cols=list(df.columns) if not df.empty else [],
            kop_md=kop_md,
            landing_md=landing_md,
        )
        if df.empty:
            log.warning("clearance.calculate.empty_input", citing=processed.citing_type.value)
            return ClearanceResult(
                citing_type=processed.citing_type.value,
                points=df,
                sections=gpd.GeoDataFrame(),
                summary=pd.DataFrame(),
            )

        log.debug("clearance.step.fetch_bbox.start", citing=processed.citing_type.value)
        bundle = self.plat_repo.fetch_for_trajectory(
            df["easting"], df["northing"], buffer_m=2000
        )
        log.debug(
            "clearance.step.fetch_bbox.done",
            citing=processed.citing_type.value,
            section_count=len(bundle.sections),
        )

        log.debug("clearance.step.locate.start", citing=processed.citing_type.value)
        located = locate_points(df, bundle.sections)
        log.debug(
            "clearance.step.locate.done",
            citing=processed.citing_type.value,
            rows=len(located),
            cols=list(located.columns),
        )

        log.debug("clearance.step.calculate.start", citing=processed.citing_type.value)
        with_clearance = calculate_clearances(located, bundle.sections)
        log.debug(
            "clearance.step.calculate.done",
            citing=processed.citing_type.value,
            rows=len(with_clearance),
            cols=list(with_clearance.columns),
        )

        log.debug("clearance.step.summary.start", citing=processed.citing_type.value)
        summary = self._build_summary(with_clearance, kop_md=kop_md, landing_md=landing_md)
        log.debug(
            "clearance.step.summary.done",
            citing=processed.citing_type.value,
            summary_rows=len(summary),
        )
        log.info(
            "clearance.summary",
            citing=processed.citing_type.value,
            points=len(with_clearance),
            shl_section=summary.iloc[0]["label"] if not summary.empty else None,
        )
        return ClearanceResult(
            citing_type=processed.citing_type.value,
            points=with_clearance,
            sections=bundle.sections,
            summary=summary,
        )

    @staticmethod
    def _build_summary(
        df: pd.DataFrame,
        *,
        kop_md: float | None,
        landing_md: float | None,
    ) -> pd.DataFrame:
        """Pull a footage row at each significant station: SHL / KOP / Landing / BHL."""
        if df.empty:
            return df

        rows: list[dict] = []
        rows.append(_pick_row(df, df["measured_depth"].iloc[0], "SHL"))
        if kop_md is not None:
            rows.append(_pick_row(df, kop_md, "KOP"))
        if landing_md is not None:
            rows.append(_pick_row(df, landing_md, "Landing"))
        rows.append(_pick_row(df, df["measured_depth"].iloc[-1], "BHL"))

        out_cols = ["location", "measured_depth", "azimuth", "label", "FNL", "FSL", "FEL", "FWL"]
        return pd.DataFrame([r for r in rows if r is not None])[out_cols]


def _pick_row(df: pd.DataFrame, target_md: float, location_label: str) -> dict | None:
    """Find the row with measured_depth closest to ``target_md`` and tag it."""
    if df.empty:
        return None
    idx = (df["measured_depth"] - target_md).abs().idxmin()
    src = df.loc[idx]
    return {
        "location": location_label,
        "measured_depth": float(src["measured_depth"]),
        "azimuth": float(src.get("azimuth")) if pd.notna(src.get("azimuth")) else None,
        "label": src.get("label"),
        "FNL": _to_float(src.get("FNL")),
        "FSL": _to_float(src.get("FSL")),
        "FEL": _to_float(src.get("FEL")),
        "FWL": _to_float(src.get("FWL")),
    }


def _to_float(v) -> float | None:
    return float(v) if v is not None and pd.notna(v) else None
