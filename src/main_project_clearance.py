"""
DXClearance.py
Author: Colton Goodrich
Date: 11/10/2024
Python Version: 3.12
Clearance processing for wellbore survey data and plat boundaries.

This module provides functionality for calculating clearance distances between
wellbore trajectories and plat boundaries, handling spatial relationships and
boundary analysis.

Key Features:
    - Plat boundary clearance calculations (FEL, FWL, FNL, FSL)
    - Multi-plat spatial relationship handling
    - Concentration assignment for survey points
    - Boundary segmentation and distance analysis
    - Integration with shapely geometry operations
    - Support for adjacent plat relationships

Typical usage example:
    clearance = ClearanceProcess(
        df_used=survey_df,
        df_plat=plat_boundaries,
        adjacent_plats=adjacent_plats_df
    )

    results = clearance.clearance_data
    footages = clearance.whole_df

Notes:
    - Requires input DataFrames with specific structure:
        * Survey points with shape geometry
        * Plat boundaries with polygon geometry
        * Adjacent plat definitions with geometry and Conc values
    - Handles complex plat boundary relationships
    - Supports multiple concentration zones
    - Integrates with spatial analysis tools
    - Provides cardinal direction clearances

Dependencies:
    - pandas
    - numpy
    - shapely
    - geopandas (optional)
    - scipy
"""
import sqlite3
import geopandas as gpd
from scipy.spatial import ConvexHull
from rdp import rdp
from shapely.geometry import Point, Polygon
import numpy.typing as npt
import pandas as pd
import numpy as np
import math
from typing import Optional, Tuple, Union, TypeVar, List, Any, Dict, Set
from numpy.typing import NDArray
import os

T = TypeVar('T', bound=List[Any])


def _reorganize_lst_points_with_angle(
        lst: List[List[float]],
        centroid: List[float]
) -> List[List[float]]:
    """Reorganizes polygon points by calculating angles relative to centroid.

    Calculates the angular position of each point relative to the centroid and
    appends this angle value to each point. Angles are measured in degrees from
    0 to 360, with 0 degrees pointing east and increasing counterclockwise.

    Args:
        lst: List of polygon vertex coordinates as [x, y] pairs
        centroid: Centroid coordinates as [x, y] for angular reference

    Returns:
        List of points with appended angle values: [[x, y, angle], ...]

    Notes:
        - Angles are calculated using atan2 for proper quadrant handling
        - Results are normalized to 0-360 degree range
        - Original point coordinates are preserved in returned list
    """
    # Calculate angles relative to centroid and append to points
    lst_arrange = [
        list(i) + [
            (math.degrees(
                math.atan2(centroid[1] - i[1], centroid[0] - i[0])
            ) + 360) % 360
        ]
        for i in lst
    ]

    return lst_arrange


def _calculate_well_to_line_clearance_detailed(
        well_trajectory: Union[List[List[float]], npt.NDArray],
        line_points: Union[List[List[float]], npt.NDArray]
) -> List[Dict[str, Any]]:
    """Calculates detailed clearance metrics between well trajectory and boundary line.

    Performs vectorized calculation of distances, projection parameters, and
    intersection angles between well trajectory points and a boundary line segment.
    Optimized for performance with large trajectory datasets.

    Args:
        well_trajectory: Array of well trajectory points as [x, y] coordinates
        line_points: Two points defining the boundary line segment as [[x1, y1], [x2, y2]]

    Returns:
        List of dictionaries containing detailed clearance metrics for each trajectory point:
        - point_index: Index of the trajectory point
        - well_point: Coordinates of trajectory point [x, y]
        - distance: Perpendicular distance to line segment
        - closest_surface_point: Coordinates of closest point on line segment
        - intersection_angle: Angle between well-to-surface vector and line segment (degrees)
        - original_segment: Original line segment points

    Notes:
        - Uses vectorized operations for computational efficiency
        - Handles numerical stability with epsilon padding
        - Calculates acute angles for consistent interpretation
        - Projects points onto extended line and clamps to segment bounds
    """
    # Convert inputs to numpy arrays
    well_trajectory = np.array(well_trajectory)
    line_points = np.array(line_points)
    p1, p2 = line_points
    line_vector = p2 - p1
    line_length_squared = np.sum(line_vector ** 2)

    # Vectorized calculation of projection parameters
    well_points_diff = well_trajectory - p1
    t = np.divide(
        np.sum(well_points_diff * line_vector, axis=1),
        line_length_squared,
        where=line_length_squared != 0
    )

    # Clamp projection parameters to segment bounds
    t = np.clip(t, 0, 1)

    # Calculate closest points for all trajectory points
    closest_points = p1 + t[:, np.newaxis] * line_vector

    # Calculate distances using L2 norm
    distances = np.linalg.norm(well_trajectory - closest_points, axis=1)

    # Calculate intersection angles
    well_to_closest = well_trajectory - closest_points
    norm_well_to_closest = np.linalg.norm(well_to_closest, axis=1)
    norm_line_vector = np.linalg.norm(line_vector)

    # Calculate angles with numerical stability
    epsilon = 1e-10
    angle_cos = np.sum(well_to_closest * line_vector, axis=1) / (
            norm_well_to_closest * norm_line_vector + epsilon
    )
    angles = np.degrees(np.arccos(np.clip(angle_cos, -1, 1)))

    # Convert obtuse angles to acute
    angles = np.where(angles > 90, 180 - angles, angles)

    # Format results
    result = [
        {
            "point_index": i,
            "well_point": well_trajectory[i],
            "distance": distances[i],
            "closest_surface_point": closest_points[i],
            "intersection_angle": angles[i],
            "original_segment": line_points
        }
        for i in range(len(well_trajectory))
    ]

    return result


def _optimized_corner_process(
        trajectory: Union[List[List[float]], npt.NDArray]
) -> List[List[float]]:
    """Identifies corner points in a polygon boundary with adaptive simplification.

    Uses convex hull and Ramer-Douglas-Peucker (RDP) algorithm to simplify polygon
    boundaries while preserving significant corner points. Adaptively adjusts
    simplification epsilon based on coordinate scale.

    Args:
        trajectory: List or array of polygon vertices as [x, y] coordinates

    Returns:
        List of detected corner points with centroid-relative angles:
        [[x, y, angle], ...] where angle is in degrees (0-360)

    Notes:
        - Uses ConvexHull for robust point ordering
        - Applies adaptive RDP simplification based on coordinate magnitude
        - Identifies corners using angle threshold detection
        - Returns corner coordinates with centroid-relative angles
        - Scale-aware processing handles both survey and plat coordinate systems
    """
    # Convert to numpy array for vector operations
    trajectory = np.array(trajectory)

    # Calculate polygon centroid
    centroid = Polygon(trajectory).centroid.coords[0]

    # Create clockwise point ordering using ConvexHull
    hull = ConvexHull(trajectory)
    trajectory = trajectory[hull.vertices]

    # Apply adaptive RDP simplification
    epsilon = 0.002 if (35 < trajectory[0, 0] < 55 or 35 < trajectory[0, 1] < 55) else 200
    simplified = rdp(np.vstack((trajectory, trajectory[0])), epsilon=epsilon)

    # Calculate sequential angle differences
    vectors = np.diff(simplified, axis=0)
    angles = np.arctan2(vectors[:, 1], vectors[:, 0])
    angle_diffs = np.diff(angles, append=angles[0] - 2 * np.pi)
    angle_diffs = np.abs(
        np.where(angle_diffs > np.pi, angle_diffs - 2 * np.pi, angle_diffs)
    )

    # Identify corners using angle threshold
    corners = simplified[1:][angle_diffs > np.pi / 35]

    # Calculate centroid-relative angles
    centroid_vectors = corners - centroid
    centroid_angles = (
                              np.degrees(
                                  np.arctan2(centroid_vectors[:, 1], centroid_vectors[:, 0])
                              ) + 360
                      ) % 360

    # Combine corner coordinates with angles
    result = np.column_stack((corners, centroid_angles))

    return result.tolist()


def _remove_dupes_list_of_lists(lst: List[List[T]]) -> List[List[T]]:
    """Removes duplicate sublists from a list of lists while preserving order.

    Efficiently identifies and removes duplicate sublists by converting to a hashable
    representation, maintaining the original order of first appearance.

    Args:
        lst: List containing sublists that may have duplicates

    Returns:
        List with duplicate sublists removed, preserving original list types

    Notes:
        - Preserves the first occurrence of each unique sublist
        - Maintains original data types (sublists stay as lists)
        - Uses set lookup for O(1) membership testing
        - Memory usage scales with number of unique sublists
    """
    # Initialize data structures for tracking duplicates
    dup_free: List[List[T]] = []
    dup_free_set: set = set()

    # Process each sublist while maintaining order
    for x in lst:
        x_tuple = tuple(x)  # Convert to hashable type
        if x_tuple not in dup_free_set:
            dup_free.append(x)  # Keep original list type
            dup_free_set.add(x_tuple)

    return dup_free


def _remove_duplicates_preserve_order(points_list: List[T]) -> List[Tuple]:
    """Removes duplicate points while preserving order, converting results to tuples.

    Efficiently removes duplicate entries from a list of points/coordinates by
    converting to tuples for hashable comparison. Maintains original ordering
    while returning results as tuples.

    Args:
        points_list: List of lists containing coordinate/point data.
            Inner lists should contain comparable elements (typically numbers).

    Returns:
        List of tuples containing unique points in their original order
        of first appearance. All points are converted to tuples in output.

    Notes:
        - Uses set for O(1) lookup efficiency
        - Preserves first occurrence ordering
        - Converts all points to tuples in output
        - Memory usage is O(n) where n is number of unique points

    Examples:
        >>> coords = [[1,2], [3,4], [1,2], [5,6]]
        >>> _remove_duplicates_preserve_order(coords)
        [(1,2), (3,4), (5,6)]

        >>> points = [[0.5,1.0], [0.5,1.0], [2.0,3.0]]
        >>> _remove_duplicates_preserve_order(points)
        [(0.5,1.0), (2.0,3.0)]
    """
    # Initialize tracking set and result list
    seen: Set[tuple] = set()
    result: List[tuple] = []

    # Process each point
    for point in points_list:
        point_tuple = tuple(point)  # Convert to hashable type
        if point_tuple not in seen:
            result.append(point_tuple)  # Store as tuple
            seen.add(point_tuple)

    return result


def _consolidate_columns(
        df: pd.DataFrame,
        num_segments: int,
        dir_val: str
) -> pd.DataFrame:
    """Consolidates segmented distance measurements and related data into single columns.

    Takes a DataFrame with multiple segment columns and consolidates them based on
    minimum distance values, handling missing data appropriately.

    Args:
        df: Input DataFrame containing segmented measurements
            Must have columns formatted as:
            - distance{i}_{dir_val}
            - closest_surface_point{i}_{dir_val}
            - intersection_angle{i}_{dir_val}
            - segments{i}_{dir_val}
            where i ranges from 1 to num_segments
        num_segments: Number of segment columns to process
        dir_val: Direction value suffix for column names

    Returns:
        DataFrame with consolidated columns:
        - distance_{dir_val}
        - closest_surface_point_{dir_val}
        - intersection_angle_{dir_val}
        - segments_{dir_val}

    Notes:
        - Handles missing values by returning NaN for all fields if no valid distances
        - Selects values based on minimum distance when multiple valid segments exist
        - Preserves row order from input DataFrame
        - All consolidated columns include dir_val suffix

    Example:
        >>> df = pd.DataFrame({
        ...     'distance1_up': [1.0, np.nan],
        ...     'distance2_up': [2.0, 3.0]})
        >>> _consolidate_columns(df, 2, 'up')
    """
    # Initialize list to store consolidated results
    consolidated: List[Dict[str, Any]] = []

    # Process each row
    for _, row in df.iterrows():
        # Find valid segment indices (non-NaN distances)
        valid_indices = [i for i in range(1, num_segments + 1)
                         if pd.notna(row[f'distance{i}_{dir_val}'])]

        # Handle case with no valid distances
        if not valid_indices:
            consolidated.append({
                'distance': np.nan,
                'closest_surface_point': np.nan,
                'intersection_angle': np.nan,
                'segments': np.nan,
            })
        else:
            # Find index with minimum distance
            min_distance_index = min(valid_indices,
                                     key=lambda i: row[f'distance{i}_{dir_val}'])

            # Consolidate values from minimum distance segment
            consolidated.append({
                f'distance_{dir_val}': row[f'distance{min_distance_index}_{dir_val}'],
                f'closest_surface_point_{dir_val}': row[
                    f'closest_surface_point{min_distance_index}_{dir_val}'],
                f'intersection_angle_{dir_val}': row[f'intersection_angle{min_distance_index}_{dir_val}'],
                f'segments_{dir_val}': row[f'segments{min_distance_index}_{dir_val}']
            })

    return pd.DataFrame(consolidated)


def _process_row(
        row: pd.Series,
        num_segments: int,
        dir_val: str
) -> pd.Series:
    """Process row data to keep only the segment with angle closest to 90 degrees.

    Analyzes intersection angles across segments and preserves only the data from
    the segment whose angle is closest to 90 degrees, setting all other segments
    to NaN.

    Args:
        row: Pandas Series containing segment data with columns formatted as:
            - intersection_angle{i}_{dir_val}
            - distance{i}_{dir_val}
            - closest_surface_point{i}_{dir_val}
            - segments{i}_{dir_val}
            where i ranges from 1 to num_segments
        num_segments: Number of segments to process
        dir_val: Direction value suffix for column names

    Returns:
        Modified Pandas Series with all segments except the one closest
        to 90 degrees set to NaN

    Notes:
        - Modifies row data in-place
        - Uses absolute difference from 90 degrees for comparison
        - Sets all values to NaN for segments not closest to 90 degrees
        - Preserves original data structure and column names

    Example:
        >>> row = pd.Series({
        ...     'intersection_angle1_up': 85,
        ...     'intersection_angle2_up': 45,
        ...     'distance1_up': 1.0,
        ...     'distance2_up': 2.0
        ... })
        >>> processed = _process_row(row, 2, 'up')
        # Will keep segment 1 data (85 degrees) and set segment 2 to NaN
    """
    # Extract all intersection angles for comparison
    angles = [row[f'intersection_angle{i}_{dir_val}']
              for i in range(1, num_segments + 1)]

    # Find index of angle closest to 90 degrees
    closest_to_90 = min(range(len(angles)),
                        key=lambda i: abs(angles[i] - 90))

    # Set all segments except closest to 90 to NaN
    for i in range(1, num_segments + 1):
        if i != closest_to_90 + 1:  # Add 1 since segment numbering starts at 1
            row[f'distance{i}_{dir_val}'] = np.nan
            row[f'closest_surface_point{i}_{dir_val}'] = np.nan
            row[f'intersection_angle{i}_{dir_val}'] = np.nan
            row[f'segments{i}_{dir_val}'] = np.nan

    return row


def _results_finder(
        segments: List[List[float]],
        dir_val: str,
        well_trajectory: NDArray[np.float64]
) -> pd.DataFrame:
    """Calculates clearance distances between well trajectory and boundary segments.

    Performs vectorized computation of distances, closest points, and intersection angles
    between well trajectory points and multiple boundary line segments. Optimized for
    performance with large datasets.

    Args:
        segments: List of line segments, each defined by two points [[x1, y1], [x2, y2]]
        dir_val: Direction identifier string ('East', 'West', 'North', 'South')
        well_trajectory: Array of trajectory points with format [[x, y, index], ...]

    Returns:
        DataFrame containing clearance metrics for each trajectory point:
        - point_index: Index of trajectory point
        - distance_{dir_val}: Perpendicular distance to closest segment (in feet)
        - closest_surface_point_{dir_val}: Coordinates of closest point on segment
        - intersection_angle_{dir_val}: Angle between well-to-surface vector and segment
        - segments_{dir_val}: The line segment with minimum distance

    Notes:
        - Uses vectorized operations for computational efficiency
        - Converts distance units from meters to feet (dividing by 0.3048)
        - Calculates acute angles (0-90°) for consistent interpretation
        - Returns minimum distance results for each trajectory point
    """
    # Extract trajectory components for vectorized operations
    well_indices: NDArray = well_trajectory[:, 2]
    well_points: NDArray = well_trajectory[:, :2]

    # Convert segments to numpy array for vectorized math
    segments: NDArray = np.array(segments)
    p1: NDArray = segments[:, 0, :]  # Start points of segments
    p2: NDArray = segments[:, 1, :]  # End points of segments
    segment_vectors: NDArray = p2 - p1
    segment_lengths_squared: NDArray = np.sum(segment_vectors ** 2, axis=1)

    # Pre-allocate result lists
    distances: List[float] = []
    closest_points: List[NDArray] = []
    angles: List[float] = []
    min_dist_indices: List[int] = []

    # Process each well point against all segments
    for well_point in well_points:
        # Calculate projection parameters
        well_point_diff: NDArray = well_point - p1
        t: NDArray = np.sum(well_point_diff * segment_vectors, axis=1) / segment_lengths_squared
        t = np.clip(t, 0, 1)  # Constrain to segment bounds

        # Find closest points and distances
        closest_point: NDArray = p1 + t[:, None] * segment_vectors
        distance: NDArray = np.linalg.norm(well_point - closest_point, axis=1)

        # Calculate intersection angles
        vector_to_closest: NDArray = closest_point - well_point
        norm_well_to_closest: NDArray = np.linalg.norm(vector_to_closest, axis=1)
        norm_segment_vectors: NDArray = np.linalg.norm(segment_vectors, axis=1)

        # Calculate and adjust angles
        cos_angles: NDArray = np.sum(vector_to_closest * segment_vectors, axis=1) / (
                norm_well_to_closest * norm_segment_vectors + 1e-10
        )
        angle: NDArray = np.degrees(np.arccos(np.clip(cos_angles, -1, 1)))
        angle = np.where(angle > 90, 180 - angle, angle)

        # Store minimum distance results
        min_idx: int = np.argmin(distance)
        distances.append(distance[min_idx])
        closest_points.append(closest_point[min_idx])
        angles.append(angle[min_idx])
        min_dist_indices.append(min_idx)

    # Format results into DataFrame
    results_df = pd.DataFrame({
        "point_index": well_indices,
        f"distance_{dir_val}": np.array(distances) / 0.3048,  # Convert m to ft
        f"closest_surface_point_{dir_val}": closest_points,
        f"intersection_angle_{dir_val}": angles,
        f"segments_{dir_val}": [segments[i] for i in min_dist_indices]
    })

    return results_df


def _regular_corner_class(
        corners: List[List[float]],
        data_lengths: List[List[float]]
) -> List[List[List[float]]]:
    """Classifies and organizes polygon corner points into directional sides.

    Processes corner points and associated data points to group them into four sides
    (west, north, east, south) based on their angular positions relative to the polygon.

    Args:
        corners: List of corner points with format [x, y, angle]
        data_lengths: List of polygon points with format [x, y, angle]

    Returns:
        List containing four lists representing the sides in order:
        [west_side, north_side, east_side, south_side]
        Each side list contains points in proper geometric order

    Notes:
        - Angles are expected in degrees (0-360)
        - West side handles angle wrap-around at 0/360 degrees
        - Points are deduplicated while preserving order
        - Empty lists are returned for sides with missing corner points
    """

    def find_corner_point(
            corners: List[List[float]],
            min_angle: float,
            max_angle: float
    ) -> Optional[List[float]]:
        """Finds first corner point within specified angle range.

        Args:
            corners: List of corner points [x, y, angle]
            min_angle: Minimum angle in degrees (exclusive)
            max_angle: Maximum angle in degrees (inclusive)

        Returns:
            Corner point if found, None otherwise
        """
        return next((i for i in corners if min_angle < i[-1] <= max_angle), None)

    def find_side_points(
            data_lengths: List[List[float]],
            start_angle: float,
            end_angle: float,
            reverse: bool = False
    ) -> List[List[float]]:
        """Extracts points between start and end angles.

        Args:
            data_lengths: List of points [x, y, angle]
            start_angle: Starting angle in degrees (inclusive)
            end_angle: Ending angle in degrees (inclusive)
            reverse: If True, reverses point order

        Returns:
            Deduplicated list of points in specified order
        """
        points = [i for i in data_lengths if start_angle <= i[-1] <= end_angle]
        return _remove_duplicates_preserve_order(points[::-1] if reverse else points)

    def get_side(
            data_lengths: List[List[float]],
            corners: List[List[float]],
            start_angle: float,
            end_angle: float,
            reverse: bool = False
    ) -> List[List[float]]:
        """Extracts points forming one side of the polygon.

        Args:
            data_lengths: All polygon points
            corners: Corner points only
            start_angle: Starting angle for side
            end_angle: Ending angle for side
            reverse: If True, reverses point order

        Returns:
            List of points forming the requested side
        """
        start_point = find_corner_point(corners, start_angle, end_angle)
        end_point = find_corner_point(corners, start_angle - 90, start_angle)

        if start_point is None or end_point is None:
            return []

        start_idx = data_lengths.index(start_point)
        end_idx = data_lengths.index(end_point)

        return find_side_points(data_lengths,
                                data_lengths[end_idx][-1],
                                data_lengths[start_idx][-1],
                                reverse)

    # Process cardinal sides
    south_side = get_side(data_lengths, corners, 90, 180, reverse=True)
    east_side = get_side(data_lengths, corners, 180, 270, reverse=True)
    north_side = get_side(data_lengths, corners, 270, 360, reverse=True)

    # Handle west side angle wrap-around
    nw_point = find_corner_point(corners, 270, 360)
    sw_point = find_corner_point(corners, 0, 90)

    # Construct west side handling 0/360 degree boundary
    if nw_point is not None and sw_point is not None:
        nw_idx = data_lengths.index(nw_point)
        sw_idx = data_lengths.index(sw_point)
        west_side = [sw_point] + [
            i for i in data_lengths
            if (i[-1] > data_lengths[nw_idx][-1] or i[-1] < data_lengths[sw_idx][-1])
               and i not in (east_side + south_side + north_side)
        ] + [nw_point]
        west_side = _remove_duplicates_preserve_order(west_side)
    else:
        west_side = []

    return [west_side, north_side, east_side, south_side]


def _corner_generator_process(
        data_lengths: List[List[float]]
) -> Tuple[List[List[float]], List[List[List[float]]]]:
    """Processes polygon points to identify corners and classify sides.

    Identifies corner points in a polygon and organizes all polygon points into
    directional sides (west, north, east, south) for boundary analysis.

    Args:
        data_lengths: List of polygon vertex coordinates as [x, y] pairs

    Returns:
        Tuple containing:
        - List of corner points with angles: [[x, y, angle], ...]
        - List of four directional sides: [west_side, north_side, east_side, south_side]
          where each side is a list of points with angles

    Notes:
        - Uses optimized corner detection with adaptive simplification
        - Calculates centroid-relative angles for consistent orientation
        - Sorts and deduplicates points to ensure clean boundaries
        - Handles polygon sides with proper geometric ordering
    """
    # Optimize corner point detection
    corner_arrange = _optimized_corner_process(data_lengths)

    # Calculate polygon centroid for angle references
    centroid = Polygon(data_lengths).centroid
    centroid_point = [centroid.x, centroid.y]

    # Calculate angles relative to centroid
    corner_arrange = _reorganize_lst_points_with_angle(
        [i[:2] for i in corner_arrange],
        centroid_point
    )

    # Sort and deduplicate corner points
    corners = sorted(corner_arrange, key=lambda r: r[-1])
    corners = _remove_dupes_list_of_lists(corners)

    # Process all points with angles
    data_lengths = _reorganize_lst_points_with_angle(data_lengths, centroid_point)
    data_lengths = sorted(data_lengths, key=lambda r: r[-1])

    # Ensure consistent list format
    corners = [list(i) for i in corners]

    # Classify points into directional sides
    all_data = _regular_corner_class(corners, data_lengths)

    return corners, all_data


def _id_sides(polygon: List[List[float]]) -> Tuple[List[List[List[float]]], ...]:
    """Identifies and segments the sides of a polygon into directional components.

    Takes a polygon defined by points and returns segmented lists of points organized
    by cardinal direction (right/east, left/west, up/north, down/south). Points are
    sorted and paired into segments for each side.

    Args:
        polygon: List of [x,y] coordinates defining the polygon vertices in order

    Returns:
        Tuple containing four lists of segments, in order:
            - right_lst_segments: List of point pairs for eastern side
            - left_lst_segments: List of point pairs for western side
            - up_lst_segments: List of point pairs for northern side
            - down_lst_segments: List of point pairs for southern side
        Each segment is a pair of [x,y] coordinates defining start and end points

    Notes:
        - Uses _corner_generator_process() to identify corners and classify sides
        - Points are sorted based on appropriate coordinate for each direction:
          * East/West sides sort by y-coordinate
          * North/South sides sort by x-coordinate
        - Segments are created as sequential pairs of sorted points
    """
    # Process corners and generate initial side classifications
    corners, sides_generated = _corner_generator_process(polygon)

    # Remove angle information from classified points
    sides_generated = [[j[:-1] for j in i] for i in sides_generated]

    # Extract directional sides
    left_lst, up_lst, right_lst, down_lst = (
        sides_generated[0],  # West
        sides_generated[1],  # North
        sides_generated[2],  # East
        sides_generated[3]  # South
    )

    # Sort points appropriately for each direction
    left_lst = sorted(left_lst, key=lambda x: x[1])  # Sort west points by y
    up_lst = sorted(up_lst, key=lambda x: x[0])  # Sort north points by x
    right_lst = sorted(right_lst, key=lambda x: x[1], reverse=True)  # Sort east points by y descending
    down_lst = sorted(down_lst, key=lambda x: x[0], reverse=True)  # Sort south points by x descending

    # Generate segments as sequential point pairs
    right_lst_segments = [[right_lst[i], right_lst[i + 1]] for i in range(len(right_lst) - 1)]
    left_lst_segments = [[left_lst[i], left_lst[i + 1]] for i in range(len(left_lst) - 1)]
    down_lst_segments = [[down_lst[i], down_lst[i + 1]] for i in range(len(down_lst) - 1)]
    up_lst_segments = [[up_lst[i], up_lst[i + 1]] for i in range(len(up_lst) - 1)]

    return right_lst_segments, left_lst_segments, up_lst_segments, down_lst_segments


def find_conc_part(test_plat: pd.DataFrame, point_df: pd.DataFrame) -> pd.DataFrame:
    """Assigns concentration zones to points using spatial join.

    Performs a spatial join between survey points and plat polygons to determine
    which concentration zone contains each point. Uses geopandas for efficient
    spatial operations.

    Args:
        test_plat: DataFrame containing plat polygons with 'geometry' column
        point_df: DataFrame containing survey points with 'shp_pt' column

    Returns:
        DataFrame with survey points assigned to concentration zones

    Notes:
        - Converts input DataFrames to GeoDataFrames if needed
        - Uses 'within' predicate for spatial relationship testing
        - Joins concentration information to original point data
        - Handles coordinate reference system alignment
        - Final step in concentration assignment workflow
    """
    # Convert test_plat to GeoDataFrame if not already
    if not isinstance(test_plat, gpd.GeoDataFrame):
        test_plat_gdf = gpd.GeoDataFrame(test_plat, geometry='geometry')
    else:
        test_plat_gdf = test_plat

    # Convert point_df to GeoDataFrame using shp_pt column
    plat_gdf = gpd.GeoDataFrame(
        point_df,
        geometry=point_df['shp_pt'],
        crs=test_plat_gdf.crs  # Ensure both GeoDataFrames have the same CRS
    )

    # Perform spatial join to determine which plat contains each point
    joined = gpd.sjoin(plat_gdf, test_plat_gdf[['Conc', 'label', 'geometry']],
                      how='inner', predicate='within')

    # Convert result back to regular DataFrame, dropping geometry column
    df_out = pd.DataFrame(joined.drop(columns='geometry'))
    return df_out


class ClearanceProcess:
    """Processes clearance data for well surveys and plats.

    This class handles the processing of well survey data in relation to plat boundaries
    and adjacent plats, calculating concentrations and clearance metrics.

    Attributes:
        whole_df (pd.DataFrame): Complete processed dataset with all survey points
        clearance_data (pd.DataFrame): Filtered clearance results with boundary distances
        used_conc (List[Union[str, float]]): List of used concentration values

    Notes:
        - Expects input DataFrames to have specific column structure
        - 'shp_pt' column must contain shapely Point objects
        - Plat DataFrames must include geometry and centroid columns
    """

    def __init__(
            self,
            df_used: pd.DataFrame,
            df_plat: pd.DataFrame,
            db_local: sqlite3.Connection,
            bypass_db: bool = False
    ) -> None:
        """Initialize the ClearanceProcess with survey and plat data.

        Args:
            df_used: DataFrame containing survey points and associated data
                Must include 'shp_pt' column with shapely Point objects
            df_plat: DataFrame containing plat boundary information
                Must include 'geometry' column with shapely Polygon objects
            bypass_db: If True, skips database lookup and uses df_plat directly
                Useful for relative clearance calculations with transformed plats

        Notes:
            - Automatically calculates concentrations upon initialization
            - Creates empty whole_df for later processing
            - Triggers main_clearance processing during initialization
            - When bypass_db=True, uses find_conc_part to determine concentration zones
            - When bypass_db=False, uses fnd_conc with database lookup

        Raises:
            ValueError: If required columns are missing from input DataFrames
            TypeError: If geometry objects are not properly formatted
        """
        # Initialize list of used concentration values
        self.used_conc = []

        # Determine point concentrations based on bypass_db flag
        if bypass_db:
            # For second process - use df_plat directly as test_plat
            df_used = find_conc_part(df_plat, df_used)
        else:
            # For first process - normal database lookup
            df_used = self.fnd_conc(df_plat, df_used, db_local)

        # Initialize empty DataFrame for complete dataset
        self.whole_df = pd.DataFrame()

        # Process clearance data and store results
        self.clearance_data = self.main_clearance(df_plat, df_used)

    def main_clearance(self, df_plat: pd.DataFrame, df_used: pd.DataFrame) -> pd.DataFrame:
        """Processes clearance calculations for well trajectories against plat boundaries.

        Calculates distances from well trajectory points to the boundaries of their
        containing plats in all cardinal directions (FNL, FSL, FEL, FWL).

        Args:
            df_plat: DataFrame containing plat boundary information
                Must include 'label' and 'geometry' columns
            df_used: DataFrame containing survey points with assigned concentrations
                Must include 'point_index', 'easting', 'northing', and 'label' columns

        Returns:
            pd.DataFrame: Original survey data merged with calculated boundary distances
                Contains columns:
                - All original survey columns
                - point_index: Index of trajectory point
                - FNL: Distance to north line (feet)
                - FSL: Distance to south line (feet)
                - FEL: Distance to east line (feet)
                - FWL: Distance to west line (feet)

        Notes:
            - Processes each concentration (label) group separately
            - Segments plat boundaries into directional components
            - Calculates minimum distances to each boundary
            - Merges directional results into comprehensive dataset
            - Handles missing plat geometries with error reporting
            - Distance values are returned in feet

        Raises:
            IndexError: When plat geometry is missing for a concentration
        """
        # Process each unique concentration and calculate clearances
        self.whole_df = self._loop_through_list(df_plat, df_used)

        # Sort results by first column (typically point_index)
        self.whole_df = self.whole_df.sort_values(by=self.whole_df.columns[0])

        # Rename direction columns to standard notation
        self.whole_df = self.whole_df.rename(
            columns={
                'distance_East': 'FEL',
                'distance_West': 'FWL',
                'distance_North': 'FNL',
                'distance_South': 'FSL'
            }
        )

        # Extract relevant columns and merge with original data
        edited_df = self.whole_df[['point_index', 'FNL', 'FSL', 'FEL', "FWL"]]
        result = pd.merge(df_used, edited_df, on='point_index')

        # Store unique concentration values used in processing
        self.used_conc = result['label'].unique().tolist()

        return result

    def load_relative_clearance(self, df_plat: pd.DataFrame, df_used: pd.DataFrame) -> None:
        """Calculates relative clearance measurements for alternative plat configurations.

        Similar to main_clearance but calculates distances relative to an alternative
        plat configuration, useful for comparing clearances between different plat
        boundaries or well placements.

        Args:
            df_plat: DataFrame containing alternative plat boundary information
            df_used: DataFrame containing survey points with assigned concentrations

        Notes:
            - Results are stored with 'rel_' prefix (rel_fel, rel_fwl, rel_fnl, rel_fsl)
            - Uses same processing logic as main_clearance
            - Designed for comparison scenarios and what-if analysis
            - Does not modify clearance_data, creates a separate result set
        """
        rel_df = self._loop_through_list(df_plat, df_used)
        rel_df = rel_df.sort_values(by=rel_df.columns[0])
        rel_df = rel_df.rename(
            columns={
                'distance_East': 'rel_fel',
                'distance_West': 'rel_fwl',
                'distance_North': 'rel_fnl',
                'distance_South': 'rel_fsl'
            }
        )
        # Note: This method needs implementation to store or return the results

    def find_single_point(self, pt: List[float]) -> Optional[pd.DataFrame]:
        """Calculates clearance metrics for a single point against plat boundaries.

        Determines which plat contains the given point and calculates clearance
        distances to all sides of that plat. Useful for isolated point analysis
        without processing an entire trajectory.

        Args:
            pt: Point coordinates as [x, y]

        Returns:
            DataFrame with clearance measurements if point is contained in a plat,
            None otherwise

        Notes:
            - Checks all plats in self.plats to find containing plat
            - Returns None if point is not contained in any plat
            - Uses same directional processing as trajectory points
            - Result includes FNL, FSL, FEL, FWL distance measurements
        """
        def find_if_contained() -> Union[str, bool]:
            """Finds which plat contains the point, if any."""
            for idx, row in self.plats.iterrows():
                if row['geometry'].contains(Point(pt)):
                    return row['Conc']
            return False

        # Check if point is contained in any plat
        output = find_if_contained()
        if not output:
            return None

        # Filter to the containing plat
        used_plat = self.plats[self.plats['Conc'] == output]

        # Extract plat geometries
        conc_geometries: Dict[str, List[Tuple[float, float]]] = {
            conc: list(geom.exterior.coords)
            for conc, geom in used_plat.set_index('label')['geometry'].items()
        }

        # Pre-compute directional boundary segments
        boundary_segments: Dict[str, Tuple[List[List[float]], ...]] = {
            conc: _id_sides(geom_coords)
            for conc, geom_coords in conc_geometries.items()
        }

        # Get the concentration value
        conc = [i for i, v in boundary_segments.items()]

        # Format single point for processing
        well_trajectory = np.array([[pt[0], pt[1], 1]])

        # Get boundary segments for current concentration
        segments = boundary_segments.get(conc[0])
        if segments is None:
            print(f'No geometry found for concentration: {conc}')
            return None

        # Unpack directional segments
        right_lst_segments, left_lst_segments, up_lst_segments, down_lst_segments = segments

        # Calculate clearances for each direction
        direction_results: Dict[str, pd.DataFrame] = {
            'West': _results_finder(left_lst_segments, 'West', well_trajectory),
            'East': _results_finder(right_lst_segments, 'East', well_trajectory),
            'South': _results_finder(down_lst_segments, 'South', well_trajectory),
            'North': _results_finder(up_lst_segments, 'North', well_trajectory)
        }

        # Set index for efficient joining
        for df in direction_results.values():
            df.set_index('point_index', inplace=True)

        # Combine directional results
        combined_df: pd.DataFrame = pd.concat(direction_results.values(), axis=1)

        # Rename distance columns to standard notation
        combined_df.rename(columns={
            'distance_East': 'FEL',
            'distance_West': 'FWL',
            'distance_North': 'FNL',
            'distance_South': 'FSL'
        }, inplace=True)

        # Reset index for standard format
        combined_df.reset_index(inplace=True)
        return combined_df

    def _loop_through_list(self, df_plat: pd.DataFrame, df_used: pd.DataFrame) -> pd.DataFrame:
        """Processes clearance calculations for all trajectory points grouped by concentration.

        Core processing function that handles clearance calculations for all trajectory
        points against their containing plat boundaries. Segments processing by
        concentration group for efficiency.

        Args:
            df_plat: DataFrame containing plat boundary information
            df_used: DataFrame containing survey points with assigned concentrations

        Returns:
            DataFrame with complete clearance results for all trajectory points

        Notes:
            - Groups trajectory points by 'label' (concentration zone)
            - Pre-computes boundary segments for all plats
            - Processes each concentration group independently
            - Calculates clearances for all four cardinal directions
            - Combines results into comprehensive dataset
            - Handles potential missing geometries with error reporting
        """
        # Group trajectory points by concentration zone
        grouped: pd.core.groupby.DataFrameGroupBy = df_used.groupby('label')

        # Pre-compute geometry coordinates dictionary
        conc_geometries: Dict[str, List[Tuple[float, float]]] = {
            conc: list(geom.exterior.coords)
            for conc, geom in df_plat.set_index('label')['geometry'].items()
        }

        # Pre-compute directional boundary segments
        boundary_segments = {
            conc: _id_sides(geom_coords)
            for conc, geom_coords in conc_geometries.items()
        }

        # Initialize results list
        concat_lst: List[pd.DataFrame] = []

        # Process each concentration group
        for conc, group in grouped:
            # Extract trajectory points
            well_trajectory: NDArray = group[['easting', 'northing', 'point_index']].values

            # Get boundary segments for current concentration
            segments = boundary_segments.get(conc)
            if segments is None:
                print(f'No geometry found for concentration: {conc}')
                continue

            # Unpack directional segments
            right_lst_segments, left_lst_segments, up_lst_segments, down_lst_segments = segments

            # Calculate clearances for each direction
            direction_results: Dict[str, pd.DataFrame] = {
                'West': _results_finder(left_lst_segments, 'West', well_trajectory),
                'East': _results_finder(right_lst_segments, 'East', well_trajectory),
                'South': _results_finder(down_lst_segments, 'South', well_trajectory),
                'North': _results_finder(up_lst_segments, 'North', well_trajectory)
            }

            # Set index for efficient joining
            for df in direction_results.values():
                df.set_index('point_index', inplace=True)

            # Combine directional results
            combined_df: pd.DataFrame = pd.concat(direction_results.values(), axis=1)

            # Reset index for merging
            combined_df.reset_index(inplace=True)

            # Merge with original trajectory data
            merged_data: pd.DataFrame = group.merge(
                combined_df,
                on='point_index',
                how='left'
            )

            concat_lst.append(merged_data)

        # Combine all results
        final_df: pd.DataFrame = pd.concat(
            concat_lst,
            ignore_index=True,
            sort=False
        )

        return final_df

    def geo_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transforms tabular plat boundary data into shapely geometries.

        Converts coordinate points into shapely Point objects and groups them into
        Polygon geometries by concentration. Adds centroid calculation and formats
        concentration labels for consistent processing.

        Args:
            df: DataFrame containing plat boundary coordinates
                Must include 'Conc', 'Easting', 'Northing' columns

        Returns:
            DataFrame with processed geometries, containing:
            - Conc: Concentration identifier
            - geometry: Shapely Polygon object for boundary
            - centroid: Shapely Point object for plat centroid
            - label: Formatted concentration label

        Notes:
            - Converts numerical concentration codes to formatted string labels
            - Groups points by concentration to form complete polygons
            - Calculates centroid for each polygon
            - Essential preprocessing step for spatial operations
        """
        def transform_string(s: str) -> str:
            """Formats concentration string into standard notation.

            Example: '123456E' -> '12 34E 56E E'
            """
            part1 = str(int(s[:2]))
            part2 = str(int(s[2:4])) + s[4]
            part3 = str(int(s[5:7])) + s[7]
            part4 = s[-1]

            return f"{part1} {part2} {part3} {part4}"

        # Create Point geometry for each coordinate pair
        df['geometry'] = df.apply(lambda row: Point(row['Easting'], row['Northing']), axis=1)
        used_fields = df[['Conc', 'Easting', 'Northing', 'geometry']]

        # Group by concentration and create polygons
        polygons = used_fields.groupby('Conc').apply(
            lambda x: Polygon(zip(x['Easting'], x['Northing']))
        ).reset_index()

        # Merge polygon geometries with original data
        merged_data = used_fields.merge(polygons, on='Conc')
        merged_data = merged_data.drop('geometry', axis=1).rename(columns={0: 'geometry'})

        # Create final DataFrame with polygons and metadata
        df_new = merged_data.groupby('Conc').apply(
            lambda x: Polygon(zip(x['Easting'], x['Northing']))
        ).reset_index()

        # Format final output with standardized columns
        df_new.columns = ['Conc', 'geometry']
        df_new['centroid'] = df_new.apply(lambda x: x['geometry'].centroid, axis=1)
        df_new['label'] = df_new.apply(lambda x: transform_string(x['Conc']), axis=1)

        return df_new

    def fnd_conc(self, plat_df: pd.DataFrame, point_df: pd.DataFrame, conn_db) -> pd.DataFrame:
        """Finds concentration zones for survey points using database lookup.

        Queries a local SQLite database to determine which concentration zone (plat)
        contains each survey point. Uses spatial filtering to optimize database queries.

        Args:
            plat_df: DataFrame containing plat information (not used directly)
            point_df: DataFrame containing survey points with 'shp_pt' column

        Returns:
            DataFrame with survey points assigned to concentration zones

        Notes:
            - Connects to a local SQLite database at a fixed path
            - Uses bounding box filtering for efficient spatial queries
            - Transforms raw database results into shapely geometries
            - Performs spatial join to assign concentration zones to points
            - Essential preprocessing step for clearance calculations
        """
        # Connect to local database
        # path_used_db = r'C:\Work\Databases'
        # apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
        # conn_db = sqlite3.connect(apd_data_dir)

        def get_points_bbox(points_series: pd.Series) -> Tuple[float, float, float, float]:
            """Calculate bounding box from a series of Shapely points.

            Args:
                points_series: pandas Series containing Shapely Point objects

            Returns:
                tuple: (minx, miny, maxx, maxy)
            """
            # Create a list of coordinates
            coords = [(pt.x, pt.y) for pt in points_series]
            # Unzip coordinates into separate x and y lists
            x_coords, y_coords = zip(*coords)

            # Calculate bounds
            return min(x_coords), min(y_coords), max(x_coords), max(y_coords)

        def get_coordinate_query(bbox: Tuple[float, float, float, float], buffer_distance: float = 1000) -> str:
            """Generate SQL query using coordinate columns with buffer.

            Args:
                bbox: tuple of (minx, miny, maxx, maxy)
                buffer_distance: amount to expand search area

            Returns:
                SQL query string filtering by coordinate bounds
            """
            return f"""
            SELECT *
            FROM BaseData
            WHERE 
                Easting >= {bbox[0] - buffer_distance}
                AND Easting <= {bbox[2] + buffer_distance}
                AND Northing >= {bbox[1] - buffer_distance}
                AND Northing <= {bbox[3] + buffer_distance}
            """

        # Calculate bounding box of all points
        bbox = get_points_bbox(point_df['shp_pt'])

        # Query database for plats within bounding box
        spatial_query = get_coordinate_query(bbox)
        filtered_data = pd.read_sql(spatial_query, conn_db)

        # Extract unique concentration values
        conc_vals = filtered_data['Conc'].unique()
        concs = [str(i) for i in conc_vals]
        concs = ', '.join([f"'{str(elem)}'" for elem in concs])

        # Query complete plat data for matching concentrations
        query = f"""select * from BaseData where Conc IN ({concs})"""
        filtered_data = pd.read_sql(query, conn_db)

        # Transform database results into shapely geometries
        test_plat = self.geo_transform(filtered_data)

        # Assign concentration zones to points
        return find_conc_part(test_plat, point_df)

