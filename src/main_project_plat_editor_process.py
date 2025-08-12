import traceback
from typing import Tuple

from shapely.ops import substring
import copy
import itertools
# from main_project_well_path_tracer import WellPathTracer
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLineEdit, QSpinBox,
                             QCheckBox,
                             QDialog, QTabWidget, QTextBrowser, QTableWidget, QLabel, QTableView, QRadioButton,
                             QGraphicsView,
                             QComboBox, QMessageBox, QFileDialog, QButtonGroup)
import math
from shapely.geometry import Polygon, Point, LineString
from PyQt5.QtGui import QStandardItemModel, QStandardItem
import pandas as pd
from shapely.geometry import Polygon
import numpy as np
import ModuleAgnostic
import regex as re
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from shapely.geometry import Point, LineString, Polygon, MultiPoint
from shapely.geometry.base import BaseGeometry
import operator
from main_project_clearance import ClearanceProcess
from main_project_well_path_tracer import triangulatorWithKnownData, mainTriangulator
from main_project_plat_editor_tracer_known import triangulator_with_known

from PyQt5.QtWidgets import QHeaderView, QAbstractItemView
from typing import Dict, Any, Optional
from kop_predictor import predict_kickoff_point, analyze_survey, determine_well_type
from main_project_writer import _isolate_footage_depths
def decimal_converter(side, deg, minutes, sec, dir_val):
    """
    Simplified version with clearer logic (mathematically equivalent to above).
    """
    deg, minutes, sec = float(deg), float(minutes), float(sec)
    dec_val_base = deg + minutes / 60 + sec / 3600
    side_lower = side.lower()

    # Base orientations for each side
    if 'west' in side_lower:
        base_azimuth = 90
    elif 'east' in side_lower:
        base_azimuth = 270
    elif 'north' in side_lower:
        if dir_val in [3, 2, 'SW', 'NE']:  # SW, NE
            base_azimuth = 90
        else:  # SE, NW
            base_azimuth = 270
    elif 'south' in side_lower:
        if dir_val in [4, 1, 'NW', 'SE']:  # NW, SE
            base_azimuth = 90
        else:  # NE, SW
            base_azimuth = 270
    else:
        return dec_val_base

    # Determine if we add or subtract the bearing
    if ((side_lower.startswith('west') and dir_val in [4, 1]) or
            (side_lower.startswith('east') and dir_val in [4, 1]) or
            (side_lower.startswith('north') and dir_val not in [3, 2]) or
            (side_lower.startswith('south') and dir_val in [4, 1])):
        return base_azimuth + dec_val_base
    else:
        return base_azimuth - dec_val_base


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


# [[0, 0, 'west'], [57.47675276934449, 1367.3925489379747, 'west'], [114.95350553868899, 2734.7850978759493, 'west'], [173.65556368413476, 4134.7248956063695, 'west'],[232.35762182958055, 5534.664693336789, 'west'],
#  [232.35762182958055, 5534.664693336789, 'north'], [1576.036528947231, 5507.672156088213, 'north'], [2919.715436064882, 5480.679618839637, 'north'], [4263.3529211546975, 5454.118017579228, 'north'],[5607.163370289499, 5427.20104902549, 'north'],
#  [5607.163370289499, 5427.20104902549, 'east'], [5563.818601999683, 4040.6683897772837, 'east'], [5520.473833709867, 2654.1357305290776, 'east'], [5489.793269621355, 1312.4864831521, 'east'], [5459.1127055328425, -29.16276422487772, 'east']
#  [5459.1127055328425, -29.16276422487772, 'south'], [4144.3290198691375, -76.06526216010172, 'south'], [2819.771432677988, -121.88906290120315, 'south'], [1493.8631614177295, -168.86015830713677, 'south'], [168.60312760687225, -214.91410910015162, 'south']]
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


def find_adjacent_sections(conn, conc_code):
    query = f"select * from Adjacent"
    output = pd.read_sql(query, conn).drop_duplicates(keep="first")
    return output[output['Conc2'] == conc_code]['adjacent_Conc_Name_2'].values.tolist()


def get_plat_adjacency_dict(conc_val, direction):
    conc_loc = int(float(conc_val[:2]))
    adjacency_dict = {
        0: [0, 0, 0, 0, 0, 0, 0, 0],
        1: [36, 31, 6, 7, 12, 11, 2, 35],
        2: [35, 36, 1, 12, 11, 10, 3, 34],
        3: [34, 35, 2, 11, 10, 9, 4, 33],
        4: [33, 34, 3, 10, 9, 8, 5, 32],
        5: [32, 33, 4, 9, 8, 7, 6, 31],
        6: [31, 32, 5, 8, 7, 12, 1, 36],
        7: [6, 5, 8, 17, 18, 13, 12, 1],
        8: [5, 4, 9, 16, 17, 18, 7, 6],
        9: [4, 3, 10, 15, 16, 17, 8, 5],
        10: [3, 2, 11, 14, 15, 16, 9, 4],
        11: [2, 1, 12, 13, 14, 15, 10, 3],
        12: [1, 6, 7, 18, 13, 14, 11, 2],
        13: [12, 7, 18, 19, 24, 23, 14, 11],
        14: [11, 12, 13, 24, 23, 22, 15, 10],
        15: [10, 11, 14, 23, 22, 21, 16, 9],
        16: [9, 10, 15, 22, 21, 20, 17, 8],
        17: [8, 9, 16, 21, 20, 19, 18, 7],
        18: [7, 8, 17, 20, 19, 24, 13, 12],
        19: [18, 17, 20, 29, 30, 25, 24, 13],
        20: [17, 16, 21, 28, 29, 30, 19, 18],
        21: [16, 15, 22, 27, 28, 29, 20, 17],
        22: [15, 14, 23, 26, 27, 28, 21, 16],
        23: [14, 13, 24, 25, 26, 27, 22, 15],
        24: [13, 18, 19, 30, 25, 26, 23, 14],
        25: [24, 19, 30, 31, 36, 35, 26, 23],
        26: [23, 24, 25, 36, 35, 34, 27, 22],
        27: [22, 23, 26, 35, 34, 33, 28, 21],
        28: [21, 22, 27, 34, 33, 32, 29, 20],
        29: [20, 21, 28, 33, 32, 31, 30, 19],
        30: [19, 20, 29, 32, 31, 36, 25, 24],
        31: [30, 29, 32, 5, 6, 1, 36, 25],
        32: [29, 28, 33, 4, 5, 6, 31, 30],
        33: [28, 27, 34, 3, 4, 5, 32, 29],
        34: [27, 26, 35, 2, 3, 4, 33, 28],
        35: [26, 25, 36, 1, 2, 3, 34, 27],
        36: [25, 30, 31, 6, 1, 2, 35, 26]
    }
    used = adjacency_dict[conc_loc]
    return used[direction]


def calculate_angle(point1, point2):
    angle = math.atan2(point2.y - point1.y, point2.x - point1.x)
    return math.degrees(angle)


def fix_adj_sections(conn, adj_sections, init_plat):
    used_concs = adj_sections + [init_plat[0]]
    df = pd.DataFrame(columns=['conc', 'geometry'])
    query = f"SELECT * FROM BaseData"
    output = pd.read_sql(query, conn)
    used_data = output[output['Conc'].isin(used_concs)]
    init = used_data[used_data['Conc'] == init_plat[0]]
    init_ref_plat = Polygon(init[['Easting', 'Northing']].values.tolist())
    grouped = used_data.groupby(['Conc'])
    for i, row in grouped:
        geo_vals = Polygon(row[['Easting', 'Northing']].values.tolist())
        angle = calculate_angle(init_ref_plat.centroid, geo_vals.centroid)

        # shared_len, direction = classify_with_buffer(init_ref_plat, geo_vals, epsilon=1e-4)
    # get_plat_adjacency_dict(val, conc_val)


def classify_with_buffer(ref_poly, neigh_poly, epsilon=1e-6):
    """
    - ref_poly: Shapely Polygon (the reference section)
    - neigh_poly: Shapely Polygon (a candidate neighbor)
    - epsilon: buffer distance around ref_poly.boundary

    Returns:
      (shared_len, direction) where
        shared_len = length of (ref.boundary ∩ neigh.boundary)
                   OR, if that is zero, length of (ref.boundary.buffer(eps) ∩ neigh.boundary)
        direction  = one of "N","S","E","W","NE","NW","SE","SW", or None if no adjacency even within epsilon.
    """
    # 1) Check exact shared boundary first:
    exact_shared = ref_poly.boundary.intersection(neigh_poly.boundary)
    if not exact_shared.is_empty and exact_shared.length > 0:
        # Collect all coordinates from one or more LineStrings:
        if exact_shared.geom_type == "MultiLineString":
            coords = []
            for seg in exact_shared.geoms:  # use .geoms instead of iterating directly
                coords.extend(seg.coords)
            x0, y0 = coords[0]
            x1, y1 = coords[-1]
        else:  # single LineString
            x0, y0 = exact_shared.coords[0]
            x1, y1 = exact_shared.coords[-1]

        # Decide if edge is horizontal (→ N/S) or vertical (→ E/W):
        if abs(y1 - y0) < abs(x1 - x0):
            direction = "N" if (exact_shared.centroid.y > ref_poly.centroid.y) else "S"
        else:
            direction = "E" if (exact_shared.centroid.x > ref_poly.centroid.x) else "W"

        return exact_shared.length, direction

    # 2) Buffer the ref boundary by epsilon and check “proximal” touch:
    buf = ref_poly.boundary.buffer(epsilon)
    prox_shared = buf.intersection(neigh_poly.boundary)
    if prox_shared.is_empty or prox_shared.length == 0:
        return 0.0, None

    # 3) Classify direction via centroids for near‐touchers:
    rcx, rcy = ref_poly.centroid.x, ref_poly.centroid.y
    ncx, ncy = neigh_poly.centroid.x, neigh_poly.centroid.y
    dx, dy = ncx - rcx, ncy - rcy
    tol = epsilon * 10
    is_vert = abs(dx) < tol
    is_horiz = abs(dy) < tol

    if is_vert and dy > 0:
        direction = "N"
    elif is_vert and dy < 0:
        direction = "S"
    elif is_horiz and dx > 0:
        direction = "E"
    elif is_horiz and dx < 0:
        direction = "W"
    else:
        if dx > 0 and dy > 0:
            direction = "NE"
        elif dx < 0 and dy > 0:
            direction = "NW"
        elif dx > 0 and dy < 0:
            direction = "SE"
        else:
            direction = "SW"

    return prox_shared.length, direction


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


class SetupRelativeCoordsPage:
    def __init__(self, conn, ui):
        self.section_visits = None
        self._rel_models = {}
        self._rel_tbls = {}
        self.dict_plats_lines = {}
        self.dict_plats_pts = {}

        self.dict_figures = {}
        self.dict_canvas = {}
        self.dict_ax = {}
        self.conn = conn

        cursor = conn.cursor()

        # Query to get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")

        # Fetch all results
        tables = cursor.fetchall()

        self.ui = ui
        self.plat_footages_table = QStandardItemModel()
        self.ui.dx_survey_location_tableview_2.setModel(self.plat_footages_table)
        self.ui.dx_survey_location_tableview_2.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.currently_used_plat_data = pd.DataFrame()
        self.side_names = [
            "south_left_2", "south_left_1", "south_right_1", "south_right_2",
            "north_left_2", "north_left_1", "north_right_1", "north_right_2",
            "west_up_2", "west_up_1", "west_down_1", "west_down_2",
            "east_up_2", "east_up_1", "east_down_1", "east_down_2",
        ]
        # self.get_all_rel_wells2()
        self.setup_figs()
        self.tsr_data = pd.DataFrame()
        self.well_path_dict = {}
        all_rel_surveys, self.plat_df = self.get_all_rel_wells()
        self.currently_used_plat_data = pd.DataFrame()
        headers = ['section', 'township', 'township_dir', 'range', 'range_dir', 'meridian']
        base_data_combo_lst = ["", "", "", "", "", ""]
        data = [base_data_combo_lst, base_data_combo_lst, base_data_combo_lst, base_data_combo_lst, base_data_combo_lst,
                base_data_combo_lst]
        self.combo_box_df = pd.DataFrame(data, columns=headers)
        self.ui.tracer_rel_push_button.pressed.connect(self.rel_plat_data_filler)
        self.setup_combo_boxes(all_rel_surveys)
        # self.setup_plat_data_boxes()
        self.setup_section_combo_box()

    def set_well_path_dict(self, well_path_dict):
        self.well_path_dict = well_path_dict

    def set_tsr_data(self, tsr_data):
        self.tsr_data = tsr_data

    def setup_plat_data_boxes(self):
        print('setting up')
        row_cols = ["length", "degrees", "minutes", "seconds", "bearing_str", 'decimal_azimuth']
        # records = []
        side_names = ["south_left_2", "south_left_1", "south_right_1", "south_right_2",
                      "north_left_2", "north_left_1", "north_right_1", "north_right_2",
                      "west_up_2", "west_up_1", "west_down_1", "west_down_2",
                      "east_up_2", "east_up_1", "east_down_1", "east_down_2"]
        # for version in range(1, 9):
        #     for side in side_names:
        #         try:
        #             # Get the QTableView widget by its name
        #             table_widget_name = f"{side}_table_rel_{version}"
        #             tbl: QTableView = getattr(self.ui, table_widget_name)
        #             # Check if the table and its model exist
        #             if tbl and tbl.model():
        #                 # Connect the model's dataChanged signal to the handler.
        #                 # Use a lambda to capture the current `side` and `version`.
        #                 tbl.model().dataChanged.connect(
        #                     lambda top_left, bottom_right, roles, current_side=side, current_version=version: \
        #                         self.connect_and_process_user_data(top_left, current_side, current_version)
        #                 )
        #             else:
        #                 print('nada')
        #         except AttributeError:
        #             # This is good practice in case a widget name is misspelled or doesn't exist
        #             print(f"Warning: Widget '' not found.")

        # for i in range(8):
        #     pass
        #     # cb = getattr(self.ui, f"version_combo_rel_{i + 1}")
        #     # cb.blockSignals(True)
        #     # cb.clear()
        #     # cb.addItems(lst)
        #     # cb.activated[int].connect(lambda idx, ver=i + 1, combo=cb: self.plat_combo_box_fill(ver, idx, combo))
        #     # cb.blockSignals(False)

    def process_kop_lp(self, results):
        if results['kop']:
            kop = results['kop']
            kop_df = pd.DataFrame([kop])
            kop_df['Point'] = 'KOP'
            # kop_df['type'] = f"{sot}{label}"

            # Landing point analysis for all directional/horizontal wells
            if results['landing_point']:
                lp = results['landing_point']
                lp_df = pd.DataFrame([lp])
                lp_df['Point'] = 'LP'
                # lp_df['type'] = f"{sot}{label}"
                return kop_df, lp_df
            else:
                if results['well_type'] == 'directional':
                    print("  (Well may still be building or have irregular profile)")
                return kop_df, pd.DataFrame()

    def process_for_spec_points(self, min_curv_data):
        results = analyze_survey(min_curv_data)
        kop_true,lp_true = self.process_kop_lp(results)
        kop_sr = min_curv_data[min_curv_data['measured_depth'] == kop_true['measured_depth'].iloc[0]]
        lp_sr = min_curv_data[min_curv_data['measured_depth'] == lp_true['measured_depth'].iloc[0]]
        bhl_sr = min_curv_data.tail(1)
        spec_vals = pd.concat([kop_sr, lp_sr, bhl_sr])
        spec_vals = spec_vals[['FNL', 'FSL', 'FEL', 'FWL']]
        spec_vals['lbl'] = ['kop', 'lp', 'bhl']
        return spec_vals
    def connect_and_process_user_data(self, top_left_index, side, version):
        def get_plat_coords():
            query = "select * from SectionPlatDataAGRC"
            return pd.read_sql(query, self.conn).drop_duplicates(keep="first")

        def retrieve_well_data():
            return [self.ui.dx_survey_north_ref_line.text(),
                    self.ui.dx_survey_mag_dec_line.text(),
                    self.ui.dx_survey_conv_angle_line.text(),
                    self.ui.dx_survey_pro_azi_line.text()]

        all_plats_df = {}
        currently_used_plat_data = self.collect_relative_data()
        consecutive_codes, _ = pd.factorize(currently_used_plat_data['order'])
        currently_used_plat_data['range'] = consecutive_codes + 1
        grouped = currently_used_plat_data.groupby(['range'])
        all_conc_codes = []
        for x, df in grouped:
            plat_coords = convert_to_pts(df)
            conc = df['conc'].iloc[0]
            all_plats_df[conc] = plat_coords
            all_conc_codes.append(conc)
        plat_df = self.data_frame_plat_builder(grouped)
        plat_df_conc = plat_df['conc'].unique()
        min_curv_data, gdf_data, known_conc_data, all_pts_data = self.run_plat_well_tracer(
            current_plat_coords=plat_df[plat_df['conc'] == plat_df_conc[0]],
            current_plat_conc=plat_df_conc[0], existing_data = True)
        collected_data = self.collect_relative_data()
        spec_vals = self.process_for_spec_points(min_curv_data)

        self.writer_plat_process(gdf_data, collected_data, spec_vals)

        # all_plats_df = {}
        # self.currently_used_plat_data = self.collect_relative_data()
        # consecutive_codes, _ = pd.factorize(self.currently_used_plat_data['order'])
        # self.currently_used_plat_data['range'] = consecutive_codes + 1
        # initial_plat_conc = \
        #     self.currently_used_plat_data[self.currently_used_plat_data['order'] == version]['conc'].iloc[0]
        # grouped = self.currently_used_plat_data.groupby(['range'])
        # all_conc_codes = []
        # for x, df in grouped:
        #     plat_coords = convert_to_pts(df)
        #     conc = df['conc'].iloc[0]
        #     all_plats_df[conc] = plat_coords
        #     all_conc_codes.append(conc)
        # # self.draw_plat_solo(all_plats_df[initial_plat_conc], version)
        # plat_df = self.data_frame_plat_builder(grouped)
        # plat_df_conc = plat_df['conc'].unique()
        # # well_path_dict, original_all_plats_df, current_plat_coords, well_path, current_plat_conc, currently_used_plat_data
        # # def rel_plat_main_activate(serui glf):
        # #     plat_df = data_frame_plat_builder()
        # #     plat_df_conc = plat_df['conc'].unique()
        # current_plat_coords = plat_df[plat_df['conc'] == plat_df_conc[0]]
        # current_plat_conc = plat_df_conc[0]
        # original_all_plats_df = plat_df
        # # min_curv_data, gdf_data, known_conc_data, all_pts_data = self.run_plat_well_tracer(
        # #     current_plat_coords=plat_df[plat_df['conc'] == plat_df_conc[0]],
        # #     current_plat_conc=plat_df_conc[0], original_all_plats_df=plat_df)
        #
        # well_paths_lst = [k for k, v in self.well_path_dict.items()]
        # all_plats_df = plat_df
        # all_pts_data = get_plat_coords()
        #
        # min_curv_data, known_conc_data, section_degrees_data, plat_north_refs_lst, shl_calc = mainTriangulator(
        #     conn=self.conn,
        #     tsr_data_df=self.tsr_data,
        #     data_plat_coords=current_plat_coords,
        #     df=all_pts_data,
        #     conc=current_plat_conc,
        #     survey_data_df=self.well_path_dict['pln_df_grid_dx'].clearance_data,
        #     well_parameter_data=retrieve_well_data(), ui = self.ui, existing_data=True)
        #
        # # self.writer_plat_process(gdf_data, all_pts_data)
        #
        # triangulator_with_known(
        #     conn=self.conn,
        #     data_plat_coords=current_plat_coords,
        #     survey_data_df=self.well_path_dict['pln_df_grid_dx'].clearance_data,
        #     well_parameter_data=retrieve_well_data())
        # self.rel_plat_data_filler(version)
        # output = self.collect_relative_data()
        pass

    def setup_unique_values_for_combo_boxes(self, df):
        output_sections = tuple(str(x) for x in sorted(int(x) for x in df['section'].unique()))
        output_township = tuple(str(x) for x in sorted(int(x) for x in df['township'].unique()))
        output_township_dirs = tuple(df['township_bearing_str'].unique())
        output_range = tuple(str(x) for x in sorted(int(x) for x in df['rng'].unique()))
        output_range_dirs = tuple(df['rng_bearing_str'].unique())
        output_meridians = tuple(df['baseline_str'].unique())
        return output_sections, output_township, output_township_dirs, output_range, output_range_dirs, output_meridians

    def setup_section_combo_box(self):
        def standard_combo_box_setup(cb, lst):
            lst = tuple([""] + list(lst))
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(lst)
            cb.activated[int].connect(
                lambda idx, ver=i + 1, combo=cb: self.run_combo_box_section(ver, idx, combo))
            cb.blockSignals(False)

        output_sections, output_township, output_township_dirs, output_range, output_range_dirs, output_meridians = self.setup_unique_values_for_combo_boxes(
            self.plat_df)
        for i in range(8):
            try:
                ui_val = i + 1
                section_cb = getattr(self.ui, f"section_combo_rel_{ui_val}")
                township_cb = getattr(self.ui, f"township_combo_rel_{ui_val}")
                township_dir_cb = getattr(self.ui, f"township_dir_combo_rel_{ui_val}")
                range_cb = getattr(self.ui, f"range_combo_rel_{ui_val}")
                range_dir_cb = getattr(self.ui, f"range_dir_combo_rel_{ui_val}")
                meridian_cb = getattr(self.ui, f"meridian_combo_rel_{ui_val}")
                standard_combo_box_setup(section_cb, output_sections)
                standard_combo_box_setup(township_cb, output_township)
                standard_combo_box_setup(township_dir_cb, output_township_dirs)
                standard_combo_box_setup(range_cb, output_range)
                standard_combo_box_setup(range_dir_cb, output_range_dirs)
                standard_combo_box_setup(meridian_cb, output_meridians)

            except AttributeError:
                pass

    def run_combo_box_section(self, version: int, index: int, combo: QComboBox):
        # def direction_to_number(variable, val):
        #     translations = {
        #         'rng': {'w': '2', 'e': '1', '':''},
        #         'township': {'s': '2', 'n': '1', '':''},
        #         'baseline': {'u': '2', 's': '1', '':''},
        #     }
        #     return translations.get(variable, {}).get(val, val)

        def sql_combo_box_process():
            # Create a mapping of column names to values
            filters = {
                'section': section_val,
                'township': township_val,
                'township_bearing_str': township_dir_val,
                'rng': range_val,
                'rng_bearing_str': range_dir_val,
                'baseline_str': meridian_val
            }

            # Filter out empty values
            active_filters = {col: val for col, val in filters.items() if val != ""}

            # Start with the full dataframe
            filtered_data = self.plat_df
            # Apply each non-empty filter
            for col, val in active_filters.items():
                if val.isdigit():
                    filtered_data = filtered_data[filtered_data[col] == int(float(val))]
                else:
                    filtered_data = filtered_data[filtered_data[col] == val]
            return filtered_data

        def update_combo_boxes_with_filtered(filtered_data):
            output_sections, output_township, output_township_dirs, output_range, output_range_dirs, output_meridians = self.setup_unique_values_for_combo_boxes(
                filtered_data)
            current_selections = {
                'section': section_val,
                'township': township_val,
                'township_bearing_str': township_dir_val,
                'rng': range_val,
                'rng_bearing_str': range_dir_val,
                'baseline_str': meridian_val
            }
            combo_updates = [
                (section_cb, output_sections, 'section'),
                (township_cb, output_township, 'township'),
                (township_dir_cb, output_township_dirs, 'township_bearing_str'),
                (range_cb, output_range, 'rng'),
                (range_dir_cb, output_range_dirs, 'rng_bearing_str'),
                (meridian_cb, output_meridians, 'baseline_str')
            ]
            if not filtered_data.empty:
                for cb, vals, key in combo_updates:
                    new_data = tuple([""] + list(vals))
                    cb.blockSignals(True)
                    cb.clear()
                    cb.addItems(new_data)

                    try:
                        cb.activated[int].disconnect()
                    except TypeError:
                        pass  # No connections to disconnect
                    if current_selections[key] in new_data:
                        cb.setCurrentText(current_selections[key])
                    if len(new_data) == 2:
                        cb.setCurrentText(new_data[1])
                    # Reconnect signal
                    cb.activated[int].connect(
                        lambda idx, ver=version, combo_ref=cb: self.run_combo_box_section(ver, idx, combo_ref))

                    # Unblock signals
                    cb.blockSignals(False)

        section_cb = getattr(self.ui, f"section_combo_rel_{version}")
        township_cb = getattr(self.ui, f"township_combo_rel_{version}")
        township_dir_cb = getattr(self.ui, f"township_dir_combo_rel_{version}")
        range_cb = getattr(self.ui, f"range_combo_rel_{version}")
        range_dir_cb = getattr(self.ui, f"range_dir_combo_rel_{version}")
        meridian_cb = getattr(self.ui, f"meridian_combo_rel_{version}")

        section_val = section_cb.currentText()
        township_val = township_cb.currentText()
        township_dir_val = township_dir_cb.currentText()
        range_val = range_cb.currentText()
        range_dir_val = range_dir_cb.currentText()
        meridian_val = meridian_cb.currentText()
        output_data = sql_combo_box_process()
        if len(output_data['label'].unique()) == 1:
            self.fill_tsr_data(output_data, version)
            self.fill_calls_models(output_data, version)
            self.fill_calls_data(output_data, version)
        # update_combo_boxes_with_filtered(output_data)

    def run_sql_search_process(self):
        pass

    def setup_figs(self):
        for i in range(8):
            # ui_element = getattr(self.ui, f"well_graphic_mp_individual_{i + 1}")
            # ui_viz = getattr(self.ui, f"well_graphic_section_all_layout_{i + 1}")
            ui_viz = getattr(self.ui, f"well_graphic_mp_individual_{i + 1}")

            self.dict_figures[i + 1] = plt.figure()
            self.dict_canvas[i + 1] = FigureCanvas(self.dict_figures[i + 1])
            self.dict_ax[i + 1] = self.dict_figures[i + 1].subplots()
            ui_viz.addWidget(self.dict_canvas[i + 1])
            line_collection_template, = self.dict_ax[i + 1].plot([], [], color='black', linewidth=1, zorder=5)
            scatter_collection_template = self.dict_ax[i + 1].scatter([], [], c='black', s=50, zorder=2, alpha=0.5)
            self.dict_plats_lines[i + 1] = line_collection_template
            self.dict_plats_pts[i + 1] = scatter_collection_template

            self.dict_ax[i + 1].axis('equal')
            # self.zoom_fac = self.zp.zoom_factory(self.dict_ax[i + 1], 1.1)

    def get_all_rel_wells(self):
        query = f"select * from tsr_plats_surveys"
        output = pd.read_sql(query, self.conn)
        df_sorted = output.sort_values(
            by=[
                'baseline', 'section',
                'township_bearing', 'rng_bearing',
                'township', 'rng', 'version'],
            ascending=[True, True, True, True, True, True, True]
        ).reset_index(drop=True)
        output_labels = tuple(df_sorted['label'].unique())
        return output_labels, df_sorted

    def setup_combo_boxes(self, lst):
        for i in range(8):
            cb = getattr(self.ui, f"version_combo_rel_{i + 1}")
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(lst)
            cb.activated[int].connect(lambda idx, ver=i + 1, combo=cb: self.plat_combo_box_fill(ver, idx, combo))
            cb.blockSignals(False)

    def fill_tsr_data(self, output, version):
        first_line = output.iloc[0]
        getattr(self.ui, f"section_input_rel_{version}").setText(str(first_line['section']))
        getattr(self.ui, f"township_input_rel_{version}").setText(str(first_line['township']))
        getattr(self.ui, f"township_dir_input_rel_{version}").setText(str(first_line['township_bearing_str']))
        getattr(self.ui, f"range_input_rel_{version}").setText(str(first_line['rng']))
        getattr(self.ui, f"range_dir_input_rel_{version}").setText(str(first_line['rng_bearing_str']))
        getattr(self.ui, f"meridian_input_rel_{version}").setText(str(first_line['baseline_str']))

    def fill_calls_models(self, output, version):
        if not hasattr(self, "_rel_models"):
            self._rel_models = {}
        if not hasattr(self, "_rel_tbls"):
            self._rel_tbls = {}
            # define which DataFrame columns you want in your tables

        for side_name, df_side in output.groupby("side"):
            tbl = getattr(self.ui, f"{side_name}_table_rel_{version}")
            model = QStandardItemModel(tbl)
            # … populate model …
            self._rel_models[(side_name, version)] = model
            self._rel_tbls[(side_name, version)] = tbl

    def fill_calls_data(self, output, version):
        cols = ["length", "degrees", "minutes", "seconds", "bearing_str"]

        for idx, side in enumerate(self.side_names):
            model = self._rel_models[(side, version)]
            tbl = self._rel_tbls[(side, version)]
            model.removeRows(0, model.rowCount())
            row = output[output["side"] == side].iloc[0]
            if row.empty:
                # nothing to show for this side
                tbl.setModel(model)
                continue
            # 3) append one QStandardItem per column
            for val in (row[col] for col in cols):
                item = QStandardItem(str(val))
                # store the raw value as user‐data if you like:
                item.setData(val)
                model.appendRow(item)
            tbl.setModel(model)
            tbl.verticalHeader().setVisible(False)
            tbl.horizontalHeader().setVisible(False)
            tbl.setShowGrid(True)
            tbl.show()
            tbl.model().dataChanged.connect(
                lambda top_left, _, __, current_side=side, current_version=version: self.connect_and_process_user_data(
                    top_left, current_side, current_version)
            )

    def plat_combo_box_fill(self, version: int, index: int, combo: QComboBox):
        # def fill_tsr_data():
        #     first_line = output.iloc[0]
        #     getattr(self.ui, f"section_input_rel_{version}").setText(str(first_line['section']))
        #     getattr(self.ui, f"township_input_rel_{version}").setText(str(first_line['township']))
        #     getattr(self.ui, f"township_dir_input_rel_{version}").setText(str(first_line['township_bearing_str']))
        #     getattr(self.ui, f"range_input_rel_{version}").setText(str(first_line['rng']))
        #     getattr(self.ui, f"range_dir_input_rel_{version}").setText(str(first_line['rng_bearing_str']))
        #     getattr(self.ui, f"meridian_input_rel_{version}").setText(str(first_line['baseline_str']))
        #
        # def fill_calls_models():
        #     if not hasattr(self, "_rel_models"):
        #         self._rel_models = {}
        #     if not hasattr(self, "_rel_tbls"):
        #         self._rel_tbls = {}
        #         # define which DataFrame columns you want in your tables
        #
        #     for side_name, df_side in output.groupby("side"):
        #         tbl = getattr(self.ui, f"{side_name}_table_rel_{version}")
        #         model = QStandardItemModel(tbl)
        #         # … populate model …
        #         self._rel_models[(side_name, version)] = model
        #         self._rel_tbls[(side_name, version)] = tbl
        #     # group your DataFrame by the 'side' field
        #     # for side_name, df_side in output.groupby("side"):
        #     #     # find the matching QTableView on your UI
        #     #     tbl: QTableView = getattr(self.ui,f"{side_name}_table_rel_{version}")
        #     #     self._rel_tbls[(side_name, version)] = tbl
        #     #     # build a fresh model
        #     #     model = QStandardItemModel(tbl)  # parent it to self!
        #     #     model.setColumnCount(len(cols))
        #     #     model.setHorizontalHeaderLabels(headers)
        #     #
        #     #     # fill rows
        #     #     for r, (_, row) in enumerate(df_side.iterrows()):
        #     #         for c, col in enumerate(cols):
        #     #             item = QStandardItem(str(row[col]))
        #     #             model.setItem(r, c, item)
        #     #
        #     #     # attach it
        #     #     tbl.setModel(model)
        #     #     # stash it so Python doesn’t GC it—and so you can update it later if needed
        #     #
        #     #     self._rel_models[(side_name, version)] = model
        #     #     # self._rel_tbls[(side_name, version)] = tbl
        #
        # def fill_calls_data():
        #     for idx, side in enumerate(self.side_names):
        #         model = self._rel_models[(side, version)]
        #         tbl = self._rel_tbls[(side, version)]
        #         model.removeRows(0, model.rowCount())
        #         row = output[output["side"] == side].iloc[0]
        #         if row.empty:
        #             # nothing to show for this side
        #             tbl.setModel(model)
        #             continue
        #         # 3) append one QStandardItem per column
        #         for val in (row[col] for col in cols):
        #             item = QStandardItem(str(val))
        #             # store the raw value as user‐data if you like:
        #             item.setData(val)
        #             model.appendRow(item)
        #         tbl.setModel(model)
        #         tbl.verticalHeader().setVisible(False)
        #         tbl.horizontalHeader().setVisible(False)
        #         tbl.setShowGrid(True)
        #         tbl.show()

        cols = ["length", "degrees", "minutes", "seconds", "bearing_str"]
        current_label = combo.itemText(index)
        query = f"select * from tsr_plats_surveys where label = '{current_label}'"
        output = pd.read_sql(query, self.conn)
        self.fill_tsr_data(output, version)
        self.fill_calls_models(output, version)
        self.fill_calls_data(output, version)
        self.rel_plat_data_filler(version)

    def data_frame_plat_builder(self, grouped):
        rows = []
        for _rng, df_build in grouped:
            _conc = df_build['conc'].iloc[0]
            coords_build = convert_to_pts(df_build)
            df_pts = pd.DataFrame(coords_build, columns=['x', 'y', 'side'])
            df_pts['conc'] = _conc
            df_pts['point_i'] = df_pts.groupby('side').cumcount()
            rows.append(df_pts)
        plat_df = pd.concat(rows, ignore_index=True)
        plat_df = plat_df[['conc', 'side', 'point_i', 'x', 'y']]
        return plat_df

    def rel_plat_data_filler(self, version):
        all_plats_df = {}
        self.currently_used_plat_data = self.collect_relative_data()
        consecutive_codes, _ = pd.factorize(self.currently_used_plat_data['order'])
        self.currently_used_plat_data['range'] = consecutive_codes + 1
        grouped = self.currently_used_plat_data.groupby(['range'])
        all_conc_codes = []
        for x, df in grouped:
            plat_coords = convert_to_pts(df)
            conc = df['conc'].iloc[0]
            all_plats_df[conc] = plat_coords
            all_conc_codes.append(conc)
        plat_df = self.data_frame_plat_builder(grouped)
        plat_df_conc = plat_df['conc'].unique()

        min_curv_data, gdf_data, known_conc_data, all_pts_data = self.run_plat_well_tracer(
            current_plat_coords=plat_df[plat_df['conc'] == plat_df_conc[0]],
            current_plat_conc=plat_df_conc[0])
        spec_vals = self.process_for_spec_points(min_curv_data)

        self.writer_plat_process(gdf_data, all_pts_data, spec_vals)
        print("OUTPUT")

    def write_clearance_footages(self, footage_lst: pd.DataFrame) -> None:
        """Display clearance footage measurements in dedicated table view.

        Presents clearance distances (FNL, FSL, FEL, FWL) for critical depth points
        in a formatted table for regulatory compliance and engineering analysis.
        Provides clear visualization of well positioning relative to plat boundaries
        with standardized footage precision for professional reporting.

        Args:
            footage_lst (pd.DataFrame): Footage data with clearance measurements for key depths
            ui (Any): PyQt5 user interface object containing footages table view
        """
        # Remove non-footage columns for focused display
        # footage_lst = footage_lst.drop(columns=['measured_depth', 'azimuth'])

        # Setup table for batch data loading
        self.ui.dx_survey_location_tableview_2.setUpdatesEnabled(False)
        self.plat_footages_table.setRowCount(0)
        self.ui.dx_survey_location_tableview_2.setModel(self.plat_footages_table)

        # Convert DataFrame to list format for table population
        data = footage_lst.values.tolist()
        self.plat_footages_table.setRowCount(len(data))

        # Populate table with formatted footage data
        for row_idx, row in enumerate(data):
            for col_idx, value in enumerate(row):
                if col_idx != 4:  # Skip label column for numerical formatting
                    # Round numerical values to 2 decimal places for footage display
                    item = QStandardItem(str(round(float(value), 2)))
                else:
                    # Display label column as-is
                    item = QStandardItem(str(value))
                self.plat_footages_table.setItem(row_idx, col_idx, item)

        # Configure table headers and appearance
        columns = footage_lst.columns.values
        self.plat_footages_table.setHorizontalHeaderLabels(columns)
        self._configure_table_appearance(self.ui.dx_survey_location_tableview_2)
    def _configure_table_appearance(self, table_view: Any) -> None:
        """Configure table view properties for professional appearance.

        Internal method for standardizing table display settings across
        all survey data presentations.

        Args:
            table_view (Any): PyQt5 table view component to configure
        """
        table_view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table_view.verticalHeader().setVisible(False)  # Hide row numbers
        table_view.setShowGrid(True)
        table_view.setUpdatesEnabled(True)
        table_view.show()
        table_view.viewport().update()
    def writer_plat_process(self, df, all_pts_df, spec_vals):
        def combo_box(value, ui_element):
            ui_element.blockSignals(True)
            index = ui_element.findText(str(value))
            ui_element.setCurrentIndex(index)
            ui_element.blockSignals(False)
        for idx, row in df.iterrows():
            ref_val = idx + 1
            sec_ui = getattr(self.ui, f"section_combo_rel_{ref_val}")
            ts_ui = getattr(self.ui, f"township_combo_rel_{ref_val}")
            ts_dir_ui = getattr(self.ui, f"township_dir_combo_rel_{ref_val}")
            rng_ui = getattr(self.ui, f"range_combo_rel_{ref_val}")
            rng_dir_ui = getattr(self.ui, f"range_dir_combo_rel_{ref_val}")
            baseline_ui = getattr(self.ui, f"meridian_combo_rel_{ref_val}")
            combo_box(row['sec'], sec_ui)
            combo_box(row['ts'], ts_ui)
            combo_box(row['ts_dir'], ts_dir_ui)
            combo_box(row['rng'], rng_ui)
            combo_box(row['rng_dir'], rng_dir_ui)
            combo_box(row['baseline'], baseline_ui)
            plat_data = list(row['geometry'].exterior.coords)
            used_plat_df = all_pts_df[all_pts_df['conc'] == row['Conc']]
            self.draw_plat_solo(plat_data, ref_val)
            self.fill_tsr_data(used_plat_df, ref_val)
            self.fill_calls_models(used_plat_df, ref_val)
            self.fill_calls_data(used_plat_df, ref_val)
            # sec_ui.blockSignals(True)
            # ts_ui.blockSignals(True)
            # ts_dir_ui.blockSignals(True)
            # rng_ui.blockSignals(True)
            # rng_dir_ui.blockSignals(True)
            # baseline_ui.blockSignals(True)

            # index = sec_ui.findText(str(row['sec']))
            # sec_ui.setCurrentIndex(index)
            # sec_ui.setText(row['sec'])

            # 'sec', 'ts', 'ts_dir', 'rng', 'rng_dir', 'baseline'
        self.write_clearance_footages(spec_vals)
        pass

    def grapher(self, data):
        x_coords = [point[0] for point in data]
        y_coords = [point[1] for point in data]
        plt.figure(figsize=(10, 8))
        plt.plot(x_coords, y_coords, 'b-', linewidth=2, marker='o', markersize=4)
        plt.xlabel('X Coordinate')
        plt.ylabel('Y Coordinate')
        plt.title('XY Plot')
        plt.grid(True, alpha=0.3)
        plt.axis('equal')
        plt.show()

    def grapher_two_plots(self, data1, data2):
        # data2 = [i for i in data2 if i != 0]
        x_coords_1 = [point[0] for point in data1]
        y_coords_1 = [point[1] for point in data1]

        x_coords_2 = [point[0] for point in data2]
        y_coords_2 = [point[1] for point in data2]
        plt.figure(figsize=(10, 8))
        plt.plot(x_coords_1, y_coords_1, color='red')
        plt.plot(x_coords_2, y_coords_2, color='blue')

        plt.xlabel('X Coordinate')
        plt.ylabel('Y Coordinate')
        plt.title('XY Plot')
        plt.grid(True, alpha=0.3)
        plt.axis('equal')
        plt.show()

    def graph_one_polygon(self, poly):
        x, y = poly.exterior.xy

        # x_coords_1 = [point[0] for point in data1]
        # y_coords_1 = [point[1] for point in data1]

        fig, ax = plt.subplots()

        # 4. Plot the exterior of the polygon
        # The '*' unpacks the x and y coordinate lists
        ax.plot(x, y, color='blue', linewidth=3)

        # 5. Set aspect ratio and display the plot
        ax.set_aspect('equal', 'box')
        plt.show()

    def draw_plat_solo(self, plat, version):
        canvas_used = getattr(self, f"dict_canvas")[version]
        ax_used = getattr(self, f"dict_ax")[version]
        line_collection_used = self.dict_plats_lines[version]
        pts_collection_used = self.dict_plats_pts[version]
        x = [point[0] for point in plat]
        y = [point[1] for point in plat]

        pts_collection_used.set_offsets([i[:2] for i in plat])
        line_collection_used.set_data(x, y)
        ax_used.relim()
        ax_used.autoscale_view()
        canvas_used.blit(ax_used.bbox)
        canvas_used.draw()
        # pass

    def collect_relative_data(self):
        def convert_conc(sec, ts, ts_dir, rng, rng_dir, baseline):
            translations = {
                'rng': {'2': 'W', '1': 'E'},
                'township': {'2': 'S', '1': 'N'},
                'baseline': {'2': 'U', '1': 'S'},
                'alignment': {'1': 'SE', '2': 'NE', '3': 'SW', '4': 'NW'}
            }
            section = str(int(float(sec))).zfill(2)
            township = str(int(float(ts))).zfill(2)
            rng = str(int(float(rng))).zfill(2)

            # Handle direction codes (which might also be floats)
            ts_dir = str(ts_dir)
            rng_dir = str(rng_dir)
            baseline = str(baseline)

            # Translate direction codes
            ts_dir = translations.get('township', {}).get(ts_dir, ts_dir).upper()
            rng_dir = translations.get('rng', {}).get(rng_dir, rng_dir).upper()
            baseline = translations.get('baseline', {}).get(baseline, baseline).upper()

            return "".join([section, township, ts_dir, rng, rng_dir, baseline])

        """
        Read all the inputs and tables for versions 1–8 and return
        a DataFrame with one row per table-entry, with these columns:
          ['label','version',
           'section','township','township_bearing_str',
           'rng','rng_bearing_str','baseline_str',
           'side','length','degrees','minutes','seconds',
           'bearing_str','decimal_azimuth']
        """
        side_names = ["south_left_2", "south_left_1", "south_right_1", "south_right_2",
                      "north_left_2", "north_left_1", "north_right_1", "north_right_2",
                      "west_up_2", "west_up_1", "west_down_1", "west_down_2",
                      "east_up_2", "east_up_1", "east_down_1", "east_down_2"]

        # the columns in each table, in the same order you built them
        row_cols = ["length", "degrees", "minutes", "seconds", "bearing_str", 'decimal_azimuth']
        records = []
        for version in range(1, 9):
            # 1) read the “header” fields
            rec_base = {
                "section": getattr(self.ui, f"section_input_rel_{version}").text(),
                "township": getattr(self.ui, f"township_input_rel_{version}").text(),
                "township_bearing_str": getattr(self.ui, f"township_dir_input_rel_{version}").text(),
                "rng": getattr(self.ui, f"range_input_rel_{version}").text(),
                "rng_bearing_str": getattr(self.ui, f"range_dir_input_rel_{version}").text(),
                "baseline_str": getattr(self.ui, f"meridian_input_rel_{version}").text(),
            }
            # 2) for each side, read that one-column table
            for side in side_names:
                tbl: QTableView = getattr(self.ui, f"{side}_table_rel_{version}")
                model = tbl.model()
                if model is None:
                    continue

                # start a fresh record for this side
                rec = dict(rec_base)
                rec["side"] = side

                # iterate each row in the single column
                for row_idx, field in enumerate(row_cols):
                    # safe‐guard if someone changed row-count
                    if row_idx < model.rowCount():
                        item = model.item(row_idx, 0)
                        rec[field] = item.text() if item is not None else ""
                    else:
                        rec[field] = ""
                rec['order'] = version
                records.append(rec)
        df = pd.DataFrame.from_records(records)
        df['conc'] = df.apply(
            lambda row: convert_conc(row['section'], row['township'], row['township_bearing_str'],
                                     row['rng'],
                                     row['rng_bearing_str'], row['baseline_str']), axis=1)
        df['decimal_azimuth'] = df.apply(
            lambda row: decimal_converter(row['side'], row['degrees'], row['minutes'], row['seconds'],
                                          row['baseline_str']), axis=1)
        return df

    def main_tracer_process(self, current_plat_coords, current_plat_conc, original_all_plats_df, well_path, title):

        def get_direction_sides():
            used_df = all_plats_df[all_plats_df['conc'] == current_plat_conc]
            grouped_df = used_df.groupby('side')
            dict_index = {'e': 2, 'w': 6, 'n': 0, 's': 4}
            for r, group_df in grouped_df:
                line_string_side = Polygon(group_df[['x', 'y']].values.tolist())
                on_line3 = intersection_pt.within(line_string_side.buffer(1e-8))

            for r, group_df in grouped_df:
                line_string_side = Polygon(group_df[['x', 'y']].values.tolist())
                on_line3 = intersection_pt.within(line_string_side.buffer(1e-8))
                if on_line3:
                    return r[0], dict_index[r[0]]

        def well_path_prox(intersection, side_dict_all, direction, tol=1e-8):
            pt = intersection if isinstance(intersection, Point) else Point(intersection)

            # pick just the one side
            side_key = direction.lower()
            if side_key == 'n':
                # coords = side_dict_all['north']
                coords = side_dict_all[side_dict_all['side'] == 'north'][['x', 'y']].values.tolist()
            elif side_key == 's':
                # coords = side_dict_all['south']
                coords = side_dict_all[side_dict_all['side'] == 'south'][['x', 'y']].values.tolist()

            elif side_key == 'e':
                # coords = side_dict_all['east']
                coords = side_dict_all[side_dict_all['side'] == 'east'][['x', 'y']].values.tolist()

            elif side_key == 'w':
                # coords = side_dict_all['west']
                coords = side_dict_all[side_dict_all['side'] == 'west'][['x', 'y']].values.tolist()

            else:
                raise KeyError(f"Direction must be one of 'n','s','e','w', not {direction!r}")

            # the “start” and “end” of that side’s line
            p_start = Point(coords[0])  # corner A
            p_end = Point(coords[-1])  # corner B

            # whichever corner is nearer the intersection…
            return pt.distance(p_start) < pt.distance(p_end)

        def get_offset_added_delta(x, y, dx, dy):

            return x + float(dx), y + float(dy)

        def get_dataframe_from_qtableview():
            # Get the model
            model = self.ui.dx_survey_table_mod.model()
            if model is None:
                print("The QTableView does not have a model.")
                return None
            # Get the number of rows and columns
            rows = model.rowCount()
            columns = model.columnCount()
            # Create a list to store all the data
            data = []
            # Get column headers
            headers = []
            for column in range(columns):
                header = model.headerData(column, Qt.Horizontal, Qt.DisplayRole)
                headers.append(str(header))
            # Iterate through each cell in the table
            for row in range(rows):
                row_data = []
                for column in range(columns):
                    index = model.index(row, column)
                    # Get the data for the current cell
                    cell_data = model.data(index, Qt.DisplayRole)
                    row_data.append(cell_data)
                data.append(row_data)

            # Create pandas DataFrame
            df = pd.DataFrame(data, columns=headers)
            return df

        def df_to_polygon(df):
            # all_cells = np.ravel(df.to_numpy(), order='F').tolist()
            all_cells = df[['x', 'y']].values.tolist()
            coords_unique = [list(t) for t in dict.fromkeys(map(tuple, all_cells))]

            ring = [tuple(pt) for pt in coords_unique]
            return Polygon(ring)

        def update_original_dataframe(df_o, df_new):
            df2 = df_o.set_index(['conc', 'side', 'point_i'])
            repl2 = df_new.set_index(['conc', 'side', 'point_i'])

            # 2) restrict repl2 to just the columns you want to overwrite
            #    (here: 'x' and 'y')
            repl2 = repl2[['x', 'y']]

            # 3) update df2 in place
            df2.update(repl2)

            # 4) (optionally) drop the index back to columns
            df_new = df2.reset_index()
            return df_new

        def check_for_multipoint():
            all_pts = []
            if not isinstance(intersection_pt, MultiPoint):
                return intersection_pt
            elif intersection_pt == Point(0, 0):
                return intersection_pt_current
            else:
                for geom in intersection_pt.geoms:
                    # all_pts.append(geom)
                    if not geom.equals(intersection_pt_current):
                        return geom
                # return all_pts[1]

        def check_intersection_pts(intersection_result):
            if isinstance(intersection_result, MultiPoint):
                # Sort intersection points by their position along the LineString
                sorted_points = sorted(intersection_result.geoms,
                                       key=lambda pt: intersection_segment.project(pt))

                first_crossed_point = sorted_points[0]

            elif intersection_result.geom_type == "Point":
                first_crossed_point = intersection_result

            else:
                # Handle other unexpected cases (like no intersection, LineString, etc.)
                first_crossed_point = None
            return first_crossed_point

        def check_full_inter_pts(intersection_result, current_well_path_section, current_plat_coords):
            cardinal_direction = None
            if isinstance(intersection_result, MultiPoint):
                pts_1 = sorted(intersection_result.geoms,
                               key=lambda pt: intersection_segment.project(pt))
            elif intersection_result.geom_type == "Point":
                pts_1 = [intersection_result]
            else:
                pts_1 = []

            # Now get distances (normalized between 0 and 1)
            line_length = intersection_segment.length
            cut_distances = [0.0] + [intersection_segment.project(pt) / line_length for pt in pts_1] + [1.0]

            # Slice line into segments between cut distances
            segments = []
            for i in range(len(cut_distances) - 1):
                start_frac = cut_distances[i]
                end_frac = cut_distances[i + 1]
                seg = substring(intersection_segment, start_frac, end_frac, normalized=True)
                segments.append(seg)

            first_segment = segments[0]  # from earlier code
            first_coords_set = set(first_segment.coords)

            # 2. Create coordinate tuples from the DataFrame
            all_coords = list(
                zip(current_well_path_section['e_offset_delta'], current_well_path_section['n_offset_delta']))

            # 3. Filter OUT rows that are part of the first segment
            mask = [pt not in first_coords_set for pt in all_coords]
            everything_but_first = current_well_path_section[mask]

            # NEW CODE: Determine which boundary side the intersection passes through
            from shapely.geometry import LineString
            intersection_point = pts_1[0]

            for side in current_plat_coords['side'].unique():
                side_coords = current_plat_coords[current_plat_coords['side'] == side][['x', 'y']].values
                side_line = LineString(side_coords)
                if side_line.distance(intersection_point) < 1e-6:  # tolerance for floating point precision
                    cardinal_direction = side[0]
                    break
            dict_index = {'e': 2, 'w': 6, 'n': 0, 's': 4}
            return everything_but_first, pts_1[0], cardinal_direction, dict_index[cardinal_direction]

        def plot_shapely_and_dataframe(polygon, point, dataframe,
                                       title="Shapely Objects and DataFrame Visualization"):
            """
            Plot a shapely polygon, point, and pandas dataframe offset data.

            Args:
                polygon: Shapely Polygon object
                point: Shapely Point object
                dataframe: Pandas DataFrame with 'e_offset_delta' and 'n_offset_delta' columns
                title: Plot title
            """
            fig, ax = plt.subplots(figsize=(10, 8))

            # Plot polygon
            if polygon and not polygon.is_empty:
                x, y = polygon.exterior.xy
                ax.plot(x, y, 'b-', linewidth=2, label='Polygon Boundary')
                ax.fill(x, y, alpha=0.3, color='lightblue', label='Polygon Area')

            # Plot point
            if point and not point.is_empty:
                ax.scatter(point.x, point.y, color='red', s=100, marker='o',
                           label='Point', zorder=5, edgecolors='black')

            # Plot dataframe offset data
            if not dataframe.empty and 'e_offset_delta' in dataframe.columns and 'n_offset_delta' in dataframe.columns:
                ax.scatter(dataframe['e_offset_delta'], dataframe['n_offset_delta'],
                           color='green', alpha=0.7, s=50, marker='^',
                           label='Offset Data', zorder=4)

                # Add measured_depth labels if column exists
                if 'measured_depth' in dataframe.columns:
                    for idx, row in dataframe.iterrows():
                        ax.annotate(f"{row['measured_depth']:.1f}",
                                    (row['e_offset_delta'], row['n_offset_delta']),
                                    xytext=(5, 5), textcoords='offset points',
                                    fontsize=8, alpha=0.8, ha='left')

            # Formatting
            ax.set_xlabel('Easting / E-Offset')
            ax.set_ylabel('Northing / N-Offset')
            ax.set_title(title)
            ax.legend()
            ax.grid(True, alpha=0.3)
            ax.set_aspect('equal', adjustable='box')

            plt.tight_layout()
            plt.show()

        well_paths_lst = [k for k, v in self.well_path_dict.items()]
        all_plats_df = original_all_plats_df
        # well_path = self.well_path_dict[i].clearance_data
        result_coords = current_plat_coords[['x', 'y', 'side']].values.tolist()
        starter_pt = get_starter_pt(well_path.iloc[0], result_coords)
        starter_utm = well_path.iloc[0][['easting', 'northing']].values.tolist()
        dx_start, dy_start = (float(well_path['easting'].iloc[0])) - starter_pt[0] * 0.3048, (
            float(well_path['northing'].iloc[0])) - starter_pt[1] * 0.3048
        well_path[['e_offset_delta', 'n_offset_delta']] = (well_path.apply(
            lambda row: get_offset_added_delta(starter_pt[0], starter_pt[1], row['e_offset'], row['n_offset']), axis=1,
            result_type='expand'))
        well_path['rel_data_order'] = 99
        current_well_path_section = copy.deepcopy(well_path)
        current_plat_coords_modified = [i[:2] for i in result_coords]
        current_polygon = Polygon(current_plat_coords_modified)
        used_conc_sections = [current_plat_conc]
        counter = 2
        intersection_pt_current = Point(0, 0)
        while True:
            polygon_plat = current_polygon
            # pts = [Point(x, y) for x, y in zip(current_well_path_section.e_offset_delta, current_well_path_section.n_offset_delta)]
            intersection_segment = LineString(
                list(zip(current_well_path_section['e_offset_delta'], current_well_path_section['n_offset_delta'])))
            boundary = polygon_plat.exterior
            intersection_pt = intersection_segment.intersection(boundary)

            try:
                current_well_path_section, intersection_pt, dir_val, index = check_full_inter_pts(intersection_pt,
                                                                                                  current_well_path_section,
                                                                                                  current_plat_coords)
                intersection_pt_current = intersection_pt
            except KeyError:
                all_plats_df[['x_delta', 'y_delta']] = (
                    all_plats_df.apply(
                        lambda row: get_offset_added_delta(row['x'] * 0.3048, row['y'] * 0.3048, dx_start, dy_start),
                        axis=1,
                        result_type='expand'))
                self.graph_plats_and_well(all_plats_df, list(zip(well_path.easting, well_path.northing)), title)
                return all_plats_df

            next_plat_df = self.currently_used_plat_data[self.currently_used_plat_data['range'] == counter]
            try:
                next_plat_conc = next_plat_df['conc'].iloc[0]
                if next_plat_conc == [used_conc_sections[-1]]:
                    break
                if next_plat_conc not in used_conc_sections:
                    rewritten_coords = all_plats_df[all_plats_df['conc'] == next_plat_conc]
                else:
                    used_conc_sections.append(next_plat_conc)

                    next_plat_coords_dict = all_plats_df[all_plats_df['conc'] == next_plat_conc]

                    well_prox_boo = well_path_prox(intersection=intersection_pt_current,
                                                   side_dict_all=next_plat_coords_dict,
                                                   direction=dir_val)
                    rewritten_coords = self.coords_stitcher(next_plat_coords_dict,
                                                            all_plats_df[all_plats_df['conc'] == current_plat_conc],
                                                            dir_val, well_prox_boo)


            except IndexError as f:
                error_traceback = traceback.format_exc()
                print(f"Error details:\n{error_traceback}")

                break

            current_polygon = df_to_polygon(rewritten_coords)
            new_dict = pd.DataFrame(data=rewritten_coords.to_dict(orient='list'))
            try:
                all_plats_df = update_original_dataframe(all_plats_df, new_dict)
                counter += 1
                current_plat_conc = next_plat_conc
            except ValueError as e:
                print('broke here 3')
                all_plats_df[['x_delta', 'y_delta']] = (
                    all_plats_df.apply(
                        lambda row: get_offset_added_delta(row['x'] / 0.3048, row['y'] / 0.3048, starter_utm[0],
                                                           starter_utm[1]), axis=1,
                        result_type='expand'))
                return all_plats_df
        return pd.DataFrame()

    def run_plat_well_tracer(self, current_plat_coords, current_plat_conc, existing_data = False):

        def get_plat_coords():
            query = "select * from SectionPlatDataAGRC"
            return pd.read_sql(query, self.conn).drop_duplicates(keep="first")

        def retrieve_well_data():
            return [self.ui.dx_survey_north_ref_line.text(),
                    self.ui.dx_survey_mag_dec_line.text(),
                    self.ui.dx_survey_conv_angle_line.text(),
                    self.ui.dx_survey_pro_azi_line.text()]
            pass

        def parse_conc(conc_str: str) -> dict:
            """
            Reverses the concatenation process, parsing a string back into its
            Public Land Survey System (PLSS) components.

            Args:
                conc_str: A 9-character string (e.g., '0102N03WS').

            Returns:
                A dictionary containing the section, township, range, and direction codes.
            """
            # 1. Define the reverse translation map by inverting the original.
            # This maps letters like 'N' or 'W' back to their numeric codes.

            # 2. Slice the string into its component parts based on fixed positions.
            # Example: '0102N03WS'
            # sec: '01', ts: '02', ts_dir: 'N', rng: '03', rng_dir: 'W', baseline: 'S'
            sec_str = conc_str[0:2]
            ts_str = conc_str[2:4]
            ts_dir_char = conc_str[4:5]
            rng_str = conc_str[5:7]
            rng_dir_char = conc_str[7:8]
            baseline_char = conc_str[8:9]

            # 3. Translate and convert values back to their original format.
            # Convert number strings to integers.
            sec = int(sec_str)
            ts = int(ts_str)
            rng = int(rng_str)

            # Use the reverse map to get the direction codes.

            # 4. Return the components in a structured dictionary.
            return {
                'sec': sec,
                'ts': ts,
                'ts_dir': ts_dir_char,
                'rng': rng,
                'rng_dir': rng_dir_char,
                'baseline': baseline_char
            }

        all_pts_data = get_plat_coords()

        min_curv_data, known_conc_data, section_degrees_data, plat_north_refs_lst, shl_calc = mainTriangulator(
            conn=self.conn,
            tsr_data_df=self.tsr_data,
            data_plat_coords=current_plat_coords,
            df=all_pts_data,
            conc=current_plat_conc,
            survey_data_df=self.well_path_dict['pln_df_grid_dx'].clearance_data,
            well_parameter_data=retrieve_well_data(),
            ui=self.ui, existing_data = existing_data)

        data_lst = [[known_conc_data[i], Polygon(section_degrees_data[i])] for i in range(len(known_conc_data))]

        headers = ['Conc', 'geometry']
        gdf_data = pd.DataFrame(data=data_lst, columns=headers)

        gdf_data[['sec', 'ts', 'ts_dir', 'rng', 'rng_dir', 'baseline']] = gdf_data.apply(
            lambda x: parse_conc(x['Conc']),
            axis=1,
            result_type='expand'
        )

        return min_curv_data, gdf_data, known_conc_data, all_pts_data

    def coords_stitcher(self, next_coords_df, current_coords_df, direction, direction_boo):
        def get_point_indices():
            """
            Determines the correct starting and matched indices based on direction.

            Args:
                direction (str): The cardinal direction ("W", "N", "E", "S").
                direction_boo (bool): True to select the first index pair, False for the second.

            Returns:
                tuple: A tuple containing the (starting_point_index, matched_point_index).
            """
            # Consolidate all mappings into a single, clear dictionary.
            # Format: direction: ([start_indices], [matched_indices])
            # POINT_MAPPING = {
            #     "w": ([0, 4], [12, 8]),
            #     "n": ([4, 8], [16, 12]),
            #     "e": ([8, 12], [4, 0]),
            #     "s": ([12, 16], [8, 4]),
            # }
            POINT_MAPPING = {
                "w": ([0, 4], [14, 10]),
                "n": ([5, 9], [19, 15]),
                "e": ([10, 14], [4, 0]),
                "s": ([15, 19], [9, 5]),
            }
            lst_dict = {"0": [0, 4], "1": [4, 8], "2": [8, 12], "3": [12, 16]}
            matched_lst_dict = {"0": [12, 8], "1": [16, 12], "2": [4, 0], "3": [8, 4]}
            # Use a simple integer (0 or 1) to select from the lists.
            selector = 0 if direction_boo else 1

            # Directly look up the lists of options for the given direction.
            start_options, match_options = POINT_MAPPING[direction]

            # Select the specific index from each list and return the pair.
            return start_options[selector], match_options[selector]

        def calculate_diff_from_dfs():
            """
            Calculates the difference between two coordinates selected from DataFrames.

            The function translates legacy list-based indices into DataFrame locations
            to select the appropriate points for calculation.

            Args:
                current_coords_df (pd.DataFrame): DataFrame with 'west', 'north', 'east', 'south' columns.
                next_coords_df (pd.DataFrame): DataFrame with 'west', 'north', 'east', 'south' columns.
                starting_pts (int): The legacy index for the point in current_coords_df.
                matched_pt (int): The legacy index for the point in next_coords_df.

            Returns:
                tuple: A tuple containing the difference in x and y (diff_x, diff_y).
            """
            # Map for converting index to column name

            column_map = {0: 'west', 1: 'north', 2: 'east', 3: 'south'}

            # 1. Get location for the starting point in current_coords_df
            start_col = column_map[starting_pts // 5]

            start_row = (starting_pts % 5)

            current_point = \
                current_coords_df[
                    (current_coords_df['side'] == start_col) & (current_coords_df['point_i'] == start_row)][
                    ['x', 'y']].iloc[0].values.tolist()
            # current_point = current_coords_df.loc[start_row, start_col]
            # 2. Get location for the matched point in next_coords_df
            matched_col = column_map[matched_pt // 5]
            matched_row = matched_pt % 5

            next_point = \
                next_coords_df[(next_coords_df['side'] == matched_col) & (next_coords_df['point_i'] == matched_row)][
                    ['x', 'y']].iloc[0].values.tolist()
            # next_point = next_coords_df.loc[matched_row, matched_col]

            # 3. Perform the calculation
            diff_x_pt = current_point[0] - next_point[0]
            diff_y_pt = current_point[1] - next_point[1]

            return diff_x_pt, diff_y_pt

        def my_calc(x, y):
            return x + diff_x_used, y + diff_y_used

        def update_original_dataframe(df_o, df_new):
            dir_dict = {'n': ['north', 'south'],
                        's': ['south', 'north'],
                        'e': ['west', 'east'],
                        'w': ['east', 'west']}
            dir_lst = dir_dict[direction]
            north_coords = df_o[df_o['side'] == dir_lst[0]][['x', 'y']].iloc[::-1].reset_index(drop=True)
            south_indices = df_new[df_new['side'] == dir_lst[1]].index
            df_new.loc[south_indices, ['x', 'y']] = north_coords.values
            #
            # df2 = df_o.set_index(['conc', 'side', 'point_i'])
            # repl2 = df_new.set_index(['conc', 'side', 'point_i'])
            #
            # # 2) restrict repl2 to just the columns you want to overwrite
            # #    (here: 'x' and 'y')
            # repl2 = repl2[['x', 'y']]
            #
            # # 3) update df2 in place
            # df2.update(repl2)
            #
            # # 4) (optionally) drop the index back to columns
            # df_new = df2.reset_index()
            return df_new

        # to run this on every cell in every column:
        # result_df = df.applymap(my_calc)
        opp_direction_list = {"0": '2', "1": '3', "2": '0', "3": '1'}
        cols = ['south', 'east', 'north', 'west']
        # current_coords_df  = pd.DataFrame(data = current_plat_dict_out)
        # next_coords_df = pd.DataFrame(data = next_plat_dict_out)
        # next_coords_df_mod = copy.copy(next_coords_df)
        # current_coords_df_mod = copy.copy(current_coords_df)
        # idx_w0 = current_coords_df_mod.loc[(current_coords_df_mod.side == 'west') & (current_coords_df_mod.point_i == 0), :].index[0]
        # idx_sN = current_coords_df_mod.loc[current_coords_df_mod.side == 'south'].nlargest(1, 'point_i').index[0]
        # current_coords_df_mod.loc[0, ['x', 'y']] = current_coords_df_mod.loc[19, ['x', 'y']].values
        # current_coords_df_mod = current_coords_df_mod.apply(lambda row: round_row(row['x'], row['y']))
        # current_coords_df_mod['west'].iloc[0] = current_coords_df_mod['south'].iloc[4]
        # current_coords_df_mod.loc[0, 'west'] = current_coords_df_mod.loc[4, 'south']
        # current_coords_df_mod = current_coords_df.applymap(lambda pt:[round(pt[0],1), round(pt[1], 1)])
        # current_coords_df_zeroed = current_coords_df_mod.apply(lambda col: col.where(~col.map(tuple).duplicated(), other=np.nan))
        starting_pts, matched_pt = get_point_indices()
        diff_x_used, diff_y_used = calculate_diff_from_dfs()

        next_coords_df[['x', 'y']] = next_coords_df.apply(lambda row: my_calc(row['x'], row['y']), axis=1,
                                                          result_type='expand')
        next_coords_df = update_original_dataframe(current_coords_df, next_coords_df)

        # next_coords_df_mod = next_coords_df.applymap(my_calc)
        return next_coords_df

    def graph_plat_and_well(self, poly, well):
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

    def graph_plats_and_well(self, polygons, well, title):
        grouped = polygons.groupby("conc")
        fig, ax = plt.subplots()
        x = [point[0] for point in well]
        y = [point[1] for point in well]
        ax.plot(x, y, color='blue', linewidth=3)

        for i, k in grouped:
            x_coords_1 = k['x_delta'].values.tolist()
            y_coords_1 = k['y_delta'].values.tolist()
            ax.plot(x_coords_1, y_coords_1, color='red')
        ax.set_aspect('equal', 'box')
        plt.title(title)
        plt.show()
        pass

    def graph_plats_and_well2(self, polygons, well, title):
        # grouped = polygons.groupby("conc")
        fig, ax = plt.subplots()
        x = [point[0] for point in well]
        y = [point[1] for point in well]
        ax.plot(x, y, color='blue', linewidth=3)

        for poly in polygons:
            x_coords_1, y_coords_1 = poly.exterior.xy

            # x_coords_1 = k['x_delta'].values.tolist()
            # y_coords_1 = k['y_delta'].values.tolist()
            ax.plot(x_coords_1, y_coords_1, color='red')
        ax.set_aspect('equal', 'box')
        plt.title(title)
        plt.show()


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
