"""
Clearance calculation for EToolsV3.

This module calculates distances from wellbore trajectory points
to section boundaries (FNL, FSL, FEL, FWL).
"""

from typing import Tuple, Optional
import numpy as np
import pandas as pd
from shapely.geometry import Point, LineString
from shapely.ops import nearest_points

from data.models.clearance import ClearancePoint, ClearanceResults
from data.models.plat import PlatBoundary
from config.logging_config import get_logger

logger = get_logger(__name__)


class ClearanceCalculator:
    """Calculates clearances from wellbore to section boundaries."""

    def __init__(self):
        """Initialize clearance calculator."""
        self.logger = logger

    def calculate_clearances(
        self,
        survey_df: pd.DataFrame,
        plat_boundaries: dict
    ) -> ClearanceResults:
        """
        Calculate clearances for all survey points.

        Args:
            survey_df: Survey DataFrame with easting, northing, section_conc columns.
            plat_boundaries: Dictionary mapping conc to PlatBoundary objects.

        Returns:
            ClearanceResults with all clearance measurements.
        """
        clearance_points = []

        for idx, row in survey_df.iterrows():
            if pd.isna(row.get('section_conc')):
                continue

            point = Point(row['easting'], row['northing'])
            section_conc = row['section_conc']

            # Get boundary for this section
            boundary = plat_boundaries.get(section_conc)
            if boundary is None:
                self.logger.warning(f"No boundary found for section {section_conc}")
                continue

            # Calculate distances to each boundary
            fnl = self._distance_to_boundary(point, boundary.north_boundary)
            fsl = self._distance_to_boundary(point, boundary.south_boundary)
            fel = self._distance_to_boundary(point, boundary.east_boundary)
            fwl = self._distance_to_boundary(point, boundary.west_boundary)

            # Find minimum clearance
            distances = {'N': fnl, 'S': fsl, 'E': fel, 'W': fwl}
            min_dir = min(distances, key=distances.get)
            min_clearance = distances[min_dir]

            # Check if point is in section
            is_in_section = boundary.polygon.contains(point)

            clearance_point = {
                'measured_depth': row['measured_depth'],
                'tvd': row.get('tvd', 0.0),
                'easting': row['easting'],
                'northing': row['northing'],
                'section_conc': section_conc,
                'section_label': row.get('section_label', ''),
                'fnl': fnl,
                'fsl': fsl,
                'fel': fel,
                'fwl': fwl,
                'min_clearance': min_clearance,
                'min_clearance_direction': min_dir,
                'is_in_section': is_in_section,
                'crosses_boundary': False
            }

            clearance_points.append(clearance_point)

        # Create DataFrame
        clearances_df = pd.DataFrame(clearance_points)

        # Detect boundary crossings
        if len(clearances_df) > 1:
            clearances_df['crosses_boundary'] = (
                clearances_df['section_conc'] != clearances_df['section_conc'].shift()
            )

        # Create results object
        results = ClearanceResults(
            api_number=survey_df.iloc[0].get('api_number', ''),
            lateral_name=survey_df.iloc[0].get('lateral_name', ''),
            clearances=clearances_df
        )

        self.logger.info(
            f"Calculated clearances for {len(clearances_df)} points, "
            f"Min overall: {results.min_overall_clearance:.1f} ft"
        )

        return results

    def _distance_to_boundary(
        self,
        point: Point,
        boundary: list
    ) -> float:
        """
        Calculate perpendicular distance from point to boundary.

        Args:
            point: Point to measure from.
            boundary: List of boundary coordinate tuples.

        Returns:
            Distance in feet.
        """
        if not boundary or len(boundary) < 2:
            return np.inf

        # Create LineString from boundary
        boundary_line = LineString(boundary)

        # Calculate distance
        distance = point.distance(boundary_line)

        return distance

    def calculate_point_to_line_distance(
        self,
        point: Tuple[float, float],
        line_start: Tuple[float, float],
        line_end: Tuple[float, float]
    ) -> float:
        """
        Calculate perpendicular distance from point to line segment.

        Args:
            point: Point coordinates (easting, northing).
            line_start: Line start coordinates.
            line_end: Line end coordinates.

        Returns:
            Perpendicular distance in feet.
        """
        px, py = point
        x1, y1 = line_start
        x2, y2 = line_end

        # Line segment vector
        dx = x2 - x1
        dy = y2 - y1

        # If line segment is a point, return distance to point
        if dx == 0 and dy == 0:
            return np.sqrt((px - x1)**2 + (py - y1)**2)

        # Parameter t of projection onto line
        t = ((px - x1) * dx + (py - y1) * dy) / (dx**2 + dy**2)

        # Clamp t to [0, 1] to stay on segment
        t = max(0, min(1, t))

        # Closest point on segment
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy

        # Distance
        distance = np.sqrt((px - closest_x)**2 + (py - closest_y)**2)

        return distance

    def calculate_vectorized_distances(
        self,
        eastings: np.ndarray,
        northings: np.ndarray,
        boundary: list
    ) -> np.ndarray:
        """
        Calculate distances for multiple points at once (vectorized).

        Args:
            eastings: Array of easting coordinates.
            northings: Array of northing coordinates.
            boundary: Boundary points.

        Returns:
            Array of distances.
        """
        if not boundary or len(boundary) < 2:
            return np.full(len(eastings), np.inf)

        boundary_line = LineString(boundary)
        distances = []

        for e, n in zip(eastings, northings):
            point = Point(e, n)
            dist = point.distance(boundary_line)
            distances.append(dist)

        return np.array(distances)
