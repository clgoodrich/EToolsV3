"""
Plat (section) repository for EToolsV3.

This module provides data access for PLSS section boundaries from SQLite database.
"""

from typing import Optional, List, Tuple
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, Point

from data.repositories.base_repository import BaseSQLiteRepository
from data.models.plat import PlatSection, SpatialQuery
from config.settings import settings
from utils.errors import PlatNotFoundError, DatabaseQueryError


class PlatRepository(BaseSQLiteRepository):
    """Repository for plat/section data access."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize plat repository.

        Args:
            db_path: Path to plat SQLite database. If None, uses path from settings.
        """
        if db_path is None:
            db_path = str(settings.paths.plat_db)
        super().__init__(db_path)

    def get_plats_in_bbox(
        self,
        min_easting: float,
        max_easting: float,
        min_northing: float,
        max_northing: float,
        buffer: float = 1000.0
    ) -> pd.DataFrame:
        """
        Get all plats within a bounding box.

        Args:
            min_easting: Minimum easting coordinate.
            max_easting: Maximum easting coordinate.
            min_northing: Minimum northing coordinate.
            max_northing: Maximum northing coordinate.
            buffer: Buffer distance in feet.

        Returns:
            DataFrame with plat data.

        Raises:
            DatabaseQueryError: If query fails.
        """
        query = """
            SELECT *
            FROM BaseData
            WHERE Easting >= ?
                AND Easting <= ?
                AND Northing >= ?
                AND Northing <= ?
        """

        params = (
            min_easting - buffer,
            max_easting + buffer,
            min_northing - buffer,
            max_northing + buffer
        )

        return self._execute_query(query, params, "get_plats_in_bbox")

    def get_plats_by_conc_list(self, conc_values: List[str]) -> pd.DataFrame:
        """
        Get plats by their concatenated identifiers.

        Args:
            conc_values: List of concatenated section identifiers (e.g., ['02041N02WU']).

        Returns:
            DataFrame with plat data.

        Raises:
            DatabaseQueryError: If query fails.
        """
        if not conc_values:
            return pd.DataFrame()

        # Create placeholders for SQL IN clause
        placeholders = ','.join('?' * len(conc_values))
        query = f"""
            SELECT *
            FROM BaseData
            WHERE Conc IN ({placeholders})
        """

        return self._execute_query(query, tuple(conc_values), "get_plats_by_conc")

    def get_plat_by_conc(self, conc: str) -> pd.DataFrame:
        """
        Get a single plat by its concatenated identifier.

        Args:
            conc: Concatenated section identifier (e.g., '02041N02WU').

        Returns:
            DataFrame with plat vertices.

        Raises:
            PlatNotFoundError: If plat not found.
            DatabaseQueryError: If query fails.
        """
        query = """
            SELECT *
            FROM BaseData
            WHERE Conc = ?
            ORDER BY Easting, Northing
        """

        result = self._execute_query(query, (conc,), "get_plat_by_conc")

        if result.empty:
            raise PlatNotFoundError(f"Plat not found: {conc}")

        return result

    def get_plats_as_geodataframe(self, plat_df: pd.DataFrame) -> gpd.GeoDataFrame:
        """
        Convert plat data to GeoDataFrame with polygon geometries.

        Args:
            plat_df: DataFrame with plat corner coordinates.

        Returns:
            GeoDataFrame with polygon geometries.
        """
        if plat_df.empty:
            return gpd.GeoDataFrame()

        # Group by Conc and create polygons
        polygons = (
            plat_df.groupby('Conc')
            .apply(lambda x: Polygon(zip(x['Easting'], x['Northing'])))
            .reset_index()
            .rename(columns={0: 'geometry'})
        )

        # Add label transformation
        polygons['label'] = (
            polygons['Conc'].str[:2].astype(int).astype(str) + ' ' +
            polygons['Conc'].str[2:4].astype(int).astype(str) + polygons['Conc'].str[4] + ' ' +
            polygons['Conc'].str[5:7].astype(int).astype(str) + polygons['Conc'].str[7] + ' ' +
            polygons['Conc'].str[-1]
        )

        # Add centroids
        polygons['centroid'] = polygons['geometry'].centroid
        polygons['centroid_x'] = polygons['centroid'].x
        polygons['centroid_y'] = polygons['centroid'].y

        # Create GeoDataFrame
        gdf = gpd.GeoDataFrame(polygons, geometry='geometry', crs='EPSG:26912')  # UTM Zone 12N

        return gdf

    def find_plats_containing_points(
        self,
        eastings: List[float],
        northings: List[float],
        buffer: float = 1000.0
    ) -> gpd.GeoDataFrame:
        """
        Find plats that contain the given points.

        Args:
            eastings: List of easting coordinates.
            northings: List of northing coordinates.
            buffer: Buffer distance for bounding box query.

        Returns:
            GeoDataFrame with plats that contain any of the points.
        """
        # Get bounding box
        min_e, max_e = min(eastings), max(eastings)
        min_n, max_n = min(northings), max(northings)

        # Get plats in bounding box
        plat_df = self.get_plats_in_bbox(min_e, max_e, min_n, max_n, buffer)

        if plat_df.empty:
            return gpd.GeoDataFrame()

        # Convert to GeoDataFrame
        gdf = self.get_plats_as_geodataframe(plat_df)

        # Create points
        points = [Point(e, n) for e, n in zip(eastings, northings)]

        # Filter plats that contain any point
        def contains_any_point(polygon):
            return any(polygon.contains(point) for point in points)

        gdf['contains_point'] = gdf['geometry'].apply(contains_any_point)
        return gdf[gdf['contains_point']].copy()

    def get_adjacent_plats(self, conc: str) -> pd.DataFrame:
        """
        Get adjacent plats around a target plat.

        Args:
            conc: Concatenated section identifier.

        Returns:
            DataFrame with adjacent plats from section_relative table.
        """
        # Truncate to 9 characters for lookup
        conc_short = conc[:9]

        query = """
            SELECT *
            FROM section_relative
            WHERE Conc = ?
        """

        result = self._execute_query(query, (conc_short,), "get_adjacent_plats")

        return result.drop_duplicates(subset=['Conc'], keep='first')

    def get_plat_by_section_tsr(
        self,
        section: int,
        township: int,
        township_dir: str,
        range_num: int,
        range_dir: str,
        baseline: str = 'U'
    ) -> pd.DataFrame:
        """
        Get plat by Township/Section/Range coordinates.

        Args:
            section: Section number (1-36).
            township: Township number.
            township_dir: Township direction ('N' or 'S').
            range_num: Range number.
            range_dir: Range direction ('E' or 'W').
            baseline: Baseline identifier ('U' for Utah).

        Returns:
            DataFrame with plat data.
        """
        # Build concatenated identifier
        conc = f"{section:02d}{township:02d}{township_dir}{range_num:02d}{range_dir}{baseline}"

        return self.get_plat_by_conc(conc)

    def get_plat_statistics(self) -> dict:
        """
        Get statistics about the plat database.

        Returns:
            Dictionary with statistics (total plats, coverage area, etc.).
        """
        stats = {}

        # Total unique plats
        query = "SELECT COUNT(DISTINCT Conc) as total_plats FROM BaseData"
        stats['total_plats'] = self._execute_scalar(query, None, "count_plats")

        # Bounding box
        query = """
            SELECT
                MIN(Easting) as min_easting,
                MAX(Easting) as max_easting,
                MIN(Northing) as min_northing,
                MAX(Northing) as max_northing
            FROM BaseData
        """
        bbox_result = self._execute_query(query, None, "get_bbox")
        if not bbox_result.empty:
            stats.update(bbox_result.iloc[0].to_dict())

        return stats


class LocationRepository(BaseSQLiteRepository):
    """Repository for location data (alternative plat database)."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize location repository.

        Args:
            db_path: Path to location SQLite database. If None, uses path from settings.
        """
        if db_path is None:
            db_path = str(settings.paths.location_db)
        super().__init__(db_path)

    def get_relative_sections(self, conc_values: List[str]) -> pd.DataFrame:
        """
        Get relative section information for given concentrations.

        Args:
            conc_values: List of concatenated identifiers (truncated to 9 chars).

        Returns:
            DataFrame with section relative data grouped by Conc and Version.
        """
        if not conc_values:
            return pd.DataFrame()

        # Ensure conc values are truncated to 9 characters
        conc_values = [c[:9] for c in conc_values]

        placeholders = ','.join('?' * len(conc_values))
        query = f"""
            SELECT *
            FROM section_relative
            WHERE Conc IN ({placeholders})
        """

        result = self._execute_query(query, tuple(conc_values), "get_relative_sections")

        # Truncate Conc column to 9 characters
        if not result.empty and 'Conc' in result.columns:
            result['Conc'] = result['Conc'].apply(lambda x: x[:9] if isinstance(x, str) else x)

        return result.drop_duplicates(keep='first')
