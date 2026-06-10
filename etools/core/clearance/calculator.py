"""Compute FNL/FSL/FEL/FWL footages for every survey point.

Pipeline:
    1. Locate each point's containing section (already done by the locator).
    2. Cache one ``SectionBoundary`` per unique Conc.
    3. For each point, look up perpendicular distances to its section's
       N/S/E/W boundary lines.

Distances are computed in UTM meters and reported in feet (Utah regulatory
convention). The output dataframe matches the legacy ``clearance_data`` shape
so existing downstream code (Excel writer, viz) reads the same columns.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from etools.core.clearance.boundary_segmenter import (
    SectionBoundary,
    distances_to_sides,
    segment_section,
)
from etools.logging_setup import get_logger

log = get_logger(__name__)

_METERS_TO_FEET = 1.0 / 0.3048


def calculate_clearances(
    located_points: pd.DataFrame,
    sections: gpd.GeoDataFrame,
    *,
    easting_col: str = "easting",
    northing_col: str = "northing",
) -> pd.DataFrame:
    """Compute FNL/FSL/FEL/FWL for each point, in feet.

    ``located_points`` must already carry a ``Conc`` column (from the plat
    locator). Points with NaN Conc — outside the supplied plat coverage —
    receive NaN distances rather than failing.
    """
    if located_points.empty:
        return located_points.assign(FNL=pd.NA, FSL=pd.NA, FEL=pd.NA, FWL=pd.NA)
    if "Conc" not in located_points:
        raise ValueError("locate_points must run before calculate_clearances")

    # Build a one-time cache of segmented boundaries for the sections we touched.
    cache: dict[str, SectionBoundary] = {}
    section_lookup = sections.set_index("Conc")

    fnl, fsl, fel, fwl = [], [], [], []
    for _, row in located_points.iterrows():
        conc = row.get("Conc")
        if pd.isna(conc) or conc not in section_lookup.index:
            for side in (fnl, fsl, fel, fwl):
                side.append(pd.NA)
            continue
        if conc not in cache:
            sec = section_lookup.loc[conc]
            cache[conc] = segment_section(
                sec.geometry, conc=conc, label=sec.get("label", "")
            )
        boundary = cache[conc]
        d = distances_to_sides(row[easting_col], row[northing_col], boundary)
        fnl.append(d["N"] * _METERS_TO_FEET)
        fsl.append(d["S"] * _METERS_TO_FEET)
        fel.append(d["E"] * _METERS_TO_FEET)
        fwl.append(d["W"] * _METERS_TO_FEET)

    out = located_points.copy()
    out["FNL"] = fnl
    out["FSL"] = fsl
    out["FEL"] = fel
    out["FWL"] = fwl
    log.info(
        "clearance.calc",
        points=len(out),
        with_clearance=int(out["FNL"].notna().sum()),
        sections_segmented=len(cache),
    )
    return out
