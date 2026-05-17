"""PlatRepository — PLSS section polygons from the local SQLite plat DB.

The legacy ``Board_DB_Plss_Sections.db`` ships with two key tables:

* ``BaseData`` — section corner points (Easting/Northing UTM12N) keyed by ``Conc``.
* ``Adjacent`` — section adjacency lookups for catching wells that overrun.

A ``Conc`` like ``1402S05WU`` decomposes as
``Section 14, Township 2 S, Range 5 W, U(intah meridian)``.
We surface that in a friendly ``label`` column matching the legacy format
(``"14 2S 5W U"``).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon
from sqlalchemy import text

from etools.config import settings
from etools.db import get_sqlite_engine
from etools.logging_setup import get_logger

log = get_logger(__name__)

# UTM zone 12N covers all of Utah; surveys are stored in this CRS already.
PLAT_CRS = "EPSG:32612"


@dataclass(slots=True)
class PlatBundle:
    """Result of a plat lookup — sections + adjacency for the surrounding area."""

    sections: gpd.GeoDataFrame  # one polygon per Conc
    adjacent: pd.DataFrame  # Conc → adjacent Conc (raw lookup)


class PlatRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else settings.plats_db
        if not self.db_path.exists():
            raise FileNotFoundError(f"Plat database not found: {self.db_path}")
        self.engine = get_sqlite_engine(self.db_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_bbox(
        self,
        min_easting: float,
        min_northing: float,
        max_easting: float,
        max_northing: float,
        buffer_m: float = 1000.0,
    ) -> PlatBundle:
        """All sections whose corner points fall in the buffered bbox (UTM meters)."""
        sql = text(
            """
            SELECT Conc, Easting, Northing
            FROM BaseData
            WHERE Easting BETWEEN :emin AND :emax
              AND Northing BETWEEN :nmin AND :nmax
            """
        )
        params = {
            "emin": min_easting - buffer_m,
            "emax": max_easting + buffer_m,
            "nmin": min_northing - buffer_m,
            "nmax": max_northing + buffer_m,
        }
        with self.engine.connect() as cn:
            df = pd.read_sql_query(sql, cn, params=params)
        if df.empty:
            log.warning("plat.fetch_bbox.empty", **params)
            return _empty_bundle()

        # Re-query for the full set of corner points belonging to any matched Conc
        # so polygons aren't truncated when only one corner falls in the bbox.
        full_df = self._fetch_concs(df["Conc"].unique().tolist())
        sections = self._build_sections(full_df)
        adjacent = self._fetch_adjacent(sections["Conc"].tolist())
        log.info("plat.fetch_bbox", sections=len(sections), adjacency_rows=len(adjacent))
        return PlatBundle(sections=sections, adjacent=adjacent)

    def fetch_for_point(self, easting: float, northing: float, buffer_m: float = 5000.0) -> PlatBundle:
        return self.fetch_bbox(easting, northing, easting, northing, buffer_m=buffer_m)

    def fetch_for_trajectory(
        self,
        eastings: pd.Series | list[float],
        northings: pd.Series | list[float],
        buffer_m: float = 1000.0,
    ) -> PlatBundle:
        """Bbox derived from a survey trajectory plus a buffer."""
        e = pd.Series(eastings, dtype=float)
        n = pd.Series(northings, dtype=float)
        return self.fetch_bbox(
            float(e.min()), float(n.min()), float(e.max()), float(n.max()), buffer_m=buffer_m
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch_concs(self, concs: list[str]) -> pd.DataFrame:
        """Fetch all corner points for a known set of section codes."""
        if not concs:
            return pd.DataFrame(columns=["Conc", "Easting", "Northing"])
        # Chunk to stay well within SQLite's parameter limit.
        chunk_size = 500
        frames: list[pd.DataFrame] = []
        with self.engine.connect() as cn:
            for i in range(0, len(concs), chunk_size):
                chunk = concs[i : i + chunk_size]
                placeholders = ",".join(f":c{j}" for j in range(len(chunk)))
                sql = text(
                    f"SELECT Conc, Easting, Northing FROM BaseData WHERE Conc IN ({placeholders})"
                )
                params = {f"c{j}": c for j, c in enumerate(chunk)}
                frames.append(pd.read_sql_query(sql, cn, params=params))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _fetch_adjacent(self, concs: list[str]) -> pd.DataFrame:
        if not concs:
            return pd.DataFrame(columns=["Conc2", "adjacent_Conc_Name_2"])
        chunk_size = 500
        frames: list[pd.DataFrame] = []
        with self.engine.connect() as cn:
            for i in range(0, len(concs), chunk_size):
                chunk = concs[i : i + chunk_size]
                placeholders = ",".join(f":c{j}" for j in range(len(chunk)))
                sql = text(
                    "SELECT Conc2, adjacent_Conc_Name_2 FROM Adjacent "
                    f"WHERE Conc2 IN ({placeholders})"
                )
                params = {f"c{j}": c for j, c in enumerate(chunk)}
                frames.append(pd.read_sql_query(sql, cn, params=params))
        return (
            pd.concat(frames, ignore_index=True).drop_duplicates(keep="first")
            if frames
            else pd.DataFrame()
        )

    @staticmethod
    def _build_sections(df: pd.DataFrame) -> gpd.GeoDataFrame:
        """Group BaseData corner points by Conc and assemble each into a Polygon.

        Points are stored in traversal order in the legacy DB, so zipping
        ``(Easting, Northing)`` produces a closed ring. We additionally compute
        a friendly ``label`` and the centroid for downstream UI use.
        """
        if df.empty:
            return gpd.GeoDataFrame(columns=["Conc", "label", "geometry"], crs=PLAT_CRS)

        rows: list[dict] = []
        for conc, group in df.groupby("Conc"):
            polygon = Polygon(zip(group["Easting"], group["Northing"]))
            if not polygon.is_valid:
                polygon = polygon.buffer(0)  # repair self-intersections
            rows.append(
                {
                    "Conc": conc,
                    "label": _conc_to_label(conc),
                    "geometry": polygon,
                }
            )
        gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=PLAT_CRS)
        gdf["centroid_x"] = gdf.geometry.centroid.x
        gdf["centroid_y"] = gdf.geometry.centroid.y
        return gdf


@lru_cache(maxsize=4096)
def _conc_to_label(conc: str) -> str:
    """``1402S05WU`` → ``"14 2S 5W U"``. Falls back to the raw value if malformed."""
    if not isinstance(conc, str) or len(conc) < 9:
        return conc or ""
    try:
        sec = int(conc[0:2])
        twp = int(conc[2:4])
        twp_dir = conc[4]
        rng = int(conc[5:7])
        rng_dir = conc[7]
        meridian = conc[8]
        return f"{sec} {twp}{twp_dir} {rng}{rng_dir} {meridian}"
    except ValueError:
        return conc


def _empty_bundle() -> PlatBundle:
    return PlatBundle(
        sections=gpd.GeoDataFrame(columns=["Conc", "label", "geometry"], crs=PLAT_CRS),
        adjacent=pd.DataFrame(columns=["Conc2", "adjacent_Conc_Name_2"]),
    )
