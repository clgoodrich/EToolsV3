import pandas as pd
import numpy as np
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import nearest_points
import copy
import math
def mainTriangulator(conn, tsr_data, data, df, conc, survey_data, well_parameter_data, shl):
    print('triangulator)')
    print(tsr_data)
    print(data)
    print(df)
    print(conc)
    print(survey_data)
    print(well_parameter_data)
    print(shl)
    survey_data = alterSurveyForLargeSpacingBetweenPts(survey_data)
    counter = 0
    initial_data = df[df['new_code'] == conc].to_numpy().tolist()
    initial_data = initial_data[:16]
    plat_north_ref = initial_data[0][-3]
    plat_north_refs_lst = [plat_north_ref]
    foo = [survey_data[0] + [0] * 11]
    survey_data = survey_data[1:]
    known_conc_data = [conc]
    new_conc = conc
    dirLst = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    lst = [[0, 0, 0, 0, 0, 0, 0, 0],
           [36, 31, 6, 7, 12, 11, 2, 35],
           [35, 36, 1, 12, 11, 10, 3, 34],
           [34, 35, 2, 11, 10, 9, 4, 33],
           [33, 34, 3, 10, 9, 8, 5, 32],
           [32, 33, 4, 9, 8, 7, 6, 31],
           [31, 32, 5, 8, 7, 12, 1, 36],
           [6, 5, 8, 17, 18, 13, 12, 1],
           [5, 4, 9, 16, 17, 18, 7, 6],
           [4, 3, 10, 15, 16, 17, 8, 5],
           [3, 2, 11, 14, 15, 16, 9, 4],
           [2, 1, 12, 13, 14, 15, 10, 3],
           [1, 6, 7, 18, 13, 14, 11, 2],
           [12, 7, 18, 19, 24, 23, 14, 11],
           [11, 12, 13, 24, 23, 22, 15, 10],
           [10, 11, 14, 23, 22, 21, 16, 9],
           [9, 10, 15, 22, 21, 20, 17, 8],
           [8, 9, 16, 21, 20, 19, 18, 7],
           [7, 8, 17, 20, 19, 24, 13, 12],
           [18, 17, 20, 29, 30, 25, 24, 13],
           [17, 16, 21, 28, 29, 30, 19, 18],
           [16, 15, 22, 27, 28, 29, 20, 17],
           [15, 14, 23, 26, 27, 28, 21, 16],
           [14, 13, 24, 25, 26, 27, 22, 15],
           [13, 18, 19, 30, 25, 26, 23, 14],
           [24, 19, 30, 31, 36, 35, 26, 23],
           [23, 24, 25, 36, 35, 34, 27, 22],
           [22, 23, 26, 35, 34, 33, 28, 21],
           [21, 22, 27, 34, 33, 32, 29, 20],
           [20, 21, 28, 33, 32, 31, 30, 19],
           [19, 20, 29, 32, 31, 36, 25, 24],
           [30, 29, 32, 5, 6, 1, 36, 25],
           [29, 28, 33, 4, 5, 6, 31, 30],
           [28, 27, 34, 3, 4, 5, 32, 29],
           [27, 26, 35, 2, 3, 4, 33, 28],
           [26, 25, 36, 1, 2, 3, 34, 27],
           [25, 30, 31, 6, 1, 2, 35, 26]]
    section = int(float(tsr_data[0][6]))
    section_degrees_data = [data]
    md_lst = [i[0] for i in survey_data]
    inc_lst = [i[1] for i in survey_data]
    azi_lst = [i[2] for i in survey_data]
    north_reference, magnetic_declination, convergence_angle, target_azimuth = well_parameter_data[0], well_parameter_data[1], float(well_parameter_data[2]), float(well_parameter_data[3])
    min_curv_data = wmc.mainCalculation(md_lst, inc_lst, azi_lst, convergence_angle, north_reference, plat_north_ref, magnetic_declination, target_azimuth)


    prev_section_data = tsr_data[0][6:]
    while True:

        corners, sides_generated = ma.cornerGeneratorProcess(data)
        sides_generated = [[j[:-1] for j in i] for i in sides_generated]
        segment_lst = [[[i[j], i[j + 1]] for j in range(len(i) - 1)] for i in sides_generated]
        # findIntersectionBetweenWellAndSection(segment_lst, offset_pts_lst, shl)

        intersection, direction, well_index_end, foo, well_path_tester = findWellPathBoundaryIntersection(segment_lst, survey_data, well_parameter_data, plat_north_ref, foo, shl)
        if not well_path_tester or direction == 'Null':
            return min_curv_data, known_conc_data, section_degrees_data, plat_north_refs_lst

        index = dirLst.index(direction)
        new_section = lst[section][index]
        township, townshipDir, rng, rngDir, prev_section_data = modifySection(section, new_section, prev_section_data)
        conc_info = [new_section, township, townshipDir, rng, rngDir, tsr_data[0][-1]]
        new_conc = ma.reTranslateData(conc_info)
        # ma.grapher4(well_path_tester, section_degrees_data[-1], new_conc)
        if new_conc in known_conc_data:

            known_index = known_conc_data.index(new_conc)
            data = section_degrees_data[known_index]
            counter += 1
        else:
            old_well_path_tester = well_path_tester[:well_index_end + 1]
            proxBoo = getBooProx(data, old_well_path_tester, direction)
            known_conc_data.append(new_conc)
            data_new = df[df['new_code'] == new_conc].to_numpy().tolist()

            if len(data_new) == 0:
                data_new = GUIDataAdd.addDataIfAGRCNotFound(conn, new_conc, conc_info)
            data_new = sorted(data_new, key=lambda x: x[-1], reverse=True)
            plat_north_ref = data_new[0][-3]
            plat_north_refs_lst.append(plat_north_ref)
            data_new_deg, data_new_dec = ma.dataConverterPlatToUtm(data_new)
            # data_new_dec = ma.convertToDecimal(copy.deepcopy(data_new))
            # data_new_deg = ma.pointsConverter(data_new_dec)
            rewritten_coords = coordsAdjuster(data_new_deg, data, direction, proxBoo)
            data = rewritten_coords
            section_degrees_data.append(data)
            counter += 1
        section = new_section

    return min_curv_data, known_conc_data, section_degrees_data, plat_north_refs_lst



def find_point_from_footages(polygon_coords, ns_distance, ns_type, ew_distance, ew_type):
    """
    Find point within polygon using any combination of boundary distance references.

    Args:
        polygon_coords: List of [x, y, side] where side is 'north', 'south', 'east', or 'west'
        ns_distance: North-South distance (feet)
        ns_type: 'FNL' (From North Line) or 'FSL' (From South Line)
        ew_distance: East-West distance (feet)
        ew_type: 'FEL' (From East Line) or 'FWL' (From West Line)

    Returns:
        [x, y] coordinates of the intersection point
    """
    # Separate coordinates by side
    sides = {}
    for coord in polygon_coords:
        x, y, side = coord
        if side not in sides:
            sides[side] = []
        sides[side].append([x, y])
    sides['west'].append(sides['north'][0])
    sides['north'].append(sides['east'][0])
    sides['east'].append(sides['south'][0])
    sides['south'].append(sides['west'][0])
    # Get the appropriate boundary segments based on ns_type
    if ns_type == 'FNL':
        ns_coords = sides.get('north', [])
        ns_offset_side = 'right'  # South is right when going east
    else:  # FSL
        ns_coords = sides.get('south', [])
        ns_offset_side = 'left'  # North is left when going west
    # Get the appropriate boundary segments based on ew_type
    if ew_type == 'FEL':
        ew_coords = sides.get('east', [])
        ew_offset_side = 'left'  # West is left when going north
    else:  # FWL
        ew_coords = sides.get('west', [])
        ew_offset_side = 'right'  # East is right when going south

    # Create line segments for each boundary
    ns_segments = []
    if len(ns_coords) > 0:
        for i in range(len(ns_coords) - 1):
            ns_segments.append((tuple(ns_coords[i]), tuple(ns_coords[i + 1])))

    ew_segments = []
    if len(ew_coords) > 0:
        for i in range(len(ew_coords) - 1):
            ew_segments.append((tuple(ew_coords[i]), tuple(ew_coords[i + 1])))
    # Create parallel segments
    ns_parallel_segments = []
    for segment in ns_segments:
        line = LineString(segment)
        try:
            parallel = line.parallel_offset(ns_distance, 'right')
            #
            # if ns_type == 'FNL':
            #     parallel = line.parallel_offset(ns_distance, ns_offset_side)
            # elif ns_type == 'FSL':
            #     parallel = line.parallel_offset(-ns_distance, ns_offset_side)
            if hasattr(parallel, 'coords'):
                ns_parallel_segments.append(tuple(parallel.coords))
        except:
            continue
    ew_parallel_segments = []
    for segment in ew_segments:
        line = LineString(segment)
        # try:
        parallel = line.parallel_offset(ew_distance, 'right')
        # new_data = line_str_seg.parallel_offset(distance, 'right', resolution=1, join_style=2, mitre_limit=5)
        if hasattr(parallel, 'coords'):
            ew_parallel_segments.append(list(parallel.coords))
        # except as e:
        #     continue
    # Find intersection
    for ns_seg in ns_parallel_segments:
        line1 = LineString(ns_seg)
        for ew_seg in ew_parallel_segments:
            line2 = LineString(ew_seg)
            intersection = line1.intersection(line2)

            if hasattr(intersection, 'x') and hasattr(intersection, 'y'):
                return [intersection.x, intersection.y]

    return None
def get_offset_added_delta(dx, dy, starter_pt):
    return starter_pt[0] + float(dx) * 0.3048, starter_pt[1] + float(dy) * 0.3048
def get_starter_pt(row, current_plat):
    if row['FNL'] < row['FSL']:
        fnsl_val = row['FNL']
        fnsl = 'FNL'
    else:
        fnsl_val = row['FSL']
        fnsl = 'FSL'
    if row['FEL'] < row['FWL']:
        fewl_val = row['FEL']
        fewl = 'FEL'
    else:
        fewl_val = row['FWL']
        fewl = 'FWL'
    out = find_point_from_footages(current_plat, float(fnsl_val), fnsl, float(fewl_val), fewl)
    return out

def triangulatorWithKnownData(current_plat_coords, current_plat_conc, original_all_plats_df, well_path):
    """
    Main function to trace well path through sections with re-entry support.

    Args:
        current_plat_coords: DataFrame with current plat coordinates
        current_plat_conc: String identifier for starting plat  
        original_all_plats_df: DataFrame with all plat boundaries
        well_path: DataFrame with well trajectory data

    Returns:
        section_visits: List of section visits with details
        section_degrees_data: List of coordinate data for visited sections
        known_conc_data: List of visited concession identifiers
    """
    # Extract well points from well_path DataFrame
    result_coords = current_plat_coords[['x', 'y', 'side']].values.tolist()
    starter_pt = get_starter_pt(well_path.iloc[0], result_coords)

    well_path[['e_offset_delta', 'n_offset_delta']] = (well_path.apply(lambda row: get_offset_added_delta(row['e_offset'], row['n_offset'], starter_pt), axis=1, result_type='expand'))

    well_points = []
    for _, row in well_path.iterrows():
        if 'e_offset_delta' in row and 'n_offset_delta' in row:
            well_points.append([row['e_offset_delta'], row['n_offset_delta']])
        # if 'position_x' in row and 'position_y' in row:
        #     well_points.append([row['position_x'], row['position_y']])


    # Initialize tracking variables
    known_conc_data = []
    section_degrees_data = []
    section_visits = []

    # Direction lists
    dirLst = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

    # Section adjacency matrix
    lst = [[0, 0, 0, 0, 0, 0, 0, 0],
           [36, 31, 6, 7, 12, 11, 2, 35],
           [35, 36, 1, 12, 11, 10, 3, 34],
           [34, 35, 2, 11, 10, 9, 4, 33],
           [33, 34, 3, 10, 9, 8, 5, 32],
           [32, 33, 4, 9, 8, 7, 6, 31],
           [31, 32, 5, 8, 7, 12, 1, 36],
           [6, 5, 8, 17, 18, 13, 12, 1],
           [5, 4, 9, 16, 17, 18, 7, 6],
           [4, 3, 10, 15, 16, 17, 8, 5],
           [3, 2, 11, 14, 15, 16, 9, 4],
           [2, 1, 12, 13, 14, 15, 10, 3],
           [1, 6, 7, 18, 13, 14, 11, 2],
           [12, 7, 18, 19, 24, 23, 14, 11],
           [11, 12, 13, 24, 23, 22, 15, 10],
           [10, 11, 14, 23, 22, 21, 16, 9],
           [9, 10, 15, 22, 21, 20, 17, 8],
           [8, 9, 16, 21, 20, 19, 18, 7],
           [7, 8, 17, 20, 19, 24, 13, 12],
           [18, 17, 20, 29, 30, 25, 24, 13],
           [17, 16, 21, 28, 29, 30, 19, 18],
           [16, 15, 22, 27, 28, 29, 20, 17],
           [15, 14, 23, 26, 27, 28, 21, 16],
           [14, 13, 24, 25, 26, 27, 22, 15],
           [13, 18, 19, 30, 25, 26, 23, 14],
           [24, 19, 30, 31, 36, 35, 26, 23],
           [23, 24, 25, 36, 35, 34, 27, 22],
           [22, 23, 26, 35, 34, 33, 28, 21],
           [21, 22, 27, 34, 33, 32, 29, 20],
           [20, 21, 28, 33, 32, 31, 30, 19],
           [19, 20, 29, 32, 31, 36, 25, 24],
           [30, 29, 32, 5, 6, 1, 36, 25],
           [29, 28, 33, 4, 5, 6, 31, 30],
           [28, 27, 34, 3, 4, 5, 32, 29],
           [27, 26, 35, 2, 3, 4, 33, 28],
           [26, 25, 36, 1, 2, 3, 34, 27],
           [25, 30, 31, 6, 1, 2, 35, 26]]

    # Get initial plat data
    current_conc = current_plat_conc
    data = extractPlatCoordinates(current_plat_coords, current_conc)

    # Extract section info from concession
    section = extractSectionFromConc(current_conc)
    prev_section_data = extractTSRFromConc(current_conc)

    # Track visits to handle re-entry
    visit_tracker = {}  # {conc: [visit_indices]}
    well_index = 0

    while well_index < len(well_points) - 1:
        # Check if this is a re-entry
        if current_conc in visit_tracker:
            visit_num = len(visit_tracker[current_conc]) + 1
        else:
            visit_tracker[current_conc] = []
            visit_num = 1
            known_conc_data.append(current_conc)
            section_degrees_data.append(data)

        # Find where well exits current section
        corners, sides_generated = cornerGeneratorProcess(data)
        sides_generated = [[j[:-1] for j in i] for i in sides_generated]
        segment_lst = [[[i[j], i[j + 1]] for j in range(len(i) - 1)] for i in sides_generated]

        # Find intersection and exit direction
        intersection, direction, well_index_end = findWellPathBoundaryIntersection(
            segment_lst, well_points, well_index
        )

        if direction == 'Null' or well_index_end >= len(well_points) - 1:
            # Well ends in this section
            visit_tracker[current_conc].append((well_index, len(well_points) - 1))
            section_visits.append({
                'conc': current_conc,
                'visit_number': visit_num,
                'entry_index': well_index,
                'exit_index': len(well_points) - 1,
                'exit_direction': None
            })
            break

        # Record this visit
        visit_tracker[current_conc].append((well_index, well_index_end))
        section_visits.append({
            'conc': current_conc,
            'visit_number': visit_num,
            'entry_index': well_index,
            'exit_index': well_index_end,
            'exit_direction': direction
        })

        # Determine next section
        index = dirLst.index(direction)
        new_section = lst[section][index]

        # Update TSR data
        township, townshipDir, rng, rngDir, prev_section_data = modifySection(
            section, new_section, prev_section_data
        )

        # Create new concession identifier
        new_conc = reTranslateData([new_section, township, townshipDir, rng, rngDir, 'U'])

        # Check if we need to get new plat data
        if new_conc not in known_conc_data:
            # Get plat data from original_all_plats_df
            data_new = original_all_plats_df[original_all_plats_df['conc'] == new_conc]
            if data_new.empty:
                # Can't find next section, end here
                break

            data_new_coords = extractPlatCoordinates(data_new, new_conc)

            # Adjust coordinates for smooth transition
            proxBoo = getBooProx(data, well_points[well_index:well_index_end + 1], direction)
            rewritten_coords = coordsAdjuster(data_new_coords, data, direction, proxBoo)
            data = rewritten_coords
        else:
            # Re-entering a previously visited section
            data_index = known_conc_data.index(new_conc)
            data = section_degrees_data[data_index]

        # Update for next iteration
        current_conc = new_conc
        section = new_section
        well_index = well_index_end

    return section_visits, section_degrees_data, known_conc_data


def extractPlatCoordinates(plat_df, conc):
    """Extract coordinates for a specific concession from plat DataFrame."""
    if isinstance(plat_df, pd.DataFrame):
        plat_data = plat_df[plat_df['conc'] == conc].sort_values('point_i')
    else:
        plat_data = plat_df

    coords = []
    for _, row in plat_data.iterrows():
        coords.append([row['x'], row['y']])

    # Remove duplicates
    seen = set()
    unique_coords = []
    for coord in coords:
        coord_tuple = tuple(coord)
        if coord_tuple not in seen:
            seen.add(coord_tuple)
            unique_coords.append(coord)

    return unique_coords


def extractSectionFromConc(conc):
    """Extract section number from concession string."""
    # Format: "0107S19ES" -> section is 01 or 07
    try:
        parts = conc.split('S')
        section_str = parts[0][-2:]
        return int(section_str)
    except:
        return 1


def extractTSRFromConc(conc):
    """Extract township, range, section data from concession."""
    # Simplified extraction - adapt to your format
    # Format assumed: "SSTTDRRDU"
    try:
        parts = conc.split('S')
        section = int(parts[0][-2:])

        # Extract township and range (simplified)
        township = 4  # Default
        townshipDir = 'S'
        rng = 19  # From example
        rngDir = 'E'

        return [section, township, townshipDir, rng, rngDir, 'U']
    except:
        return [1, 1, 'S', 1, 'E', 'U']


def cornerGeneratorProcess(coords):
    """Generate corners and sides from plat coordinates."""
    # Ensure closed polygon
    if coords[0] != coords[-1]:
        coords = coords + [coords[0]]

    # Simple corner detection - every 4th point
    num_points = len(coords) - 1
    points_per_side = num_points // 4

    corners = []
    sides = []

    for i in range(4):
        start_idx = i * points_per_side
        end_idx = (i + 1) * points_per_side if i < 3 else num_points

        side_points = coords[start_idx:end_idx + 1]
        sides.append(side_points)
        corners.append(coords[start_idx])

    return corners, sides


def findWellPathBoundaryIntersection(segment_lst, well_points, start_index):
    """Find where well path intersects section boundary."""
    # Uncomment for debugging:
    # debug_segment_structure(segment_lst, well_points)

    direction = ['W', 'N', 'E', 'S']

    # Debug: Check data structures
    if not segment_lst or not well_points:
        print("Warning: Empty segment_lst or well_points")
        return [0, 0], 'Null', len(well_points)

    # Create polygon from segments for containment checks
    all_points = []
    for side_segments in segment_lst:
        for segment in side_segments:
            if isinstance(segment, list) and len(segment) >= 2:
                # Add first point of each segment
                if isinstance(segment[0], list) and len(segment[0]) >= 2:
                    all_points.append(segment[0])

    # Add last point of last segment to close polygon
    if segment_lst and segment_lst[-1] and segment_lst[-1][-1]:
        last_segment = segment_lst[-1][-1]
        if isinstance(last_segment, list) and len(last_segment) >= 2:
            if isinstance(last_segment[1], list) and len(last_segment[1]) >= 2:
                all_points.append(last_segment[1])

    if len(all_points) < 3:
        print(f"Warning: Not enough points to create polygon: {len(all_points)}")
        return [0, 0], 'Null', len(well_points)

    try:
        polygon = Polygon(all_points)
    except Exception as e:
        print(f"Error creating polygon: {e}")
        return [0, 0], 'Null', len(well_points)

    # Check each well segment for intersection
    for i in range(start_index, len(well_points) - 1):
        if not (isinstance(well_points[i], list) and len(well_points[i]) >= 2):
            continue
        if not (isinstance(well_points[i + 1], list) and len(well_points[i + 1]) >= 2):
            continue

        try:
            well_segment = LineString([well_points[i], well_points[i + 1]])
            p1 = Point(well_points[i])
            p2 = Point(well_points[i + 1])

            # Check each side's segments
            for j, side_segments in enumerate(segment_lst):
                for segment in side_segments:
                    if not (isinstance(segment, list) and len(segment) == 2):
                        continue
                    if not (isinstance(segment[0], list) and len(segment[0]) >= 2):
                        continue
                    if not (isinstance(segment[1], list) and len(segment[1]) >= 2):
                        continue

                    try:
                        boundary_segment = LineString(segment)

                        if well_segment.intersects(boundary_segment):
                            intersection = well_segment.intersection(boundary_segment)

                            if isinstance(intersection, Point):
                                # Check if we're exiting (not entering)
                                if polygon.contains(p1) and not polygon.contains(p2):
                                    return [intersection.x, intersection.y], direction[j], i + 1
                    except Exception as e:
                        print(f"Error processing segment: {e}")
                        continue

        except Exception as e:
            print(f"Error processing well segment {i}: {e}")
            continue

    return [0, 0], 'Null', len(well_points)
# def findWellPathBoundaryIntersection(segment_lst, well_points, start_index):
#     print(segment_lst)
#     print(well_points)
#     print(start_index)
#     """Find where well path intersects section boundary."""
#     direction = ['W', 'N', 'E', 'S']
#     # print(segment_lst)
#     for i in range(start_index, len(well_points) - 1):
#         well_segment = LineString([well_points[i], well_points[i + 1]])
#
#         for j, side_segments in enumerate(segment_lst):
#             for segment in side_segments:
#                 boundary_segment = LineString(segment)
#
#                 if well_segment.intersects(boundary_segment):
#                     intersection = well_segment.intersection(boundary_segment)
#
#                     if isinstance(intersection, Point):
#                         # Check if we're exiting (not entering)
#                         p1 = Point(well_points[i])
#                         p2 = Point(well_points[i + 1])
#
#                         # Create polygon from all segments
#                         all_points = []
#                         for side in segment_lst:
#                             for seg in side:
#                                 all_points.extend(seg)
#
#                         polygon = Polygon(all_points)
#
#                         if polygon.contains(p1) and not polygon.contains(p2):
#                             return [intersection.x, intersection.y], direction[j], i + 1
#
#     return [0, 0], 'Null', len(well_points)


def getBooProx(coordinates, inside_pts, direction):
    """Determine proximity to boundaries."""
    polygon = Polygon(coordinates)
    bounds = polygon.bounds  # (minx, miny, maxx, maxy)

    last_pt = inside_pts[-1]

    if direction in ['N', 'S']:
        # Check E/W proximity
        east_dist = abs(bounds[2] - last_pt[0])
        west_dist = abs(bounds[0] - last_pt[0])
        return east_dist < west_dist
    else:  # E or W
        # Check N/S proximity
        north_dist = abs(bounds[3] - last_pt[1])
        south_dist = abs(bounds[1] - last_pt[1])
        return north_dist < south_dist


def coordsAdjuster(new_coords, last_coords, direction, direction_boo):
    """Adjust coordinates for section transitions."""
    # This maintains boundary alignment between sections
    # Simplified version - you may need more sophisticated alignment

    directions_dict = {"W": 0, "N": 1, "E": 2, "S": 3}
    dir_idx = directions_dict[direction]

    # Find matching boundary points
    # For now, return new_coords as-is
    # In production, align shared boundaries

    return new_coords


def modifySection(prev, new, section_data):
    """Handle section transitions and update TSR data."""
    township = section_data[1]
    townshipDir = section_data[2]
    rng = section_data[3]
    rngDir = section_data[4]

    # Handle township boundaries
    if prev in [1, 2, 3, 4, 5, 6] and new in [31, 32, 33, 34, 35, 36]:
        if townshipDir == 'S':
            if township == 1:
                township = 1
                townshipDir = "N"
            else:
                township = township - 1
        else:
            township = township + 1

    if prev in [31, 32, 33, 34, 35, 36] and new in [1, 2, 3, 4, 5, 6]:
        if township == 1:
            township = 1
            townshipDir = "S"
        else:
            township = township - 1

    # Handle range boundaries
    if prev in [1, 12, 13, 24, 25, 36] and new in [6, 7, 18, 19, 30, 31]:
        if rng == 1:
            rng = 1
            rngDir = 'E' if rngDir == 'W' else 'W'
        else:
            rng = rng - 1 if rngDir == 'E' else rng + 1

    if prev in [6, 7, 18, 19, 30, 31] and new in [1, 12, 13, 24, 25, 36]:
        if rng == 1:
            rng = 1
            rngDir = 'W' if rngDir == 'E' else 'E'
        else:
            rng = rng + 1 if rngDir == 'E' else rng - 1

    prev_section_data = [new, township, townshipDir, rng, rngDir, section_data[5]]
    return township, townshipDir, rng, rngDir, prev_section_data


def reTranslateData(conc_info):
    """Convert section/township/range info back to concession string."""
    section, township, townshipDir, rng, rngDir, unit = conc_info

    # Format: "SSTTDRRDU"
    section_str = f"{section:02d}"
    township_str = f"{township:02d}"
    rng_str = f"{rng:02d}"

    return f"{section_str}{township_str}{townshipDir}{rng_str}{rngDir}{unit}"