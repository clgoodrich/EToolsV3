import pandas as pd
import numpy as np
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import nearest_points
import copy
import math
from main_project_clearance import _corner_generator_process
import wellMinimumCurvatureCalculation as wmc
import utm
from geopy.distance import geodesic
from shapely.ops import linemerge
from itertools import chain
import matplotlib.pyplot as plt
import ModuleAgnostic as ma


def alterSurveyForLargeSpacingBetweenPts(lst):
    new_pts = []
    for i in range(len(lst) - 1):
        div = abs(lst[i][0] - lst[i + 1][0])
        if div > 5000 and lst[i][1] == lst[i + 1][1] and lst[i][2] == lst[i + 1][2]:
            counter = int(round(div / 5000, 0))
            divisor = div / (counter + 1)
            for h in range(counter):
                new_pt = [lst[i][0] + divisor * (h + 1), lst[i][1], lst[i][2]]
                new_pts.append(new_pt)
    lst = lst + new_pts
    lst = sorted(lst, key=lambda x: x[0])
    lst = [i for i in lst if i]
    return lst


def reTranslateData_2(i):
    conc_code_merged = i[:6]
    conc_code_merged[2] = translateNumberToDirection('township', str(conc_code_merged[2])).upper()
    conc_code_merged[4] = translateNumberToDirection('rng', str(conc_code_merged[4])).upper()
    conc_code_merged[5] = translateNumberToDirection('baseline', str(conc_code_merged[5])).upper()
    conc_code_merged[0], conc_code_merged[1], conc_code_merged[3] = str(int(float(conc_code_merged[0]))).zfill(2), str(
        int(float(conc_code_merged[1]))).zfill(2), str(int(float(conc_code_merged[3]))).zfill(2)
    conc_code = "".join([str(q) for q in conc_code_merged])
    return conc_code


def translateNumberToDirection(variable, val):
    translations = {
        'rng': {'2': 'W', '1': 'E'},
        'township': {'2': 'S', '1': 'N'},
        'baseline': {'2': 'U', '1': 'S'},
        'alignment': {'1': 'SE', '2': 'NE', '3': 'SW', '4': 'NW'}
    }
    return translations.get(variable, {}).get(val, val)


def get_offset_added_delta(x, y, dx, dy):
    # return (x + float(dx)) * 0.3048, (y + float(dy)) * 0.3048

    return x + float(dx), y + float(dy)

def transform_and_correct_for_north_ref(north_ref, azimuth, convergence_angle):
    if north_ref.lower() != 'g':
        return azimuth
    else:
        true_azimuth = azimuth + convergence_angle
        # Normalize to 0-360 degrees
        if true_azimuth >= 360:
            true_azimuth -= 360
        elif true_azimuth < 0:
            true_azimuth += 360
        return true_azimuth


def triangulator_with_known(conn, data_plat_coords, survey_data_df, well_parameter_data):
    north_reference, magnetic_declination, convergence_angle, target_azimuth = well_parameter_data[0], \
        well_parameter_data[1], float(well_parameter_data[2]), float(well_parameter_data[3])
    data = df[df['conc'] == new_conc].to_numpy().tolist()
    data, data_new_dec = dataConverterPlatToUtm(data)
    for index, sublist in enumerate(data):
        if index < 4:  # Indices 0-3
            sublist.append('west')
        elif index < 8:  # Indices 4-7
            sublist.append('north')
        elif index < 12:  # Indices 8-11
            sublist.append('east')
        else:  # Indices 12 and onwards
            sublist.append('south')
    result_coords = data
    shl = get_starter_pt(survey_data_df.iloc[0], result_coords)
    survey_data_df[['e_offset_delta', 'n_offset_delta']] = (survey_data_df.apply(
        lambda row: get_offset_added_delta(shl[0], shl[1], row['e_offset'], row['n_offset']), axis=1,
        result_type='expand'))


    survey_data = survey_data_df[['measured_depth', 'inclination', 'azimuth']].values.tolist()

    survey_data = alterSurveyForLargeSpacingBetweenPts(survey_data)
    counter = 0
    initial_data = df[df['conc'] == conc].to_numpy().tolist()
    initial_data = initial_data[:16]
    plat_north_ref = initial_data[0][-3]
    plat_north_refs_lst = [plat_north_ref]
    foo = [survey_data[0] + [0] * 11]
    survey_data = survey_data[1:]
    known_conc_data = [new_conc]
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
    section = int(float(tsr_data[0][0]))
    data = [i[:2] for i in data]
    section_degrees_data = [data]
    min_curv_data = survey_data_df

    prev_section_data = tsr_data[0][:6]

    while True:
        data = [i[:2] for i in data]
        corners, sides_generated = ma.cornerGeneratorProcess(data)
        sides_generated = [[j[:-1] for j in i] for i in sides_generated]
        segment_lst = [[[i[j], i[j + 1]] for j in range(len(i) - 1)] for i in sides_generated]
        intersection, direction, well_index_end, foo, well_path_tester = findWellPathBoundaryIntersection(segment_lst,
                                                                                                          survey_data,
                                                                                                          well_parameter_data,
                                                                                                          plat_north_ref,
                                                                                                          foo, shl)


        if not well_path_tester or direction == 'Null':
            return min_curv_data, known_conc_data, section_degrees_data, plat_north_refs_lst, shl

        index = dirLst.index(direction)
        new_section = lst[section][index]
        township, townshipDir, rng, rngDir, prev_section_data = modifySection(section, new_section, prev_section_data)
        conc_info = [new_section, township, townshipDir, rng, rngDir, tsr_data[0][5]]
        new_conc = reTranslateData_2(conc_info)
        if new_conc in known_conc_data:

            known_index = known_conc_data.index(new_conc)
            data = section_degrees_data[known_index]
            counter += 1
        else:
            old_well_path_tester = well_path_tester[:well_index_end + 1]
            proxBoo = getBooProx(data, old_well_path_tester, direction)
            known_conc_data.append(new_conc)
            data_new = df[df['conc'] == new_conc].to_numpy().tolist()
            if len(data_new) == 0:
                data_new = GUIDataAdd.addDataIfAGRCNotFound(conn, new_conc, conc_info)
            data_new = sorted(data_new, key=lambda x: x[-1], reverse=True)
            plat_north_ref = data_new[0][-4]
            plat_north_refs_lst.append(plat_north_ref)
            data_new_deg, data_new_dec = dataConverterPlatToUtm(data_new)
            rewritten_coords = coordsAdjuster(data_new_deg, data, direction, proxBoo)
            data = rewritten_coords
            section_degrees_data.append(data)
            counter += 1
        section = new_section

    return min_curv_data, known_conc_data, section_degrees_data, plat_north_refs_lst, shl


def create_relative_section_polygon(df):
    """
    Creates a Shapely Polygon from PLSS survey calls, with the
    starting point at the origin (0, 0).

    Args:
        df (pd.DataFrame): DataFrame with PLSS calls for a single section.

    Returns:
        shapely.geometry.Polygon: The closed polygon of the section,
                                  relative to its starting point.
    """
    # 1. Define the correct clockwise traversal order for the section boundary
    clockwise_order = [
        'west_down_2', 'west_down_1', 'west_up_1', 'west_up_2',
        'north_left_2', 'north_left_1', 'north_right_1', 'north_right_2',
        'east_up_2', 'east_up_1', 'east_down_1', 'east_down_2',
        'south_right_2', 'south_right_1', 'south_left_1', 'south_left_2'
    ]

    # 2. Sort the DataFrame according to the clockwise order
    df['sort_key'] = pd.Categorical(df['side'], categories=clockwise_order, ordered=True)
    df_sorted = df.sort_values('sort_key').reset_index()

    # 3. Initialize the traverse at the origin (0, 0)
    points = [(0.0, 0.0)]
    current_x, current_y = 0.0, 0.0

    # 4. Iterate through the sorted rows to calculate vertices
    for index, row in df_sorted.iterrows():
        # --- Robust Azimuth Calculation ---
        decimal_angle = row['degrees'] + row['minutes'] / 60.0 + row['seconds'] / 3600.0
        bearing_str = row['bearing_str']
        azimuth = 0.0

        if bearing_str == 'NE':
            azimuth = decimal_angle
        elif bearing_str == 'SE':
            azimuth = 180.0 - decimal_angle
        elif bearing_str == 'SW':
            azimuth = 180.0 + decimal_angle
        elif bearing_str == 'NW':
            azimuth = 360.0 - decimal_angle

        # --- Plane Coordinate Calculation (in feet) ---
        distance_ft = row['length']
        azimuth_rad = math.radians(azimuth)

        delta_x = distance_ft * math.sin(azimuth_rad)
        delta_y = distance_ft * math.cos(azimuth_rad)

        current_x += delta_x
        current_y += delta_y
        points.append((current_x, current_y))

    # --- Finalize the Polygon ---
    # The last calculated point should be very close to the origin (0, 0).
    # We remove it to avoid a duplicate point in the polygon definition.
    closure_error = math.dist(points[0], points[-1])
    print(f"Closure Error: {closure_error:.2f} feet")  # Good practice to check this!

    # Create the polygon from all points except the last one.
    # section_polygon = Polygon(points[:-1])
    points_out = [list(i) for i in points[:-1]]
    return points_out


def dataConverterPlatToUtm(data):
    output = convertToDecimal2(data)
    data_converted = calculate_next_utm_points(output)
    return data_converted, output


def convertToDecimal2(data):
    data_converted = []
    for item in data:
        if len(item) > 6:
            item = item[9:15]
            item[1] = float(item[1])
        side, deg, min, sec, dir_val = map(float, item[1:6])
        dec_val_base = deg + min / 60 + sec / 3600

        if 'west' in item[0].lower():
            decVal = 360 - dec_val_base if dir_val not in [4, 1] and int(dec_val_base) not in [180, 0, 360,
                                                                                               90] else dec_val_base
        elif 'east' in item[0].lower():
            decVal = 180 + dec_val_base if dir_val in [4, 1] else 180 - dec_val_base if int(dec_val_base) not in [180,
                                                                                                                  0,
                                                                                                                  360,
                                                                                                                  90] else 180
        elif 'north' in item[0].lower():
            decVal = (90 - dec_val_base) + 90 if dir_val in [4, 1] else 180 - dec_val_base if int(dec_val_base) not in [
                180, 0, 360, 90] else 90
        elif 'south' in item[0].lower():
            decVal = (90 - dec_val_base) + 270 if dir_val in [4, 1] else 360 - dec_val_base if int(
                dec_val_base) not in [180, 0, 360, 90] else 270

        data_converted.append([side, decVal])

    return data_converted


def calculate_next_utm_points(data):
    data = reorderDecimalData(data)
    data = oneToMany(data, 4)
    current_point = (500000, 5360194.4)
    utm_points = [(500000, 5360194.4)]
    utm_points_2 = []
    for i in data:
        for step in i:
            distance, bearing = step
            distance = distance * 0.3048
            lat, lon = utm.to_latlon(*current_point, zone_number=12, zone_letter='T')
            start_point = (lat, lon)
            destination = geodesic(kilometers=distance / 1000).destination(start_point, bearing)
            destination_utm = utm.from_latlon(destination.latitude, destination.longitude)[:2]
            utm_points.append(destination_utm[:2])  # Append only the UTM coordinates (eastings and northings)
            current_point = destination_utm[:2]  # Update the current UTM point for the next iteration
    for i in utm_points:
        pt1 = (i[0] - utm_points[0][0]) / 0.3048
        pt2 = (i[1] - utm_points[0][1]) / 0.3048
        utm_points_2.append([pt1, pt2])
    return utm_points_2

def reorderDecimalData(data):
    return [data[3], data[2], data[1], data[0], data[8], data[9], data[10], data[11], data[4], data[5], data[6],
            data[7], data[15], data[14], data[13], data[12]]

def oneToMany(lst, number):
    count = -1
    outLst = []
    for i in range(len(lst)):
        if i % number == 0:
            outLst.append([])
            count += 1
        outLst[count].append(lst[i])
    return outLst





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


# def get_offset_added_delta(dx, dy, starter_pt):
#     return starter_pt[0] + float(dx) * 0.3048, starter_pt[1] + float(dy) * 0.3048


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

def convert_to_pts(plat):
    def new_point_finder(r, angle, center_x, center_y):
        x_new = center_x + (r * math.cos(math.radians(angle)))
        y_new = center_y + (r * math.sin(math.radians(angle)))
        return x_new, y_new

    def process_plat_corners(df, start_x=0, start_y=0):
        """Process plat data with corner duplication between sides."""

        # Extract main directions and sort
        df = df.copy()
        df['main_dir'] = df['side'].str.split('_').str[0]

        result = []
        x, y = start_x, start_y

        # Process in order: west, north, east, south
        for direction in ['west', 'north', 'east', 'south']:
            group = df[df['main_dir'] == direction]
            if group.empty:
                continue

            # Sort by side string to get proper order
            group = group.sort_values('side')

            # Add starting point for this direction
            result.append([x, y, direction])

            # Process each measurement
            for _, row in group.iterrows():
                x, y = new_point_finder(float(row['length']), row['decimal_azimuth'], x, y)
                result.append([x, y, direction])

        return result

    xy_lst = []
    # x, y = 0, 0
    # custom_order = [3, 2, 1, 0, 8, 9, 10, 11, 4, 5, 6, 7, 15, 14, 13, 12]
    # dirLst = ['South_Left_2', 'South_Left_1', 'South_Right_1', 'South_Right_2',
    #           'East_Up_2', 'East_Up_1', 'East_Down_1', 'East_Down_2',
    #           'North_Left_2', 'North_Left_1', 'North_Right_1', 'North_Right_2',
    #           'West_Up_2', 'West_Up_1', 'West_Down_1', 'West_Down_2']
    dir_lst = ['west_down_2', 'west_down_1', 'west_up_1', 'west_up_2', 'north_left_2', 'north_left_1', 'north_right_1',
               'north_right_2', 'east_up_2', 'east_up_1', 'east_down_1', 'east_down_2', 'south_right_2',
               'south_right_1',
               'south_left_1', 'south_left_2']

    dir_order = ['west', 'north', 'east', 'south']
    plat = sort_dataframe_by_custom_order(plat, 'side', dir_lst)
    prev_dir = 'west'
    xy_lst = process_plat_corners(plat)
    # for val, row in plat.iterrows():
    #     test = math.floor(val / 4)
    #     xy_lst.append([x, y, dir_order[test]])
    #     if prev_dir
    #     x, y = new_point_finder(float(row['length']), float(row['decimal_azimuth']), x, y)
    # xy_lst.append([x, y, dir_order[test]])
    return tuple(xy_lst)
def sort_dataframe_by_custom_order(df, column_name, custom_order_list):
    """
    Sort DataFrame by a custom order for a specific column using pandas Categorical.

    Parameters:
    -----------
    df : pandas.DataFrame
        The DataFrame to sort
    column_name : str
        The name of the column to sort by
    custom_order_list : list
        List defining the custom sort order

    Returns:
    --------
    pandas.DataFrame
        Sorted DataFrame

    Raises:
    -------
    ValueError
        If column values don't match the custom order list
    """
    # Create a copy to avoid modifying original DataFrame
    df_sorted = df.copy()

    # Check if all values in the column exist in the custom order list
    missing_values = set(df_sorted[column_name].unique()) - set(custom_order_list)
    if missing_values:
        print(f"Warning: These values in '{column_name}' are not in custom_order_list: {missing_values}")
        # Add missing values to the end of the custom order
        extended_order = custom_order_list + list(missing_values)
    else:
        extended_order = custom_order_list

    # Convert column to Categorical with custom order
    df_sorted[column_name] = pd.Categorical(
        df_sorted[column_name],
        categories=extended_order,
        ordered=True
    )

    # Sort by the categorical column
    df_sorted = df_sorted.sort_values(by=column_name, kind='mergesort')

    # Reset index to maintain clean indexing
    df_sorted = df_sorted.reset_index(drop=True)

    return df_sorted

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

    well_path[['e_offset_delta', 'n_offset_delta']] = (
        well_path.apply(lambda row: get_offset_added_delta(row['e_offset'], row['n_offset'], starter_pt), axis=1,
                        result_type='expand'))

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


def get_first_boundary_intersection_with_index(well_df, polygon_plat, tolerance=0.1):
    """
    Find the first intersection point and return the index of the well_df point
    that comes right after the intersection.
    """
    # Convert well path to LineString
    well_coords = list(zip(well_df['e_offset_delta'], well_df['n_offset_delta']))
    well_linestring = LineString(well_coords)
    boundary = polygon_plat.exterior

    # Find intersection
    intersection = well_linestring.intersection(boundary)

    if not intersection.is_empty:
        # Handle different intersection geometries
        intersection_points = []

        if intersection.geom_type == 'Point':
            intersection_points = [intersection]
        elif intersection.geom_type == 'MultiPoint':
            intersection_points = list(intersection.geoms)
        elif intersection.geom_type == 'LineString':
            coords = list(intersection.coords)
            intersection_points = [Point(coords[0]), Point(coords[-1])]
        elif intersection.geom_type == 'MultiLineString':
            for line_seg in intersection.geoms:
                coords = list(line_seg.coords)
                intersection_points.extend([Point(coords[0]), Point(coords[-1])])

        # Find the intersection point closest to the start of well path
        if intersection_points:
            min_distance = float('inf')
            first_intersection = None

            for point in intersection_points:
                distance_along_path = well_linestring.project(point)
                if distance_along_path < min_distance:
                    min_distance = distance_along_path
                    first_intersection = point

            # Now find which segment contains this intersection
            if first_intersection:
                intersection_distance = well_linestring.project(first_intersection)

                # Calculate cumulative distances along the well path
                cumulative_distance = 0
                for i in range(len(well_coords) - 1):
                    segment_start = Point(well_coords[i])
                    segment_end = Point(well_coords[i + 1])
                    segment_length = segment_start.distance(segment_end)

                    if cumulative_distance + segment_length >= intersection_distance:
                        # The intersection is in this segment
                        # Return the index of the point after this segment
                        after_intersection_index = i + 1
                        return first_intersection, after_intersection_index, intersection_distance

                    cumulative_distance += segment_length

                # If we get here, intersection is at the very end
                return first_intersection, len(well_df) - 1, intersection_distance

    return None, None, None


# Usage
# first_intersection, after_index, distance_along_path = get_first_boundary_intersection_with_index(intersection_df,
#                                                                                                   polygon_plat)


def get_direction_sides(segment_lst, well_path, sides_generated):
    def get_first_boundary_intersection(well_df, polygon_plat, tolerance=0.1):
        """
        Complete solution to find the first intersection point.
        """
        # Convert well path to LineString
        well_coords = list(zip(well_df['e_offset_delta'], well_df['n_offset_delta']))
        well_linestring = LineString(well_coords)
        boundary = polygon_plat.exterior

        # Method 1: Check if well path intersects boundary
        intersection = well_linestring.intersection(boundary)

        if not intersection.is_empty:
            # Handle different intersection geometries
            intersection_points = []

            if intersection.geom_type == 'Point':
                intersection_points = [intersection]
            elif intersection.geom_type == 'MultiPoint':
                intersection_points = list(intersection.geoms)
            elif intersection.geom_type == 'LineString':
                # Take start and end points of intersection line
                coords = list(intersection.coords)
                intersection_points = [Point(coords[0]), Point(coords[-1])]
            elif intersection.geom_type == 'MultiLineString':
                for line_seg in intersection.geoms:
                    coords = list(line_seg.coords)
                    intersection_points.extend([Point(coords[0]), Point(coords[-1])])

            # Find the intersection point closest to the start of well path
            if intersection_points:
                min_distance = float('inf')
                first_intersection = None

                for point in intersection_points:
                    # Distance along well path from start
                    distance_along_path = well_linestring.project(point)
                    if distance_along_path < min_distance:
                        min_distance = distance_along_path
                        first_intersection = point

                return first_intersection, min_distance

        # Method 2: If no direct intersection, find closest approach
        # (in case well path comes close but doesn't exactly intersect)
        closest_point_on_boundary = boundary.interpolate(boundary.project(Point(well_coords[0])))
        distance_to_boundary = Point(well_coords[0]).distance(closest_point_on_boundary)

        if distance_to_boundary <= tolerance:
            return closest_point_on_boundary, 0.0

        return None, None

    direction = ['W', 'N', 'E', 'S']
    merged_points = list(chain(sides_generated[0], sides_generated[1], sides_generated[2], sides_generated[3]))
    plat_poly = Polygon(merged_points)
    well_path_df = well_path[['e_offset_delta', 'n_offset_delta']]
    intersection_pt, df_index, min_distance = get_first_boundary_intersection_with_index(well_path_df,
                                                                                         plat_poly)
    graph_plat_and_well(plat_poly, well_path_df)
    for k, v in enumerate(sides_generated):
        line_string_side = LineString(v)
        on_line3 = intersection_pt.within(line_string_side.buffer(1e-8))
        if on_line3:
            return [intersection_pt.x, intersection_pt.y], direction[k], df_index, well_path, well_path_df
    return [0, 0], 'Null', len(well_path), well_path, well_path_df


def findWellPathBoundaryIntersection(segment_lst, survey_data, well_parameter_data, plat_ref, min_curv_data, shl):
    direction = ['W', 'N', 'E', 'S']
    north_reference, magnetic_declination, convergence_angle, target_azimuth = well_parameter_data[0], \
    well_parameter_data[1], float(well_parameter_data[2]), float(well_parameter_data[3])
    md_lst, inc_lst, azi_lst = [i[0] for i in survey_data], [math.degrees(i[1]) for i in survey_data], [
        math.degrees(i[2]) for i in survey_data]
    bearing_lst = [wmc.bearing(float(azi_lst[i]), float(convergence_angle), north_reference, plat_ref, 0) for i in
                   range(len(md_lst))]
    section_offset_lst = []
    if len(min_curv_data) > 0:
        offsetNS_lst, offsetEW_lst, tvd_lst = [i[7] for i in min_curv_data], [i[8] for i in min_curv_data], [i[6] for i
                                                                                                             in
                                                                                                             min_curv_data]
        dogLeg_lst, fFactor_lst = [i[4] for i in min_curv_data], [i[5] for i in min_curv_data]
        bhl_dep_lst, bhl_dir_lst, delta_ns_lst, delta_ew_lst, vert_sec_lst = [i[9] for i in min_curv_data], [i[10] for i
                                                                                                             in
                                                                                                             min_curv_data], [
            i[12] for i in min_curv_data], [i[13] for i in min_curv_data], [i[11] for i in min_curv_data]
        offset_pts_lst = [[offsetEW_lst[i] + shl[0], offsetNS_lst[i] + shl[1]] for i in range(len(offsetNS_lst))]
        output = min_curv_data
    for i in range(len(min_curv_data), len(bearing_lst)):
        dogLeg_lst.append(wmc.dogLegAngle(inc_lst[i - 1], inc_lst[i], bearing_lst[i - 1], bearing_lst[i]))
        fFactor_lst.append(wmc.fFactor(dogLeg_lst[i]))
        tvd_lst.append(wmc.tvd(md_lst[i - 1], md_lst[i], inc_lst[i - 1], inc_lst[i], fFactor_lst[i], tvd_lst[i - 1]))
        offsetNS_lst.append(
            wmc.offsetNS(fFactor_lst[i], md_lst[i - 1], md_lst[i], bearing_lst[i - 1], bearing_lst[i], inc_lst[i - 1],
                         inc_lst[i], offsetNS_lst[i - 1]))
        offsetEW_lst.append(
            wmc.offsetEW(fFactor_lst[i], md_lst[i - 1], md_lst[i], bearing_lst[i - 1], bearing_lst[i], inc_lst[i - 1],
                         inc_lst[i], offsetEW_lst[i - 1]))
        bhl_dep_lst.append(wmc.bhlDeparture(offsetNS_lst[i], offsetEW_lst[i]))
        bhl_dir_lst.append(wmc.bhl_Direction(float(offsetNS_lst[i]), float(offsetEW_lst[i])))
        delta_ns_lst.append(
            wmc.deltaNS(md_lst[i - 1], md_lst[i], fFactor_lst[i], bearing_lst[i - 1], bearing_lst[i], inc_lst[i - 1],
                        inc_lst[i]))
        delta_ew_lst.append(
            wmc.deltaEW(md_lst[i - 1], md_lst[i], fFactor_lst[i], bearing_lst[i - 1], bearing_lst[i], inc_lst[i - 1],
                        inc_lst[i]))
        vert_sec_lst.append(wmc.verticalSection(target_azimuth, offsetNS_lst[i], offsetEW_lst[i]))
        offset_pts_lst.append([offsetEW_lst[i] + shl[0], offsetNS_lst[i] + shl[1]])
        section_offset_lst.append(offset_pts_lst[-1])
        #'measured_depth', 'inclination', 'azimuth','dls','ratio_factor','tvd','n_offset', 'e_offset',
        output.append([md_lst[i], inc_lst[i], azi_lst[i], bearing_lst[i], dogLeg_lst[i], fFactor_lst[i], tvd_lst[i],
                       offsetNS_lst[i], offsetEW_lst[i], bhl_dep_lst[i], bhl_dir_lst[i], vert_sec_lst[i],
                       delta_ns_lst[i], delta_ew_lst[i]])
        for j in range(len(segment_lst)):
            for k in range(len(segment_lst[j])):
                pt1 = LineString([Point(offset_pts_lst[i - 1]), Point(offset_pts_lst[i])])
                pt2 = LineString([Point(segment_lst[j][k][0]), Point(segment_lst[j][k][1])])
                outcome = pt1.intersection(pt2)
                try:
                    intersection = [outcome.x, outcome.y]

                    if intersection != [0, 0]:
                        return intersection, direction[j], i, output, offset_pts_lst
                except:
                    pass
    return [0, 0], 'Null', len(bearing_lst), min_curv_data, offset_pts_lst


# def findWellPathBoundaryIntersection(segment_lst, well_points, start_index):
#     """Find where well path intersects section boundary."""
#     # Uncomment for debugging:
#     # debug_segment_structure(segment_lst, well_points)
#
#     direction = ['W', 'N', 'E', 'S']
#
#     # Debug: Check data structures
#     if not segment_lst or not well_points:
#         return [0, 0], 'Null', len(well_points)
#
#     # Create polygon from segments for containment checks
#     all_points = []
#     for side_segments in segment_lst:
#         for segment in side_segments:
#             if isinstance(segment, list) and len(segment) >= 2:
#                 # Add first point of each segment
#                 if isinstance(segment[0], list) and len(segment[0]) >= 2:
#                     all_points.append(segment[0])
#
#     # Add last point of last segment to close polygon
#     if segment_lst and segment_lst[-1] and segment_lst[-1][-1]:
#         last_segment = segment_lst[-1][-1]
#         if isinstance(last_segment, list) and len(last_segment) >= 2:
#             if isinstance(last_segment[1], list) and len(last_segment[1]) >= 2:
#                 all_points.append(last_segment[1])
#
#     if len(all_points) < 3:
#         return [0, 0], 'Null', len(well_points)
#
#     try:
#         polygon = Polygon(all_points)
#     except Exception as e:
#         return [0, 0], 'Null', len(well_points)
#
#     # Check each well segment for intersection
#     for i in range(start_index, len(well_points) - 1):
#         if not (isinstance(well_points[i], list) and len(well_points[i]) >= 2):
#             continue
#         if not (isinstance(well_points[i + 1], list) and len(well_points[i + 1]) >= 2):
#             continue
#
#         try:
#             well_segment = LineString([well_points[i], well_points[i + 1]])
#             p1 = Point(well_points[i])
#             p2 = Point(well_points[i + 1])
#
#             # Check each side's segments
#             for j, side_segments in enumerate(segment_lst):
#                 for segment in side_segments:
#                     if not (isinstance(segment, list) and len(segment) == 2):
#                         continue
#                     if not (isinstance(segment[0], list) and len(segment[0]) >= 2):
#                         continue
#                     if not (isinstance(segment[1], list) and len(segment[1]) >= 2):
#                         continue
#
#                     try:
#                         boundary_segment = LineString(segment)
#
#                         if well_segment.intersects(boundary_segment):
#                             intersection = well_segment.intersection(boundary_segment)
#
#                             if isinstance(intersection, Point):
#                                 # Check if we're exiting (not entering)
#                                 if polygon.contains(p1) and not polygon.contains(p2):
#                                     return [intersection.x, intersection.y], direction[j], i + 1
#                     except Exception as e:
#                         continue
#
#         except Exception as e:
#             continue
#
#     return [0, 0], 'Null', len(well_points)


# def findWellPathBoundaryIntersection(segment_lst, well_points, start_index):
#
#     """Find where well path intersects section boundary."""
#     direction = ['W', 'N', 'E', 'S']
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


# def coordsAdjuster(new_coords, last_coords, direction, direction_boo):
#     """Adjust coordinates for section transitions."""
#     # This maintains boundary alignment between sections
#     # Simplified version - you may need more sophisticated alignment
#
#     directions_dict = {"W": 0, "N": 1, "E": 2, "S": 3}
#     dir_idx = directions_dict[direction]
#
#     # Find matching boundary points
#     # For now, return new_coords as-is
#     # In production, align shared boundaries
#
#     return new_coords
def findUniqueListsInListOfLists(lst):
    lst_unique = []
    for i in lst:
        if i not in lst_unique:
            lst_unique.append(i)
    return lst_unique


def coordsAdjuster(new_coords, last_coords, direction, direction_boo):
    directions_dict = {"W": '0', "N": '1', "E": "2", "S": "3"}
    direction = directions_dict[direction]
    test_corners, old_data_organized = _corner_generator_process(last_coords)
    old_data_organized = [[j[:2] for j in i] for i in old_data_organized]
    old_data_organized = [[[round(k, 1) for k in j] for j in i] for i in old_data_organized]
    old_data_organized = [findUniqueListsInListOfLists(i) for i in old_data_organized]
    lst_dict = {"0": [0, 4], "1": [4, 8], "2": [8, 12], "3": [12, 16]}
    matched_lst_dict = {"0": [12, 8], "1": [16, 12], "2": [4, 0], "3": [8, 4]}
    opp_direction_list = {"0": '2', "1": '3', "2": '0', "3": '1'}
    lst_dict_boo = {True: 0, False: 1}
    starting_pts = lst_dict[str(direction)][lst_dict_boo[direction_boo]]
    matched_pt = matched_lst_dict[str(direction)][lst_dict_boo[direction_boo]]

    new_coords = [list(i) for i in new_coords]
    diff_x, diff_y = last_coords[starting_pts][0] - new_coords[matched_pt][0], last_coords[starting_pts][1] - \
                     new_coords[matched_pt][1]
    new_coords_test = [[i[0] + diff_x, i[1] + diff_y] for i in new_coords]

    test_corners, new_coords_test_organized = _corner_generator_process(new_coords_test)
    new_coords_test_organized = [[j[:2] for j in i] for i in new_coords_test_organized]
    new_coords_test_organized = [[[round(k, 1) for k in j] for j in i] for i in new_coords_test_organized]
    new_coords_test_organized = [findUniqueListsInListOfLists(i) for i in new_coords_test_organized]
    new_coords_test_organized[int(opp_direction_list[str(direction)])] = old_data_organized[int(direction)][::-1]

    return new_coords_test


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


def graph_plat_and_well(poly, well):
    well = well.values.tolist()
    x, y = poly.exterior.xy
    x_coords_1 = [point[0] for point in well]
    y_coords_1 = [point[1] for point in well]
    fig, ax = plt.subplots()

    # 4. Plot the exterior of the polygon
    # The '*' unpacks the x and y coordinate lists
    ax.plot(x, y, color='blue', linewidth=3)
    ax.plot(x_coords_1, y_coords_1, color='red')
    # 5. Set aspect ratio and display the plot
    ax.set_aspect('equal', 'box')
    plt.show()
