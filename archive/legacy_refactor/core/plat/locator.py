"""
Plat (section) location and spatial operations for EToolsV3.

This module handles spatial joins between wellbore trajectories and PLSS sections.
"""

from typing import List, Tuple, Optional
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString

from data.models.plat import PlatSection, SpatialQuery
from config.logging_config import get_logger

logger = get_logger(__name__)


class PlatLocator:
    """Locates plats (sections) that intersect with wellbore trajectories."""

    def __init__(self):
        """Initialize plat locator."""
        self.logger = logger

    def find_intersecting_plats(
        self,
        survey_df: pd.DataFrame,
        plat_gdf: gpd.GeoDataFrame
    ) -> gpd.GeoDataFrame:
        """
        Find all plats that intersect with survey trajectory.

        Args:
            survey_df: Survey DataFrame with easting/northing columns.
            plat_gdf: GeoDataFrame with plat polygons.

        Returns:
            GeoDataFrame with plats that intersect the trajectory.
        """
        if survey_df.empty or plat_gdf.empty:
            return gpd.GeoDataFrame()

        # Create trajectory line
        points = [Point(e, n) for e, n in zip(survey_df['easting'], survey_df['northing'])]
        trajectory = LineString(points)

        # Find intersecting plats
        intersecting = plat_gdf[plat_gdf['geometry'].intersects(trajectory)].copy()

        self.logger.info(f"Found {len(intersecting)} plats intersecting trajectory")

        return intersecting

    def assign_section_to_points(
        self,
        survey_df: pd.DataFrame,
        plat_gdf: gpd.GeoDataFrame
    ) -> pd.DataFrame:
        """
        Assign section (plat) to each survey point.

        Args:
            survey_df: Survey DataFrame with easting/northing columns.
            plat_gdf: GeoDataFrame with plat polygons.

        Returns:
            Survey DataFrame with section_conc and section_label columns added.
        """
        df = survey_df.copy()

        # Initialize columns
        df['section_conc'] = None
        df['section_label'] = None

        # Check each point against plats
        for idx, row in df.iterrows():
            point = Point(row['easting'], row['northing'])

            # Find containing plat
            containing = plat_gdf[plat_gdf['geometry'].contains(point)]

            if not containing.empty:
                # Take first match (should only be one)
                plat = containing.iloc[0]
                df.at[idx, 'section_conc'] = plat['Conc']
                df.at[idx, 'section_label'] = plat.get('label', '')

        self.logger.debug(
            f"Assigned sections to {df['section_conc'].notna().sum()} of {len(df)} points"
        )

        return df

    def get_section_entry_exit_points(
        self,
        survey_df: pd.DataFrame
    ) -> List[Tuple[str, float, float]]:
        """
        Get entry and exit measured depths for each section.

        Args:
            survey_df: Survey DataFrame with section_conc and measured_depth columns.

        Returns:
            List of tuples (section_conc, entry_md, exit_md).
        """
        if 'section_conc' not in survey_df.columns:
            return []

        # Remove null sections
        df = survey_df.dropna(subset=['section_conc'])

        if df.empty:
            return []

        # Group by consecutive sections
        df['section_group'] = (df['section_conc'] != df['section_conc'].shift()).cumsum()

        results = []
        for _, group in df.groupby('section_group'):
            section_conc = group['section_conc'].iloc[0]
            entry_md = group['measured_depth'].min()
            exit_md = group['measured_depth'].max()
            results.append((section_conc, entry_md, exit_md))

        return results

    def calculate_footage_by_section(
        self,
        survey_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calculate total footage in each section.

        Args:
            survey_df: Survey DataFrame with section_conc and measured_depth columns.

        Returns:
            DataFrame with section_conc and footage columns.
        """
        entry_exits = self.get_section_entry_exit_points(survey_df)

        if not entry_exits:
            return pd.DataFrame(columns=['section_conc', 'footage', 'entry_md', 'exit_md'])

        footage_df = pd.DataFrame(entry_exits, columns=['section_conc', 'entry_md', 'exit_md'])
        footage_df['footage'] = footage_df['exit_md'] - footage_df['entry_md']

        # Aggregate by section (in case trajectory re-enters)
        summary = footage_df.groupby('section_conc').agg({
            'footage': 'sum',
            'entry_md': 'min',
            'exit_md': 'max'
        }).reset_index()

        return summary

    def parse_tsr_from_conc(self, conc: str) -> dict:
        """
        Parse Township/Section/Range from concatenated identifier.

        Args:
            conc: Concatenated identifier (e.g., '02041N02WU').

        Returns:
            Dictionary with parsed components.
        """
        if len(conc) < 9:
            return {}

        try:
            return {
                'section': int(conc[:2]),
                'township': int(conc[2:4]),
                'township_dir': conc[4],
                'range': int(conc[5:7]),
                'range_dir': conc[7],
                'baseline': conc[8] if len(conc) > 8 else ''
            }
        except (ValueError, IndexError):
            return {}

    def format_tsr_label(self, conc: str) -> str:
        """
        Format TSR as readable label.

        Args:
            conc: Concatenated identifier.

        Returns:
            Formatted label (e.g., "02 04N 02W U").
        """
        parsed = self.parse_tsr_from_conc(conc)
        if not parsed:
            return conc

        return (
            f"{parsed['section']:02d} "
            f"{parsed['township']:02d}{parsed['township_dir']} "
            f"{parsed['range']:02d}{parsed['range_dir']} "
            f"{parsed.get('baseline', '')}"
        )
