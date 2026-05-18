"""Spatial-join survey points → containing PLSS section.

The legacy ``find_plats_data`` performed three passes (bbox query, conc filter,
re-query, sjoin). With the polygons already in memory and indexed by a
GeoDataFrame's spatial index, a single ``sjoin`` is all we need.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from etools.logging_setup import get_logger

log = get_logger(__name__)


def locate_points(
    points: pd.DataFrame,
    sections: gpd.GeoDataFrame,
    *,
    easting_col: str = "easting",
    northing_col: str = "northing",
) -> pd.DataFrame:
    """Tag each survey point with the ``Conc`` and ``label`` of its section.

    Returns the input frame plus two new columns: ``Conc`` and ``label``.
    Points that fall outside every supplied section get ``NaN`` for both.
    """
    if points.empty or sections.empty:
        out = points.copy()
        out["Conc"] = pd.NA
        out["label"] = pd.NA
        return out

    geom = [Point(x, y) for x, y in zip(points[easting_col], points[northing_col])]
    pts_gdf = gpd.GeoDataFrame(points.copy(), geometry=geom, crs=sections.crs)
    joined = gpd.sjoin(
        pts_gdf,
        sections[["Conc", "label", "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined.drop(columns=["index_right", "geometry"], errors="ignore")
    # Some boundary points can match two adjacent sections; keep the first.
    joined = joined[~joined.index.duplicated(keep="first")]

    # Decompose the Conc into its PLSS components so downstream consumers
    # (WCR writer, UI) don't need to re-parse. Empty for unmatched points.
    plss = joined["Conc"].apply(_parse_conc)
    for col in ("Section", "Township", "Township_Direction", "Range", "Range_Direction", "Baseline"):
        joined[col] = plss.apply(lambda d, k=col: d.get(k))

    matched = joined["Conc"].notna().sum()
    log.info(
        "plat.locate", points=len(points), matched=int(matched), unique_sections=joined["Conc"].nunique()
    )
    return joined


def _parse_conc(conc) -> dict[str, str | None]:
    """``1402S05WU`` → {Section: '14', Township: '2', Township_Direction: 'S', ...}.

    Returns a dict of Nones for missing/malformed codes so callers can build
    columns without branching.
    """
    if not isinstance(conc, str) or len(conc) < 9:
        return {
            "Section": None,
            "Township": None,
            "Township_Direction": None,
            "Range": None,
            "Range_Direction": None,
            "Baseline": None,
        }
    try:
        return {
            "Section": str(int(conc[0:2])),
            "Township": str(int(conc[2:4])),
            "Township_Direction": conc[4],
            "Range": str(int(conc[5:7])),
            "Range_Direction": conc[7],
            "Baseline": conc[8],
        }
    except ValueError:
        return {
            "Section": None,
            "Township": None,
            "Township_Direction": None,
            "Range": None,
            "Range_Direction": None,
            "Baseline": None,
        }
