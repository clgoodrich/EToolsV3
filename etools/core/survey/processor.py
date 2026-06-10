"""Minimum-curvature survey processing via welleng.

The legacy code ran the welleng pipeline twice — once for true-north output
and once for grid-north — and stored the results as ``drl_df_true_dx`` /
``drl_df_grid_dx`` / ``pln_df_true_dx`` / ``pln_df_grid_dx``. We do the same
end-to-end shape, but compute the trajectory once and just relabel azimuths,
since the underlying geometry is frame-invariant.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
from welleng.survey import Survey, SurveyHeader

from etools.core.coordinates import grid_convergence, latlon_to_utm
from etools.core.survey.magnetic import lookup_magnetic_field
from etools.logging_setup import get_logger
from etools.models import CitingType, ProcessedSurvey, SurveyFrame

log = get_logger(__name__)


_FRAME_TO_AZI_ATTR: dict[SurveyFrame, str] = {
    SurveyFrame.TRUE: "azi_true_deg",
    SurveyFrame.GRID: "azi_grid_deg",
}


def _normalize_north_ref(value: str | None) -> Literal["true", "grid", "magnetic"]:
    """Map free-text NorthReference values to welleng's enum."""
    if not value:
        return "true"
    v = value.strip().lower()
    if v.startswith("g"):
        return "grid"
    if v.startswith("m"):
        return "magnetic"
    return "true"


def _normalize_citing(value: str | None) -> CitingType:
    if value and "drill" in value.lower():
        return CitingType.DRILLED
    return CitingType.PLANNED


def process_survey(
    raw: pd.DataFrame,
    *,
    surface_lat: float,
    surface_lon: float,
    surface_elevation_ft: float,
    north_reference: str | None,
    citing_type: str | None,
    api: str,
    lateral: str,
    grid_scale_factor: float | None = None,
) -> dict[SurveyFrame, ProcessedSurvey]:
    """Process raw MD/INC/AZI rows into a ProcessedSurvey for each reference frame.

    The input ``raw`` is expected to have at least ``MeasuredDepth``,
    ``Inclination``, and ``Azimuth`` columns (degrees). Extra columns are
    ignored. Output frames share the same geometry; only the reported
    azimuth column differs.
    """
    if raw.empty:
        raise ValueError("Cannot process an empty survey.")

    df = raw[["MeasuredDepth", "Inclination", "Azimuth"]].copy()
    df = df.drop_duplicates(subset="MeasuredDepth").sort_values("MeasuredDepth").reset_index(drop=True)

    # Insert MD=0 station if missing — welleng requires the trajectory to start at zero.
    if df["MeasuredDepth"].iloc[0] > 0:
        df = pd.concat(
            [pd.DataFrame([{"MeasuredDepth": 0.0, "Inclination": 0.0, "Azimuth": 0.0}]), df],
            ignore_index=True,
        )

    md = df["MeasuredDepth"].to_numpy(dtype=float)
    inc = df["Inclination"].to_numpy(dtype=float)
    azi = df["Azimuth"].to_numpy(dtype=float)

    convergence = grid_convergence(surface_lat, surface_lon)
    mag = lookup_magnetic_field(surface_lat, surface_lon, altitude_m=surface_elevation_ft * 0.3048)

    azi_ref = _normalize_north_ref(north_reference)
    header = SurveyHeader(
        name=f"{api}-{lateral}",
        latitude=surface_lat,
        longitude=surface_lon,
        altitude=surface_elevation_ft * 0.3048,
        azi_reference=azi_ref,
        deg=True,
        depth_unit="feet",
        surface_unit="feet",
        declination=mag.declination,
        dip=mag.inclination,
        b_total=mag.total_intensity,
        convergence=convergence,
        grid_scale_factor=grid_scale_factor or 1.0,
    )

    surface_e, surface_n, _, _ = latlon_to_utm(surface_lat, surface_lon)
    survey = Survey(
        md=md, inc=inc, azi=azi,
        header=header,
        deg=True,
        unit="feet",
        start_nev=[0.0, 0.0, surface_elevation_ft],
    )

    n = np.asarray(survey.n, dtype=float)
    e = np.asarray(survey.e, dtype=float)
    tvd = np.asarray(survey.tvd, dtype=float)
    dls = np.asarray(survey.dls, dtype=float)

    # Geographic coords from local NEV: project back through the same aeqd centered at SHL.
    # welleng's n/e are in the working unit (feet); we need them in feet for this projection.
    # Inverse projection: take (north, east) in feet → lat/lon.
    lat_arr, lon_arr = _nev_to_latlon(n, e, surface_lat, surface_lon)

    # UTM (meters) and easting/northing in feet relative to SHL UTM origin.
    eastings_m = np.empty_like(n)
    northings_m = np.empty_like(n)
    for i, (la, lo) in enumerate(zip(lat_arr, lon_arr)):
        ee, nn, _, _ = latlon_to_utm(la, lo)
        eastings_m[i] = ee
        northings_m[i] = nn

    base = pd.DataFrame(
        {
            "measured_depth": md,
            "inclination": inc,
            "tvd": tvd,
            "n_offset": n,
            "e_offset": e,
            "dls": dls,
            "lat": lat_arr,
            "lon": lon_arr,
            "easting": eastings_m,
            "northing": northings_m,
        }
    )
    base["point_index"] = base.index
    base["feature"] = ""  # populated downstream when KOP/landing/perfs are tagged

    out: dict[SurveyFrame, ProcessedSurvey] = {}
    for frame in (SurveyFrame.TRUE, SurveyFrame.GRID):
        attr = _FRAME_TO_AZI_ATTR[frame]
        azi_out = np.asarray(getattr(survey, attr), dtype=float)
        frame_df = base.copy()
        frame_df.insert(2, "azimuth", azi_out)
        out[frame] = ProcessedSurvey(
            api=api,
            lateral=lateral,
            citing_type=_normalize_citing(citing_type),
            frame=frame,
            elevation=surface_elevation_ft,
            convergence_angle=convergence,
            proposed_azimuth=float(azi_out[-1]) if len(azi_out) else None,
            points=frame_df,
        )

    log.info(
        "survey.processed",
        api=api,
        lateral=lateral,
        citing=citing_type,
        points=len(md),
        convergence=convergence,
        declination=mag.declination,
    )
    return out


def interpolate_at_md(points: pd.DataFrame, target_md: float) -> dict[str, float]:
    """Linearly interpolate the processed-survey points at an arbitrary MD.

    Returns a dict with measured_depth, tvd, n_offset, e_offset, easting,
    northing, lat, lon, inclination, azimuth (if present). Out-of-range MDs
    clamp to the first/last station rather than raising — the WCR pipeline
    tolerates the SHL row at MD=0 even when surveys start at a non-zero MD.
    """
    if points.empty:
        raise ValueError("Cannot interpolate against an empty survey.")
    df = points.sort_values("measured_depth").reset_index(drop=True)
    md = df["measured_depth"].to_numpy(dtype=float)

    cols = [
        c
        for c in (
            "tvd",
            "n_offset",
            "e_offset",
            "easting",
            "northing",
            "lat",
            "lon",
            "inclination",
            "azimuth",
            "dls",
        )
        if c in df.columns
    ]

    if target_md <= md[0]:
        row = df.iloc[0]
        return {"measured_depth": float(target_md), **{c: float(row[c]) for c in cols}}
    if target_md >= md[-1]:
        row = df.iloc[-1]
        return {"measured_depth": float(target_md), **{c: float(row[c]) for c in cols}}

    idx = int(np.searchsorted(md, target_md))
    lo, hi = idx - 1, idx
    span = md[hi] - md[lo]
    t = 0.0 if span == 0 else (target_md - md[lo]) / span
    out: dict[str, float] = {"measured_depth": float(target_md)}
    for c in cols:
        a = float(df[c].iloc[lo])
        b = float(df[c].iloc[hi])
        out[c] = a + t * (b - a)
    return out


def _nev_to_latlon(
    n: np.ndarray, e: np.ndarray, lat0: float, lon0: float
) -> tuple[np.ndarray, np.ndarray]:
    """AEQD-unproject (north_ft, east_ft) at origin (lat0, lon0) back to lat/lon."""
    from pyproj import Proj

    proj = Proj(proj="aeqd", datum="WGS84", lat_0=lat0, lon_0=lon0, units="us-ft")
    lon, lat = proj(e, n, inverse=True)
    return np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
