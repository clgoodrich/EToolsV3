"""WCRPdfService — generate a WCR Excel from a WCR PDF + directional surveys.

Pipeline:

    PDF  ──► parse_wcr_pdf       ► header + perf stages + position rows
                                    │
                                    │   surface lat/lon (UTM in WCRPdfData)
                                    ▼
    raw survey ──► process_survey ► trajectory in UTM12N
                                    │
                                    │   detect_kop, perf MDs, TD
                                    ▼
                  interpolate_at_md  for each of {SHL, Control_Point,
                                                  Frac_Start, Frac_End, BHL}
                                    │
                                    ▼
                  locate_points + calculate_clearances
                                    │
                                    ▼
                  WCRLocationRow[]
                                    │
                                    ▼
                  generate_wcr_excel
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from etools.config import settings
from etools.core.clearance import calculate_clearances
from etools.core.coordinates import utm_to_latlon
from etools.core.pdf.wcr_parser import parse_wcr_pdf
from etools.core.plat import locate_points
from etools.core.survey.kop import detect_kop, detect_kop_simple
from etools.core.survey.processor import interpolate_at_md, process_survey
from etools.core.wcr import generate_wcr_excel
from etools.logging_setup import get_logger
from etools.models import (
    SurveyFrame,
    WCRLocationRow,
    WCRPdfData,
    WCRWellInfo,
)
from etools.repositories import PlatRepository

log = get_logger(__name__)


@dataclass(slots=True)
class WCRPdfResult:
    """What WCRPdfService.generate() returns — the saved path plus the rows
    that were written, plus the trajectory / section / elevation cache the
    UI uses to cascade edits without re-parsing the PDF or re-processing
    the survey."""

    output_path: Path
    pdf_data: WCRPdfData
    location_rows: list[WCRLocationRow]
    # Cache for cascade-on-edit:
    points: pd.DataFrame = field(default_factory=pd.DataFrame)
    sections: gpd.GeoDataFrame | None = None
    elevation_ft: float = 0.0


class WCRPdfService:
    def __init__(self, plat_repo: PlatRepository | None = None) -> None:
        self.plat_repo = plat_repo or PlatRepository()

    def generate(
        self,
        *,
        wcr_pdf_path: str | Path | None = None,
        wcr_data: WCRPdfData | None = None,
        surveys: pd.DataFrame,
        surface_lat: float | None = None,
        surface_lon: float | None = None,
        surface_elevation_ft: float | None = None,
        north_reference: str = "grid",
        output_path: str | Path | None = None,
    ) -> WCRPdfResult:
        """Run the full pipeline. Returns the saved WCR Excel path
        plus the location rows that were written (for UI preview).

        Either pass ``wcr_pdf_path`` (will be parsed) or ``wcr_data`` (already
        parsed — avoids a duplicate Docling run when the UI parsed the PDF
        up-front). ``surveys`` must have ``MeasuredDepth``, ``Inclination``,
        ``Azimuth`` columns (degrees). Surface coordinates default to
        whatever the WCR PDF carries in Section 27 (UTM, projected back to
        lat/lon).
        """
        if wcr_data is None:
            if wcr_pdf_path is None:
                raise ValueError("Provide either wcr_pdf_path or wcr_data.")
            wcr_data = parse_wcr_pdf(wcr_pdf_path)
        pdf_data = wcr_data
        log.info(
            "wcr_pdf_service.parsed",
            well=pdf_data.well_name,
            api=pdf_data.api,
            positions=len(pdf_data.positions),
            stages=len(pdf_data.perf_stages),
        )

        lat, lon = self._resolve_surface_latlon(pdf_data, surface_lat, surface_lon)
        elev = surface_elevation_ft or pdf_data.elevation_ft
        if elev is None:
            raise ValueError("Surface elevation missing — provide it explicitly or fix the PDF.")

        processed = process_survey(
            surveys,
            surface_lat=lat,
            surface_lon=lon,
            surface_elevation_ft=elev,
            north_reference=north_reference,
            citing_type="As-Drilled",
            api=(pdf_data.api or "0000000000")[:10],
            lateral="0000",
        )
        grid = processed[SurveyFrame.GRID]
        points = grid.points

        # ---- Resolve the five MDs of interest ----
        first_perf = pdf_data.first_perf_md
        last_perf = pdf_data.last_perf_md
        td_md = pdf_data.total_md_ft or float(points["measured_depth"].iloc[-1])

        # ---- KOP source priority ----
        # 1. DDR — the operator's own driller note ("ORIENT TOOL FACE T/ X°
        #    ... SLIDE DRILL F/<md>") is the most authoritative source.
        # 2. detect_kop_simple — our INC-crossing-8° heuristic.
        # 3. detect_kop — the 5-method consensus.
        kop_md_ddr = _ddr_kop_md(pdf_data)
        if kop_md_ddr is not None:
            kop_md = kop_md_ddr
            kop_method = "ddr-driller-note"
            kop_conf = 1.0
        else:
            kop_md_simple = detect_kop_simple(points)
            if kop_md_simple is not None:
                kop_md = kop_md_simple
                kop_method = "simple"
                kop_conf = 1.0
            else:
                kop_result = detect_kop(points)
                kop_md = kop_result.md if kop_result.md is not None else 0.0
                kop_method = kop_result.method
                kop_conf = kop_result.confidence
        log.info("wcr_pdf_service.kop", md=kop_md, method=kop_method, conf=kop_conf)

        targets: dict[str, float] = {
            "SHL": 0.0,
            "Control_Point": kop_md,
        }
        if first_perf is not None:
            targets["Frac_Start"] = first_perf
        if last_perf is not None:
            targets["Frac_End"] = last_perf
        targets["BHL"] = td_md

        # ---- Interpolate each MD onto the trajectory ----
        interp_rows: list[dict] = []
        for name, md in targets.items():
            sample = interpolate_at_md(points, md)
            sample["location"] = name
            interp_rows.append(sample)
        df = pd.DataFrame(interp_rows)

        # ---- PLSS lookup + footages ----
        bundle = self.plat_repo.fetch_for_trajectory(
            points["easting"], points["northing"], buffer_m=3000
        )
        located = locate_points(df, bundle.sections)
        with_clearance = calculate_clearances(located, bundle.sections)

        # The trajectory's TVD is absolute (surface elevation + depth-below-KB).
        # The WCR convention wants depth-below-surface, so subtract elevation.
        location_rows = [
            _to_location_row(row, tvd_offset=elev) for _, row in with_clearance.iterrows()
        ]

        # ---- Resolve output path & emit ----
        info = _info_from_pdf(pdf_data)
        out = Path(output_path) if output_path else _default_output_path(pdf_data)
        casing_df, perf_date = _db_extras(pdf_data.api)
        path = generate_wcr_excel(
            info=info,
            location_rows=location_rows,
            output_path=out,
            perf_top_md=first_perf,
            perf_bottom_md=last_perf,
            perf_date=perf_date,
            casing=casing_df,
        )
        log.info("wcr_pdf_service.generated", path=str(path))
        return WCRPdfResult(
            output_path=path,
            pdf_data=pdf_data,
            location_rows=location_rows,
            points=points,
            sections=bundle.sections,
            elevation_ft=float(elev),
        )

    # ------------------------------------------------------------------
    # Edit cascade
    # ------------------------------------------------------------------
    def recompute_rows(
        self,
        *,
        edits: list[dict],
        points: pd.DataFrame,
        sections: gpd.GeoDataFrame,
        elevation_ft: float,
    ) -> list[WCRLocationRow]:
        """Rebuild the five location rows from user edits, cascading any MD
        or Easting/Northing change through TVD/footages/PLSS labels.

        ``edits`` is a list of dicts with at minimum a ``name`` key and any
        subset of ``measured_depth`` / ``easting`` / ``northing`` overrides.
        Order is preserved in the returned list.
        """
        interp_rows: list[dict] = []
        for edit in edits:
            name = edit["name"]
            md = edit.get("measured_depth")
            override_e = edit.get("easting")
            override_n = edit.get("northing")
            if md is not None and (override_e is None and override_n is None):
                sample = interpolate_at_md(points, float(md))
            elif md is not None:
                sample = interpolate_at_md(points, float(md))
                if override_e is not None:
                    sample["easting"] = float(override_e)
                if override_n is not None:
                    sample["northing"] = float(override_n)
            else:
                # No MD provided — keep zeros so the downstream interp at
                # MD=0 still gives us a valid TVD reading for the SHL.
                sample = interpolate_at_md(points, 0.0)
                if override_e is not None:
                    sample["easting"] = float(override_e)
                if override_n is not None:
                    sample["northing"] = float(override_n)
            sample["location"] = name
            interp_rows.append(sample)

        df = pd.DataFrame(interp_rows)
        located = locate_points(df, sections)
        with_clearance = calculate_clearances(located, sections)
        return [
            _to_location_row(row, tvd_offset=elevation_ft)
            for _, row in with_clearance.iterrows()
        ]

    def rewrite_excel(
        self,
        *,
        pdf_data: WCRPdfData,
        location_rows: list[WCRLocationRow],
        output_path: str | Path | None = None,
    ) -> Path:
        """Re-emit the Excel using current (possibly edited) location rows."""
        info = _info_from_pdf(pdf_data)
        out = Path(output_path) if output_path else _default_output_path(pdf_data)
        casing_df, perf_date = _db_extras(pdf_data.api)
        path = generate_wcr_excel(
            info=info,
            location_rows=location_rows,
            output_path=out,
            perf_top_md=pdf_data.first_perf_md,
            perf_bottom_md=pdf_data.last_perf_md,
            perf_date=perf_date,
            casing=casing_df,
        )
        log.info("wcr_pdf_service.rewritten", path=str(path))
        return path

    # ------------------------------------------------------------------
    def _resolve_surface_latlon(
        self,
        pdf: WCRPdfData,
        lat: float | None,
        lon: float | None,
    ) -> tuple[float, float]:
        if lat is not None and lon is not None:
            return lat, lon
        surface = pdf.surface_position
        if surface is None or surface.utm_easting is None or surface.utm_northing is None:
            raise ValueError(
                "Surface coordinates missing from PDF — supply surface_lat/surface_lon explicitly."
            )
        # WCR PDFs use UTM zone 12N (Utah). Project back to WGS84 lat/lon.
        lat_d, lon_d = utm_to_latlon(
            surface.utm_easting, surface.utm_northing, zone_number=12, zone_letter="N"
        )
        return lat_d, lon_d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db_extras(api: str | None) -> tuple[pd.DataFrame | None, str | None]:
    """Casing table + latest perf date from the DB, when reachable.

    The PDF pipeline must keep working without SQL Server, so any failure
    here degrades to (None, None) — the workbook simply omits those cells.
    """
    if not api:
        return None, None
    try:
        from etools.repositories import WCRRepository
        from etools.services.wcr_service import _perf_summary

        bundle = WCRRepository().get_bundle(api[:10])
    except Exception as exc:
        log.info("wcr_pdf_service.db_extras.unavailable", error=str(exc))
        return None, None
    casing = bundle.casing if bundle.casing is not None and not bundle.casing.empty else None
    _, _, perf_date = _perf_summary(bundle.perforations)
    return casing, perf_date


def _ddr_kop_md(pdf_data: WCRPdfData) -> float | None:
    """Pull the shallowest KOP MD reported by the driller across all DDRs.

    A well may have several "kickoff" events (e.g. surface-curve KOP and
    lateral-curve KOP). The shallowest one is the canonical curve-start
    we want for Control_Point.
    """
    candidates: list[float] = []
    for ddr in pdf_data.ddrs:
        for ev in ddr.all_events("KOP"):
            if ev.md_ft is not None and 100 < ev.md_ft < 30000:
                candidates.append(ev.md_ft)
    return min(candidates) if candidates else None


def _to_location_row(row, *, tvd_offset: float = 0.0) -> WCRLocationRow:
    return WCRLocationRow(
        name=str(row["location"]),
        measured_depth=float(row["measured_depth"]),
        tvd=float(row.get("tvd", 0.0)) - tvd_offset,
        easting=float(row.get("easting", 0.0)),
        northing=float(row.get("northing", 0.0)),
        fnl=_to_float(row.get("FNL")),
        fsl=_to_float(row.get("FSL")),
        fel=_to_float(row.get("FEL")),
        fwl=_to_float(row.get("FWL")),
        section=_to_str(row.get("Section")),
        township=_to_str(row.get("Township")),
        township_dir=_to_str(row.get("Township_Direction")),
        range=_to_str(row.get("Range")),
        range_dir=_to_str(row.get("Range_Direction")),
        baseline=_to_str(row.get("Baseline")),
    )


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


def _info_from_pdf(pdf: WCRPdfData) -> WCRWellInfo:
    return WCRWellInfo(
        api_well_no=(pdf.api or "0000000000")[:14],
        well_name=pdf.well_name,
        operator=pdf.operator,
        well_type=_compact_well_type(pdf.well_type),
        elevation_ft=pdf.elevation_ft,
        proposed_tvd_ft=pdf.total_tvd_ft,
        proposed_md_ft=pdf.total_md_ft,
        spud_date=_parse_date(pdf.spud_date),
        rotary_date=_parse_date(pdf.rotary_date),
        td_date=_parse_date(pdf.td_date),
        completion_date=_parse_date(pdf.completion_date),
    )


_WELL_TYPE_ABBREV = {
    "oil well": "OW",
    "gas well": "GW",
    "injection well": "IW",
    "disposal well": "DW",
    "water well": "WW",
    "dry hole": "DH",
}


def _compact_well_type(raw: str | None) -> str | None:
    if not raw:
        return None
    return _WELL_TYPE_ABBREV.get(raw.strip().lower(), raw.strip())


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _default_output_path(pdf: WCRPdfData) -> Path:
    safe_name = (pdf.well_name or pdf.api or "WCR").replace(" ", "_").replace("/", "-")
    api10 = (pdf.api or "")[:10]
    return Path(settings.output_dir) / f"{safe_name}_{api10}_WCR.xlsx"
