"""
Section boundary segmentation for EToolsV3.

This module segments plat section polygons into N/S/E/W boundaries
for clearance calculations.
"""

from typing import Tuple, List
import numpy as np
from shapely.geometry import Polygon, LineString, Point

from data.models.plat import PlatBoundary
from config.logging_config import get_logger

logger = get_logger(__name__)


class BoundarySegmenter:
    """Segments section boundaries into directional components."""

    def __init__(self):
        """Initialize boundary segmenter."""
        self.logger = logger

    def segment_polygon_boundaries(self, polygon: Polygon, conc: str) -> PlatBoundary:
        """
        Segment polygon into N/S/E/W boundaries.

        Args:
            polygon: Section polygon geometry.
            conc: Section concatenated identifier.

        Returns:
            PlatBoundary with segmented boundaries.
        """
        # Get exterior coordinates
        coords = list(polygon.exterior.coords)

        if len(coords) < 4:
            self.logger.warning(f"Polygon {conc} has fewer than 4 vertices")
            return PlatBoundary(conc=conc, polygon=polygon)

        # Calculate centroid
        centroid = polygon.centroid

        # Classify each edge
        north_edges = []
        south_edges = []
        east_edges = []
        west_edges = []

        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]
            edge_type = self._classify_edge(p1, p2, (centroid.x, centroid.y))

            if edge_type == 'north':
                north_edges.append((p1, p2))
            elif edge_type == 'south':
                south_edges.append((p1, p2))
            elif edge_type == 'east':
                east_edges.append((p1, p2))
            elif edge_type == 'west':
                west_edges.append((p1, p2))

        # Flatten edges to continuous boundaries
        north_boundary = self._flatten_edges(north_edges)
        south_boundary = self._flatten_edges(south_edges)
        east_boundary = self._flatten_edges(east_edges)
        west_boundary = self._flatten_edges(west_edges)

        # Calculate lengths
        north_length = self._calculate_boundary_length(north_boundary)
        south_length = self._calculate_boundary_length(south_boundary)
        east_length = self._calculate_boundary_length(east_boundary)
        west_length = self._calculate_boundary_length(west_boundary)

        return PlatBoundary(
            conc=conc,
            polygon=polygon,
            north_boundary=north_boundary,
            south_boundary=south_boundary,
            east_boundary=east_boundary,
            west_boundary=west_boundary,
            north_length=north_length,
            south_length=south_length,
            east_length=east_length,
            west_length=west_length
        )

    def _classify_edge(
        self,
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        centroid: Tuple[float, float]
    ) -> str:
        """
        Classify edge as north, south, east, or west.

        Args:
            p1: First point (easting, northing).
            p2: Second point (easting, northing).
            centroid: Polygon centroid (easting, northing).

        Returns:
            Edge classification: 'north', 'south', 'east', or 'west'.
        """
        # Calculate edge midpoint
        mid_e = (p1[0] + p2[0]) / 2
        mid_n = (p1[1] + p2[1]) / 2

        # Calculate edge direction
        de = p2[0] - p1[0]
        dn = p2[1] - p1[1]

        # Determine if edge is more horizontal or vertical
        if abs(de) > abs(dn):
            # More horizontal - north or south
            if mid_n > centroid[1]:
                return 'north'
            else:
                return 'south'
        else:
            # More vertical - east or west
            if mid_e > centroid[0]:
                return 'east'
            else:
                return 'west'

    def _flatten_edges(self, edges: List[Tuple[Tuple[float, float], Tuple[float, float]]]) -> List[Tuple[float, float]]:
        """
        Flatten list of edges into continuous boundary.

        Args:
            edges: List of edge tuples (p1, p2).

        Returns:
            List of points forming continuous boundary.
        """
        if not edges:
            return []

        # Start with first edge
        boundary = [edges[0][0], edges[0][1]]

        # Add subsequent edges
        for edge in edges[1:]:
            # Check if edge connects to last point
            if self._points_close(boundary[-1], edge[0]):
                boundary.append(edge[1])
            elif self._points_close(boundary[-1], edge[1]):
                boundary.append(edge[0])
            else:
                # Non-contiguous edge, add both points
                boundary.extend([edge[0], edge[1]])

        return boundary

    def _points_close(self, p1: Tuple[float, float], p2: Tuple[float, float], tolerance: float = 1.0) -> bool:
        """Check if two points are within tolerance."""
        dist = np.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
        return dist < tolerance

    def _calculate_boundary_length(self, boundary: List[Tuple[float, float]]) -> float:
        """
        Calculate total length of boundary.

        Args:
            boundary: List of boundary points.

        Returns:
            Total length in feet.
        """
        if len(boundary) < 2:
            return 0.0

        total_length = 0.0
        for i in range(len(boundary) - 1):
            p1 = boundary[i]
            p2 = boundary[i + 1]
            length = np.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
            total_length += length

        return total_length

    def get_boundary_line(self, boundary: List[Tuple[float, float]]) -> LineString:
        """
        Convert boundary points to LineString.

        Args:
            boundary: List of boundary points.

        Returns:
            LineString geometry.
        """
        if len(boundary) < 2:
            return LineString()

        return LineString(boundary)
