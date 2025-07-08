import copy
import itertools

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


def get_direction(val, xMin, xMax, yMin, yMax):
    if val[0] > xMax:
        return 'E', 2
    elif val[0] < xMin:
        return 'W', 6
    if val[1] > yMax:
        return 'N', 0
    elif val[1] < yMin:
        return 'S', 4
    return False


class SetupRelativeCoordsPage:
    def __init__(self, conn, ui):
        self._rel_models = {}
        self._rel_tbls = {}
        self.dict_plats_lines = {}
        self.dict_plats_pts = {}

        self.dict_figures = {}
        self.dict_canvas = {}
        self.dict_ax = {}
        self.conn = conn
        self.ui = ui
        self.currently_used_plat_data = pd.DataFrame()
        self.side_names = [
            "south_left_2", "south_left_1", "south_right_1", "south_right_2",
            "north_left_2", "north_left_1", "north_right_1", "north_right_2",
            "west_up_2", "west_up_1", "west_down_1", "west_down_2",
            "east_up_2", "east_up_1", "east_down_1", "east_down_2",
        ]
        # self.get_all_rel_wells2()
        self.setup_figs()
        all_rel_surveys = self.get_all_rel_wells()
        self.setup_combo_boxes(all_rel_surveys)

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
        # now sort by the full key:
        df_sorted = output.sort_values(
            by=[
                'baseline', 'section',
                'township_bearing', 'rng_bearing',
                'township', 'rng', 'version'],
            ascending=[True, True, True, True, True, True, True]
        ).reset_index(drop=True)
        output_labels = tuple(df_sorted['label'].unique())
        return output_labels

    def setup_combo_boxes(self, lst):
        for i in range(8):
            cb = getattr(self.ui, f"version_combo_rel_{i + 1}")
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(lst)

            cb.activated[int].connect(lambda idx, ver=i + 1, combo=cb: self.plat_combo_box_fill(ver, idx, combo))
            cb.blockSignals(False)

    def plat_combo_box_fill(self, version: int, index: int, combo: QComboBox):
        def fill_tsr_data():
            first_line = output.iloc[0]
            getattr(self.ui, f"section_input_rel_{version}").setText(str(first_line['section']))
            getattr(self.ui, f"township_input_rel_{version}").setText(str(first_line['township']))
            getattr(self.ui, f"township_dir_input_rel_{version}").setText(str(first_line['township_bearing_str']))
            getattr(self.ui, f"range_input_rel_{version}").setText(str(first_line['rng']))
            getattr(self.ui, f"range_dir_input_rel_{version}").setText(str(first_line['rng_bearing_str']))
            getattr(self.ui, f"meridian_input_rel_{version}").setText(str(first_line['baseline_str']))

        def fill_calls_models():
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
            # group your DataFrame by the 'side' field
            # for side_name, df_side in output.groupby("side"):
            #     # find the matching QTableView on your UI
            #     tbl: QTableView = getattr(self.ui,f"{side_name}_table_rel_{version}")
            #     self._rel_tbls[(side_name, version)] = tbl
            #     # build a fresh model
            #     model = QStandardItemModel(tbl)  # parent it to self!
            #     model.setColumnCount(len(cols))
            #     model.setHorizontalHeaderLabels(headers)
            #
            #     # fill rows
            #     for r, (_, row) in enumerate(df_side.iterrows()):
            #         for c, col in enumerate(cols):
            #             item = QStandardItem(str(row[col]))
            #             model.setItem(r, c, item)
            #
            #     # attach it
            #     tbl.setModel(model)
            #     # stash it so Python doesn’t GC it—and so you can update it later if needed
            #
            #     self._rel_models[(side_name, version)] = model
            #     # self._rel_tbls[(side_name, version)] = tbl

        def fill_calls_data():
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

        def data_frame_plat_builder():
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


        all_plats_dict = {}
        self.currently_used_plat_data = pd.DataFrame()

        cols = ["length", "degrees", "minutes", "seconds", "bearing_str"]
        current_label = combo.itemText(index)
        query = f"select * from tsr_plats_surveys where label = '{current_label}'"
        output = pd.read_sql(query, self.conn)
        fill_tsr_data()
        fill_calls_models()
        fill_calls_data()
        self.currently_used_plat_data = self.collect_relative_data()
        consecutive_codes, _ = pd.factorize(self.currently_used_plat_data['order'])
        self.currently_used_plat_data['range'] = consecutive_codes + 1
        initial_plat_conc = self.currently_used_plat_data[self.currently_used_plat_data['order'] == version]['conc'].iloc[0]

        grouped = self.currently_used_plat_data.groupby(['range'])


        all_conc_codes = []

        for x, df in grouped:
            plat_coords = convert_to_pts(df)
            conc = df['conc'].iloc[0]
            all_plats_dict[conc] = plat_coords
            all_conc_codes.append(conc)
        all_conc_codes = tuple(all_conc_codes)
        result = {
            key: {direction: [item[:2] for item in group] for direction, group in
                  itertools.groupby(value, key=lambda x: x[2])}
            for key, value in all_plats_dict.items()
        }
        # for key, value in all_plats_dict.items():
        # init_plat = convert_to_pts(init_plat_data)
        self.draw_plat_solo(all_plats_dict[initial_plat_conc], version)

        plat_df = data_frame_plat_builder()
        plat_df_conc = plat_df['conc'].unique()
        output_polygons = self.run_plat_well_tracer(current_plat_coords=plat_df[plat_df['conc']==plat_df_conc[0]],
                                                    current_plat_conc=plat_df_conc[0], all_plats_dict=plat_df)
        # print(output_polygons)
        # output_polygons = self.run_plat_well_tracer_4(current_plat_coords=result[all_conc_codes[0]], current_plat_conc=all_conc_codes[0], all_plats_dict=result)

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
        # dict_used = getattr(self, f"dict_{coord_type_label}")[version]
        canvas_used = getattr(self, f"dict_canvas")[version]
        ax_used = getattr(self, f"dict_ax")[version]
        # mp = getattr(self.ui, f"well_graphic_mp_individual_{version}")
        # object = getattr(self.ui, f"well_graphic_section_all_layout_8{version}")
        line_collection_used = self.dict_plats_lines[version]
        pts_collection_used = self.dict_plats_pts[version]
        x = [point[0] for point in plat]
        y = [point[1] for point in plat]

        pts_collection_used.set_offsets([i[:2] for i in plat])
        # x, y = np.array(dict_used.exterior.coords).T
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
        df['decimal_azimuth'] = df.apply(lambda row: decimal_converter(row['side'], row['degrees'], row['minutes'], row['seconds'], row['baseline_str']), axis=1)
        return df

    def get_all_rel_wells2(self):
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

        def transform_bearings(val, label):
            if label == 'township':
                return val[4]
            if label == 'range':
                return val[7]
            if label == 'baseline':
                return val[8]
            if label == 'bearing':
                val = str(val)
                if val == '1':
                    return 'SE'
                elif val == '2':
                    return 'NE'
                elif val == '3':
                    return 'SW'
                else:
                    return 'NW'

        def transform_and_correct_side(side):
            side = side.lower()
            side = side.replace("-", "_")
            # side_val =  side[-1]
            side = side.replace(side[-1], f"_{side[-1]}")
            return side

        def transform_string(s, v, all):
            part1 = s[:2]
            part2 = s[2:4] + s[4]
            part3 = s[5:7] + s[7]
            part4 = s[-1]

            return f"{part1} {part2} {part3} {part4} - {v}"

        query = f"select * from section_plat_data"
        output = pd.read_sql(query, self.conn)
        output.sort_values(['Baseline', 'Township Direction', 'Range Direction', 'Township', 'Range', 'Section',
                            'Version']).reset_index(drop=True)
        output['conc'] = output.apply(
            lambda row: convert_conc(row['Section'], row['Township'], row['Township Direction'],
                                     row['Range'],
                                     row['Range Direction'], row['Baseline']), axis=1)
        output['label'] = output.apply(lambda x: transform_string(x['conc'], x['Version'], x[
            ['Baseline', 'Township Direction', 'Range Direction', 'Township', 'Range', 'Section']]), axis=1)
        output = output.rename(
            columns={
                'Section': 'section',
                'Township': 'township',
                'Township Direction': 'township_bearing',
                'Range': 'rng',
                'Range Direction': 'rng_bearing',
                'Baseline': 'baseline',
                'Side': 'side',
                'Length': 'length',
                'Degrees': 'degrees',
                'Minutes': 'minutes',
                'Seconds': 'seconds',
                'Alignment': 'bearing',
                'North Reference': 'north_ref',
                'Version': 'version'
            }
        )
        output['township_bearing_str'] = output.apply(lambda x: transform_bearings(val=x['conc'], label='township'),
                                                      axis=1)
        output['rng_bearing_str'] = output.apply(lambda x: transform_bearings(val=x['conc'], label='range'), axis=1)
        output['baseline_str'] = output.apply(lambda x: transform_bearings(val=x['conc'], label='baseline'), axis=1)
        output['bearing_str'] = output.apply(lambda x: transform_bearings(val=x['bearing'], label='bearing'), axis=1)
        output.drop(columns=['new_code', 'index'], inplace=True)
        new_order = ['section', 'township', 'township_bearing', 'township_bearing_str',
                     'rng', 'rng_bearing', 'rng_bearing_str', 'baseline', 'baseline_str', 'side',
                     'length', 'degrees', 'minutes', 'seconds', 'bearing', 'bearing_str', 'decimal_azimuth',
                     'north_ref', 'version', 'conc',
                     'label']

        output = output[new_order]
        output['side'] = output.apply(lambda x: transform_and_correct_side(x['side']), axis=1)
        output = output.astype({"section": float, "township": float, "township_bearing": float, "rng": float,
                                "rng_bearing": float, "baseline": float, "length": float, "degrees": float,
                                "minutes": float, "seconds": float, "bearing": float, "decimal_azimuth": float})
        output = output.astype({"section": int, "township": int, "township_bearing": int, "rng": int,
                                "rng_bearing": int, "baseline": int, "degrees": int,
                                "minutes": int, "bearing": int})

        output.to_sql('tsr_plats_surveys', self.conn, index=False, if_exists='replace')

    def plot_intersection(self, poly: Polygon, line: LineString, *, figsize=(6, 6),
                          poly_kwargs=None, line_kwargs=None, inter_kwargs=None):
        """
        Plots a Polygon and a LineString (or similar), plus their intersection.

        Parameters
        ----------
        poly : shapely.geometry.Polygon
            The polygon to plot.
        line : shapely.geometry.LineString
            The line (or multilinestring) to plot.
        figsize : tuple, optional
            Figure size passed to plt.subplots.
        poly_kwargs : dict, optional
            Styling passed to ax.fill for the polygon.
        line_kwargs : dict, optional
            Styling passed to ax.plot for the line.
        inter_kwargs : dict, optional
            Styling passed to ax.plot for the intersection geometry.
        """
        # default styles
        poly_kwargs = poly_kwargs or dict(alpha=0.3, fc='lightblue', ec='navy', label='Polygon')
        line_kwargs = line_kwargs or dict(color='gray', linewidth=2, linestyle='--', label='Line')
        inter_kwargs = inter_kwargs or dict(color='red', linewidth=3, label='Intersection')

        def _plot_geom(g: BaseGeometry, **kw):
            """Recursively plot any Shapely geometry."""
            t = g.geom_type
            if t == 'Point':
                plt.plot(g.x, g.y, marker='o', **kw)
            elif t in ('LineString', 'LinearRing'):
                x, y = g.xy
                plt.plot(x, y, **kw)
            elif t.startswith('Multi') or t == 'GeometryCollection':
                for part in g.geoms:
                    _plot_geom(part, **kw)
            else:
                raise ValueError(f"Unsupported geometry type: {t!r}")

        # compute intersection
        inter = poly.intersection(line)

        # build plot
        fig, ax = plt.subplots(figsize=figsize)

        # polygon (fill)
        x_poly, y_poly = poly.exterior.xy
        ax.fill(x_poly, y_poly, **poly_kwargs)

        # line
        _plot_geom(line, **line_kwargs)

        # intersection
        _plot_geom(inter, **inter_kwargs)

        # finalize
        ax.set_aspect('equal', 'box')
        ax.legend(loc='best')
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_title('Polygon × LineString Intersection')
        plt.show()
    def run_plat_well_tracer_4(self, current_plat_coords, current_plat_conc, all_plats_dict):
        def well_path_prox(intersection, side_dict_all, direction, tol=1e-8):
            pt = intersection if isinstance(intersection, Point) else Point(intersection)

            # pick just the one side
            side_key = direction.lower()
            if side_key == 'n':
                coords = side_dict_all['north']
            elif side_key == 's':
                coords = side_dict_all['south']
            elif side_key == 'e':
                coords = side_dict_all['east']
            elif side_key == 'w':
                coords = side_dict_all['west']
            else:
                raise KeyError(f"Direction must be one of 'n','s','e','w', not {direction!r}")

            # the “start” and “end” of that side’s line
            p_start = Point(coords[0])  # corner A
            p_end = Point(coords[-1])  # corner B

            # whichever corner is nearer the intersection…
            return pt.distance(p_start) < pt.distance(p_end)
        def well_path_prox2(coordinates, inside_pts, direction):
            side_bounds = Polygon(coordinates).bounds
            north_bound, south_bound, east_bound, west_bound = side_bounds[3], side_bounds[1], side_bounds[2], side_bounds[0]
            inside_pt_ns, inside_pt_ew = inside_pts[-1][1], inside_pts[-1][0]
            n_diff, s_diff = abs(north_bound - inside_pt_ns), abs(south_bound - inside_pt_ns)
            e_diff, w_diff = abs(east_bound - inside_pt_ew), abs(west_bound - inside_pt_ew)
            ns_diffs, ew_diffs = [n_diff, s_diff], [e_diff, w_diff]

            if direction.lower() in ['n', 's']:
                ew_prox, minDiff = min(enumerate(ew_diffs), key=operator.itemgetter(1))
                if ew_prox == 0:
                    side_prox = False
                    # side_prox = True
                elif ew_prox == 1:
                    side_prox = True
                    # side_prox = False
                return side_prox
            elif direction.lower() in ['e', 'w']:
                ns_prox, minDiff = min(enumerate(ns_diffs), key=operator.itemgetter(1))
                if ns_prox == 1:
                    side_prox = False
                    # side_prox = True
                elif ns_prox == 0:
                    side_prox = True
                    # side_prox = False
                return side_prox
        def find_crossing_segments(boundary, well_path):
            for i in range(len(coords) - 1):
                seg = LineString([coords[i], coords[i + 1]])
                if seg.intersects(boundary):
                    inter = seg.intersection(boundary)
                    # normalize to a list of Points for consistency
                    if isinstance(inter, Point):
                        pts = [inter]
                    else:
                        pts = list(inter.geoms) if hasattr(inter, 'geoms') else []
                    crossings.append((i, seg, pts))

            return crossings
        def get_offset_added_delta(dx, dy):
            return starter_pt[0] + float(dx) * 0.3048, starter_pt[1] + float(dy) * 0.3048
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
            all_cells = np.ravel(df.to_numpy(), order='F').tolist()
            coords_unique = [list(t) for t in dict.fromkeys(map(tuple, all_cells))]
            ring = [tuple(pt) for pt in coords_unique]
            return Polygon(ring)


        well_path = get_dataframe_from_qtableview()
        result_coords = [item[:2] + [k] for k, v in current_plat_coords.items() for item in v]
        starter_pt = get_starter_pt(well_path.iloc[0], result_coords)
        dx_start, dy_start = (float(well_path['easting'].iloc[0]) /0.3048) - starter_pt[0], (float(well_path['northing'].iloc[0]) /0.3048) - starter_pt[1]

        well_path[['e_offset_delta', 'n_offset_delta']] = (well_path.apply(lambda row: get_offset_added_delta(row['e_offset'], row['n_offset']), axis=1, result_type='expand'))
        well_path['rel_data_order'] = 99
        current_plat_coords_modified = [i[:2] for i in result_coords]
        current_polygon = Polygon(current_plat_coords_modified)
        xMin, xMax, yMin, yMax = current_polygon.bounds

        counter = 2

        intersection_segment = LineString(list(zip(well_path['e_offset_delta'], well_path['n_offset_delta'])))
        while True:
            polygon_plat = current_polygon
            pts = [Point(x, y) for x, y in zip(well_path.e_offset_delta, well_path.n_offset_delta)]
            mask = [polygon_plat.contains(pt) for pt in pts]
            well_path.loc[mask, 'rel_data_order'] = counter-1
            boundary = polygon_plat.exterior
            intersection_pt = intersection_segment.intersection(boundary)
            try:
                dir_val, index = get_direction((intersection_pt.x, intersection_pt.y), xMin, xMax, yMin, yMax)
            except AttributeError:
                return all_plats_dict
            next_plat_df = self.currently_used_plat_data[self.currently_used_plat_data['range'] == counter]
            try:
                next_plat_conc = next_plat_df['conc'].iloc[0]
            except IndexError:
                break
            next_plat_coords_dict = all_plats_dict[next_plat_conc]
            next_plat_coords = [tuple(item) for k, v in next_plat_coords_dict.items() for item in v]
            well_prox_boo = well_path_prox(intersection = intersection_pt, side_dict_all=next_plat_coords_dict, direction=dir_val)
            rewritten_coords = self.coords_stitcher_2(all_plats_dict[next_plat_conc], all_plats_dict[current_plat_conc], dir_val, well_prox_boo)
            current_polygon = df_to_polygon(rewritten_coords)
            new_dict = rewritten_coords.to_dict(orient='list')
            all_plats_dict[next_plat_conc] = new_dict
            counter += 1
            # current_plat_coords_modified = next_plat_coords
            current_plat_conc = next_plat_conc

        # for x, row in well_path.iterrows():
        #     polygon_plat = Polygon(current_plat_coords_modified)
        #
        #     boundary = polygon_plat.exterior
        #     delta_x, delta_y = float(row['delta_x']) * 0.3048, float(row['delta_y']) * 0.3048
        #     used_pt = [used_pt[0] + delta_x, used_pt[1] + delta_y]
        #     dir_val, index = get_direction(used_pt, xMin, xMax, yMin, yMax)
        #     intersection_pt = intersection_segment.intersection(boundary)
        #     self.plot_intersection(polygon_plat, intersection_segment)
        #
        #     if polygon_plat.contains(Point(used_pt)):
        #         well_path.at[x, 'rel_plat_conc'] = current_plat_conc
        #     else:
        #         try:
        #             intersection_pt = intersection_segment.intersection(boundary)
        #             self.plot_intersection(polygon_plat, intersection_segment)
        #             next_plat_df = self.currently_used_plat_data[self.currently_used_plat_data['range'] == counter]
        #
        #             next_plat_conc = next_plat_df['conc'].iloc[0]
        #             next_plat_coords = all_plats_dict[next_plat_conc]
        #             self.stitcher_process(next_plat_df, current_plat_df, next_plat_coords, current_plat_coords, next_plat_conc, dir_val)
        #             counter += 1
        #         except IndexError as e:
        #             pass
            # for i in used_plats:
            #     used_poly = all_plats_dict[i]
            #     if Polygon(used_poly).contains(Point(used_pt)):
            #         well_path.at[x, 'rel_plat_conc'] = conc
            #     else:
            #         pass
            # for k, v in all_plats_dict.items():
            #     if Polygon(v).contains(Point(used_pt)):
            #         well_path.at[x, 'rel_plat_conc'] = conc
            #     else:
            #
            #         pass

    def run_plat_well_tracer(self, current_plat_coords, current_plat_conc, all_plats_dict):
        def get_direction_sides():
            # print(intersection_pt)
            used_df = all_plats_dict[all_plats_dict['conc'] == current_plat_conc]
            # print(used_df)
            grouped_df = used_df.groupby('side')
            dict_index = {'e':2, 'w':6, 'n':0, 's': 4}
            # for r, group_df in grouped_df:
            #     line_string_side = Polygon(group_df[['x','y']].values.tolist())
            #     on_line3 = intersection_pt.within(line_string_side.buffer(1e-8))
            #     # if on_line3:

            for r, group_df in grouped_df:
                line_string_side = Polygon(group_df[['x','y']].values.tolist())
                on_line3 = intersection_pt.within(line_string_side.buffer(1e-8))
                if on_line3:
                    return r[0], dict_index[r[0]]

        def well_path_prox(intersection, side_dict_all, direction, tol=1e-8):
            pt = intersection if isinstance(intersection, Point) else Point(intersection)

            # pick just the one side
            side_key = direction.lower()
            if side_key == 'n':
                # coords = side_dict_all['north']
                coords = side_dict_all[side_dict_all['side']=='north'][['x', 'y']].values.tolist()
            elif side_key == 's':
                # coords = side_dict_all['south']
                coords = side_dict_all[side_dict_all['side']=='south'][['x', 'y']].values.tolist()

            elif side_key == 'e':
                # coords = side_dict_all['east']
                coords = side_dict_all[side_dict_all['side']=='east'][['x', 'y']].values.tolist()

            elif side_key == 'w':
                # coords = side_dict_all['west']
                coords = side_dict_all[side_dict_all['side']=='west'][['x', 'y']].values.tolist()

            else:
                raise KeyError(f"Direction must be one of 'n','s','e','w', not {direction!r}")

            # the “start” and “end” of that side’s line
            p_start = Point(coords[0])  # corner A
            p_end = Point(coords[-1])  # corner B

            # whichever corner is nearer the intersection…
            return pt.distance(p_start) < pt.distance(p_end)
        def well_path_prox2(coordinates, inside_pts, direction):
            side_bounds = Polygon(coordinates).bounds
            north_bound, south_bound, east_bound, west_bound = side_bounds[3], side_bounds[1], side_bounds[2], side_bounds[0]
            inside_pt_ns, inside_pt_ew = inside_pts[-1][1], inside_pts[-1][0]
            n_diff, s_diff = abs(north_bound - inside_pt_ns), abs(south_bound - inside_pt_ns)
            e_diff, w_diff = abs(east_bound - inside_pt_ew), abs(west_bound - inside_pt_ew)
            ns_diffs, ew_diffs = [n_diff, s_diff], [e_diff, w_diff]

            if direction.lower() in ['n', 's']:
                ew_prox, minDiff = min(enumerate(ew_diffs), key=operator.itemgetter(1))
                if ew_prox == 0:
                    side_prox = False
                    # side_prox = True
                elif ew_prox == 1:
                    side_prox = True
                    # side_prox = False
                return side_prox
            elif direction.lower() in ['e', 'w']:
                ns_prox, minDiff = min(enumerate(ns_diffs), key=operator.itemgetter(1))
                if ns_prox == 1:
                    side_prox = False
                    # side_prox = True
                elif ns_prox == 0:
                    side_prox = True
                    # side_prox = False
                return side_prox
        def find_crossing_segments(boundary, well_path):
            for i in range(len(coords) - 1):
                seg = LineString([coords[i], coords[i + 1]])
                if seg.intersects(boundary):
                    inter = seg.intersection(boundary)
                    # normalize to a list of Points for consistency
                    if isinstance(inter, Point):
                        pts = [inter]
                    else:
                        pts = list(inter.geoms) if hasattr(inter, 'geoms') else []
                    crossings.append((i, seg, pts))

            return crossings
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
            # print('prev point', intersection_pt_current)
            # print('new point', intersection_pt)
            all_pts = []
            if not isinstance(intersection_pt, MultiPoint):
                return intersection_pt
            elif intersection_pt == Point(0,0):
                return intersection_pt_current
            else:
                for geom in intersection_pt.geoms:
                    all_pts.append(geom)
                    # if geom.equals(intersection_pt_current):
                    #     print('unique point', geom)
                    #     return geom
                return all_pts[1]


        well_path = get_dataframe_from_qtableview()
        result_coords = current_plat_coords[['x', 'y', 'side']].values.tolist()
        # result_coords = [item[:2] + [k] for k, v in current_plat_coords.items() for item in v]
        starter_pt = get_starter_pt(well_path.iloc[0], result_coords)
        dx_start, dy_start = (float(well_path['easting'].iloc[0]) /0.3048) - starter_pt[0], (float(well_path['northing'].iloc[0]) /0.3048) - starter_pt[1]
        well_path[['e_offset_delta', 'n_offset_delta']] = (well_path.apply(lambda row: get_offset_added_delta(starter_pt[0], starter_pt[1], row['e_offset'], row['n_offset']), axis=1, result_type='expand'))
        well_path['rel_data_order'] = 99
        current_plat_coords_modified = [i[:2] for i in result_coords]
        current_polygon = Polygon(current_plat_coords_modified)
        xMin, xMax, yMin, yMax = current_polygon.bounds

        counter = 2
        intersection_segment = LineString(list(zip(well_path['e_offset_delta'], well_path['n_offset_delta'])))
        # print(well_path)
        intersection_pt_current = Point(0,0)
        while True:
            polygon_plat = current_polygon
            pts = [Point(x, y) for x, y in zip(well_path.e_offset_delta, well_path.n_offset_delta)]
            mask = [polygon_plat.contains(pt) for pt in pts]
            well_path.loc[mask, 'rel_data_order'] = counter-1
            # self.graph_plat_and_well(polygon_plat, list(zip(well_path.e_offset_delta, well_path.n_offset_delta)))

            boundary = polygon_plat.exterior
            intersection_pt = intersection_segment.intersection(boundary)
            intersection_pt = check_for_multipoint()
            intersection_pt_current = intersection_pt
            try:
                dir_val, index = get_direction_sides()
                rel_data = well_path['rel_data_order'].unique()
                self.graph_plats_and_well(all_plats_dict, list(zip(well_path.e_offset_delta, well_path.n_offset_delta)))
                # print(all_plats_dict)
                # print(well_path[well_path['rel_data_order']==99])
                # print(rel_data)
                # # if 99 not in rel_data:
                # #     print('99 is gone')
            except AttributeError:
                all_plats_dict[['x_delta', 'y_delta']] = (
                    all_plats_dict.apply(lambda row: get_offset_added_delta(row['x'], row['y'], dx_start, dy_start), axis=1,
                                          result_type='expand'))

                return all_plats_dict
            next_plat_df = self.currently_used_plat_data[self.currently_used_plat_data['range'] == counter]
            try:
                next_plat_conc = next_plat_df['conc'].iloc[0]
            except IndexError:
                break
            next_plat_coords_dict = all_plats_dict[all_plats_dict['conc']==next_plat_conc]

            well_prox_boo = well_path_prox(intersection = intersection_pt, side_dict_all=next_plat_coords_dict, direction=dir_val)
            rewritten_coords = self.coords_stitcher(next_plat_coords_dict, all_plats_dict[all_plats_dict['conc']==current_plat_conc], dir_val, well_prox_boo)
            current_polygon = df_to_polygon(rewritten_coords)
            new_dict = pd.DataFrame(data= rewritten_coords.to_dict(orient='list'))

            try:
                all_plats_dict = update_original_dataframe(all_plats_dict,new_dict)
                counter += 1
                current_plat_conc = next_plat_conc
            except ValueError as e:
                all_plats_dict[['x_delta', 'y_delta']] = (
                    all_plats_dict.apply(lambda row: get_offset_added_delta(row['x'], row['y'], dx_start, dy_start), axis=1,
                                          result_type='expand'))
                return all_plats_dict

        # for x, row in well_path.iterrows():
        #     polygon_plat = Polygon(current_plat_coords_modified)
        #
        #     boundary = polygon_plat.exterior
        #     delta_x, delta_y = float(row['delta_x']) * 0.3048, float(row['delta_y']) * 0.3048
        #     used_pt = [used_pt[0] + delta_x, used_pt[1] + delta_y]
        #     dir_val, index = get_direction(used_pt, xMin, xMax, yMin, yMax)
        #     intersection_pt = intersection_segment.intersection(boundary)
        #     self.plot_intersection(polygon_plat, intersection_segment)
        #
        #     if polygon_plat.contains(Point(used_pt)):
        #         well_path.at[x, 'rel_plat_conc'] = current_plat_conc
        #     else:
        #         try:
        #             intersection_pt = intersection_segment.intersection(boundary)
        #             self.plot_intersection(polygon_plat, intersection_segment)
        #             next_plat_df = self.currently_used_plat_data[self.currently_used_plat_data['range'] == counter]
        #
        #             next_plat_conc = next_plat_df['conc'].iloc[0]
        #             next_plat_coords = all_plats_dict[next_plat_conc]
        #             self.stitcher_process(next_plat_df, current_plat_df, next_plat_coords, current_plat_coords, next_plat_conc, dir_val)
        #             counter += 1
        #         except IndexError as e:
        #             pass
            # for i in used_plats:
            #     used_poly = all_plats_dict[i]
            #     if Polygon(used_poly).contains(Point(used_pt)):
            #         well_path.at[x, 'rel_plat_conc'] = conc
            #     else:
            #         pass
            # for k, v in all_plats_dict.items():
            #     if Polygon(v).contains(Point(used_pt)):
            #         well_path.at[x, 'rel_plat_conc'] = conc
            #     else:
            #
            #         pass

    def extract_coords_and_add_direction(self, used_dict):
        new_lst = [[i + [k] for i in v] for k, v in used_dict.items()]

        return new_lst

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
            # print('new', direction, direction_boo)
            # print('new', start_options, match_options)
            # print(start_options, match_options)
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
            # print('start', start_col)
            # print(start_row)
            # print(current_coords_df)
            current_point = current_coords_df[(current_coords_df['side'] == start_col) & (current_coords_df['point_i'] == start_row)][['x', 'y']].iloc[0].values.tolist()
            # print(current_point)
            # current_point = current_coords_df.loc[start_row, start_col]
            # 2. Get location for the matched point in next_coords_df
            matched_col = column_map[matched_pt // 5]
            matched_row = matched_pt % 5
            # print('start', matched_col)
            # print(matched_row)
            next_point = next_coords_df[(next_coords_df['side'] == matched_col) & (next_coords_df['point_i'] == matched_row)][['x', 'y']].iloc[0].values.tolist()
            # print(next_point)
            # next_point = next_coords_df.loc[matched_row, matched_col]

            # 3. Perform the calculation
            diff_x_pt = current_point[0] - next_point[0]
            diff_y_pt = current_point[1] - next_point[1]

            return diff_x_pt, diff_y_pt

        def my_calc(x,y):
            return x + diff_x_used, y + diff_y_used

        def update_original_dataframe(df_o, df_new):
            dir_dict = {'n':['north', 'south'],
                        's':['south', 'north'],
                        'e':['west','east'],
                        'w':['east','west']}
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
        print(starting_pts, matched_pt)
        diff_x_used, diff_y_used = calculate_diff_from_dfs()

        next_coords_df[['x', 'y']] = next_coords_df.apply(lambda row: my_calc(row['x'], row['y']), axis=1, result_type='expand')
        # output = update_original_dataframe(current_coords_df, next_coords_df)


        print(current_coords_df)
        print(next_coords_df)
        # next_coords_df_mod = next_coords_df.applymap(my_calc)
        return next_coords_df
        # new_coords_test_organized = [[j[:2] for j in i] for i in new_coords_test_organized]
        # next_coords_df_mod = next_coords_df_mod.applymap(lambda pt:[round(pt[0],1), round(pt[1], 1)])
        # next_coords_df_mod_zeroed = next_coords_df_mod.apply(lambda col: col.where(~col.map(tuple).duplicated(), other=np.nan))

        # new_coords_test_organized = [[[round(k, 1) for k in j] for j in i] for i in new_coords_test_organized]
        # new_coords_test_organized = [ModuleAgnostic.findUniqueListsInListOfLists(i) for i in next_coords_df_mod_zeroed]
        # new_coords_test_organized[int(opp_direction_list[str(direction)])] = old_data_organized[int(direction)][::-1]

        # next_coords_df_mod= next_coords_df_mod.apply(lambda col: ))

        # diff_x, diff_y = last_coords[starting_pts][0] - new_coords[matched_pt][0], last_coords[starting_pts][1] - new_coords[matched_pt][1]

        # corners = [current_plat_df['south'].iloc[-1], current_plat_df['east'].iloc[-1], current_plat_df['north'].iloc[-1], current_plat_df['west'].iloc[-1]]
        # current_plat_df = current_plat_df.apply(lambda col: col.where(~col.map(tuple).duplicated(),other=[[None, None]] * len(col)))
        # current_plat_df = current_plat_df.apply(lambda col: col.map(
        #     (lambda seen=set(): lambda pt: pt if (tuple(pt) not in seen and not seen.add(tuple(pt))) else [None,
        #                                                                                                    None])()
        # ))

        # next_plat_lst = self.extract_coords_and_add_direction(next_plat_dict_out)
        # current_plat_lst = self.extract_coords_and_add_direction(current_plat_dict_out)
        # current_plat_lst[0][0] = current_plat_lst[-1][-1]
        # current_plat_lst_organized = [[j[:2] for j in i] for i in current_plat_lst]
        # current_plat_lst_organized = [[[round(k, 1) for k in j] for j in i] for i in current_plat_lst_organized]
        # current_plat_lst_organized = [unique_lists(i) for i in current_plat_lst_organized]
        # corners = [current_plat_dict_out['south'][-1], current_plat_dict_out['east'][-1], current_plat_dict_out['north'][-1], current_plat_dict_out['west'][-1]]

    def coords_stitcher_3(self, next_plat_dict_out, current_plat_dict_out, direction, direction_boo):

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
            #     "W": ([0, 4], [12, 8]),
            #     "N": ([4, 8], [16, 12]),
            #     "E": ([8, 12], [4, 0]),
            #     "S": ([12, 16], [8, 4]),
            # }
            POINT_MAPPING = {
                "W": ([0, 4], [14, 10]),
                "N": ([5, 9], [19, 15]),
                "E": ([10, 14], [4, 0]),
                "S": ([15, 19], [9, 5]),
            }
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
            start_row = starting_pts % 5
            current_point = current_coords_df.loc[start_row, start_col]

            # 2. Get location for the matched point in next_coords_df
            matched_col = column_map[matched_pt // 5]
            matched_row = matched_pt % 5
            next_point = next_coords_df.loc[matched_row, matched_col]

            # 3. Perform the calculation
            diff_x_pt = current_point[0] - next_point[0]
            diff_y_pt = current_point[1] - next_point[1]

            return diff_x_pt, diff_y_pt

        def my_calc(pt):
            x, y = pt
            return [x + diff_x, y + diff_y]

        # to run this on every cell in every column:
        # result_df = df.applymap(my_calc)
        opp_direction_list = {"0": '2', "1": '3', "2": '0', "3": '1'}
        cols = ['south', 'east', 'north', 'west']
        current_coords_df  = pd.DataFrame(data = current_plat_dict_out)
        next_coords_df = pd.DataFrame(data = next_plat_dict_out)
        # next_coords_df_mod = copy.copy(next_coords_df)
        current_coords_df_mod = copy.copy(current_coords_df)
        current_coords_df_mod.loc[0, 'west'] = current_coords_df_mod.loc[4, 'south']
        current_coords_df_mod = current_coords_df.applymap(lambda pt:[round(pt[0],1), round(pt[1], 1)])
        current_coords_df_zeroed = current_coords_df_mod.apply(lambda col: col.where(~col.map(tuple).duplicated(), other=np.nan))
        starting_pts, matched_pt = get_point_indices()
        diff_x, diff_y = calculate_diff_from_dfs()
        next_coords_df_mod = next_coords_df.applymap(my_calc)
        return next_coords_df_mod
        # new_coords_test_organized = [[j[:2] for j in i] for i in new_coords_test_organized]
        # next_coords_df_mod = next_coords_df_mod.applymap(lambda pt:[round(pt[0],1), round(pt[1], 1)])
        # next_coords_df_mod_zeroed = next_coords_df_mod.apply(lambda col: col.where(~col.map(tuple).duplicated(), other=np.nan))

        # new_coords_test_organized = [[[round(k, 1) for k in j] for j in i] for i in new_coords_test_organized]
        # new_coords_test_organized = [ModuleAgnostic.findUniqueListsInListOfLists(i) for i in next_coords_df_mod_zeroed]
        # new_coords_test_organized[int(opp_direction_list[str(direction)])] = old_data_organized[int(direction)][::-1]

        # next_coords_df_mod= next_coords_df_mod.apply(lambda col: ))

        # diff_x, diff_y = last_coords[starting_pts][0] - new_coords[matched_pt][0], last_coords[starting_pts][1] - new_coords[matched_pt][1]

        # corners = [current_plat_df['south'].iloc[-1], current_plat_df['east'].iloc[-1], current_plat_df['north'].iloc[-1], current_plat_df['west'].iloc[-1]]
        # current_plat_df = current_plat_df.apply(lambda col: col.where(~col.map(tuple).duplicated(),other=[[None, None]] * len(col)))
        # current_plat_df = current_plat_df.apply(lambda col: col.map(
        #     (lambda seen=set(): lambda pt: pt if (tuple(pt) not in seen and not seen.add(tuple(pt))) else [None,
        #                                                                                                    None])()
        # ))

        # next_plat_lst = self.extract_coords_and_add_direction(next_plat_dict_out)
        # current_plat_lst = self.extract_coords_and_add_direction(current_plat_dict_out)
        # current_plat_lst[0][0] = current_plat_lst[-1][-1]
        # current_plat_lst_organized = [[j[:2] for j in i] for i in current_plat_lst]
        # current_plat_lst_organized = [[[round(k, 1) for k in j] for j in i] for i in current_plat_lst_organized]
        # current_plat_lst_organized = [unique_lists(i) for i in current_plat_lst_organized]
        # corners = [current_plat_dict_out['south'][-1], current_plat_dict_out['east'][-1], current_plat_dict_out['north'][-1], current_plat_dict_out['west'][-1]]


    def coords_stitcher_2(self, new_coords, last_coords, direction, direction_boo):

        new_coords = [list(i) for i in new_coords]
        directions_dict = {"W": '0', "N": '1', "E": "2", "S": "3"}
        direction = directions_dict[direction]
        # test_corners, old_data_organized = ModuleAgnostic.cornerGeneratorProcess(last_coords)

        # old_data_organized = [[j[:2] for j in i] for i in old_data_organized]
        # old_data_organized = [[[round(k, 1) for k in j] for j in i] for i in old_data_organized]
        # old_data_organized = [ModuleAgnostic.findUniqueListsInListOfLists(i) for i in old_data_organized]

        lst_dict = {"0": [0, 4], "1": [4, 8], "2": [8, 12], "3": [12, 16]}
        matched_lst_dict = {"0": [12, 8], "1": [16, 12], "2": [4, 0], "3": [8, 4]}
        opp_direction_list = {"0": '2', "1": '3', "2": '0', "3": '1'}
        lst_dict_boo = {True: 0, False: 1}
        starting_pts = lst_dict[str(direction)][lst_dict_boo[direction_boo]]
        matched_pt = matched_lst_dict[str(direction)][lst_dict_boo[direction_boo]]

        new_coords = [list(i) for i in new_coords]
        diff_x, diff_y = last_coords[starting_pts][0] - new_coords[matched_pt][0], last_coords[starting_pts][1] - new_coords[matched_pt][1]

        new_coords_test = [[i[0] + diff_x, i[1] + diff_y] for i in new_coords]

        # test_corners, new_coords_test_organized = ModuleAgnostic.cornerGeneratorProcess(new_coords_test)
        # new_coords_test_organized = [[j[:2] for j in i] for i in new_coords_test_organized]
        # new_coords_test_organized = [[[round(k, 1) for k in j] for j in i] for i in new_coords_test_organized]
        # new_coords_test_organized = [ModuleAgnostic.findUniqueListsInListOfLists(i) for i in new_coords_test_organized]
        # new_coords_test_organized[int(opp_direction_list[str(direction)])] = old_data_organized[int(direction)][::-1]

        return new_coords_test
    def stitcher_process(self, next_plat_df, current_plat_df, next_plat_coords, current_plat_coords, next_plat_conc, dir_val):

        coords = [0] * 20
        if dir_val == "E":
            # aligned = self.glue_plat(
            #     orientation='east',
            #     current_plat_coords=current_plat_coords,
            #     next_plat_coords=next_plat_coords,
            #     do_scale=True  # or False if you know they are same size
            # )
            self.directionE(next_plat_df, next_plat_coords, current_plat_coords, next_plat_conc, dir_val)
            # return coords, valsLst

    # def glue_plat(self,
    #               orientation: str,
    #               current_plat_coords: dict,
    #               next_plat_coords: dict,
    #               do_scale: bool = True
    #               ) -> list[tuple[float, float]]:
    #     """Return a new_plat vertex list, rigidly‐transformed so that
    #        its 'join side' sits exactly on the specified side of the
    #        current plat, with no gap."""
    #     # map orientation → which sides to align
    #     new_plat = [tuple(item[:2]) for k, v in next_plat_coords.items() for item in v]
    #     old_plat = [tuple(item[:2]) for k, v in current_plat_coords.items() for item in v]
    #     side_map = {
    #         'north': ('north', 'south'),
    #         'south': ('south', 'north'),
    #         'east': ('east', 'west'),
    #         'west': ('west', 'east'),
    #     }
    #     base_name, new_name = side_map[orientation]
    #     base = np.array(current_plat_coords[base_name])
    #     new = np.array(next_plat_coords[new_name])
    #     # endpoints
    #     p1_orig, p2_orig = base[0], base[-1]
    #     p1_new, p2_new = new[0], new[-1]
    #     # side‐vectors
    #     v_orig = p2_orig - p1_orig
    #     v_new = p2_new - p1_new
    #
    #     # lengths
    #     L_orig = np.linalg.norm(v_orig)
    #     L_new = np.linalg.norm(v_new)
    #
    #     # optional uniform scale if L_new != L_orig
    #     scale = 1.0
    #     if abs(L_orig - L_new) > 1e-6:
    #         scale = L_orig / L_new
    #
    #     # rotation angle to carry v_new → v_orig
    #     ang_new = np.arctan2(v_new[1], v_new[0])
    #     ang_orig = np.arctan2(v_orig[1], v_orig[0])
    #     theta = ang_orig - ang_new
    #
    #     # rotation matrix
    #     R = np.array([[np.cos(theta), -np.sin(theta)],
    #                   [np.sin(theta), np.cos(theta)]])
    #
    #     # your full list of new‐plat vertices:
    #     coords_new = np.array(new_plat)  # shape (N,2)
    #     # 1) move so p1_new sits at (0,0)
    #     coords0 = coords_new - p1_new[np.newaxis, :]
    #     # 2) scale
    #     coords1 = coords0 * scale
    #     # 3) rotate
    #     coords2 = coords1.dot(R.T)
    #     # 4) translate so (0,0) → p1_orig
    #     aligned_new_plat = coords2 + p1_orig[np.newaxis, :]
    #
    #     #
    #     # # optional scale
    #     # scale = (np.linalg.norm(v_orig) / np.linalg.norm(v_new)) if do_scale else 1.0
    #     # # rotation
    #     # ang_new = np.arctan2(v_new[1], v_new[0])
    #     # ang_orig = np.arctan2(v_orig[1], v_orig[0])
    #     # theta = ang_orig - ang_new
    #     # R = np.array([[np.cos(theta), -np.sin(theta)],
    #     #               [np.sin(theta), np.cos(theta)]])
    #     # # apply to all new_plat pts
    #     # pts = np.array(new_plat)
    #     # pts = (pts - p1_new) * scale
    #     # pts = pts.dot(R.T)
    #     # pts = pts + p1_orig
    #
    #     # self.grapher_two_plots(old_plat, pts)
    #     # return [tuple(p) for p in pts]

    # def stitcher_process2(self, newPlat, section, direction, path, coordLst, valsLstTot):
    #     valsLst = getPlatVals(newPlat, section, path)
    #     coords = [0] * 20
    #     if direction == "E":
    #         coords, valsLst = self.directionE(coords, coordLst, valsLst, valsLstTot)
    #         return coords, valsLst
        # elif direction == 'W':
        #     coords, valsLst = ExcelGetNewCoords.directionW(coords, coordLst, valsLst, valsLstTot)
        #     return coords, valsLst
        # elif direction == 'S':
        #     coords, valsLst = ExcelGetNewCoords.directionS(coords, coordLst, valsLst, valsLstTot)
        #     return coords, valsLst
        # elif direction == 'N':
        #     coords, valsLst = ExcelGetNewCoords.directionN(coords, coordLst, valsLst, valsLstTot)
        #     return coords, valsLst

    def directionE(self, next_plat_df, next_plat_coords, current_plat_coords, conc, direction):
        coords = [0] * 20
        # updated_coords = []

        original_plat = [tuple(item[:2]) for k, v in current_plat_coords.items() for item in v]
        new_plat = [tuple(item[:2]) for k, v in next_plat_coords.items() for item in v]

        old_line_s = current_plat_coords['south']
        old_line_n = current_plat_coords['north']
        old_line_e = current_plat_coords['east']
        old_line_w = current_plat_coords['west']

        line_s = np.array(next_plat_coords['south'])
        line_n = np.array(next_plat_coords['north'])
        line_e = next_plat_coords['east']
        line_w = next_plat_coords['west']

        new_line_w = old_line_e[::-1]
        south_pt = new_line_w[-1]
        north_pt = new_line_w[0]


        new_line_s = (line_s + [south_pt]).tolist()
        new_line_n = (line_n + [north_pt]).tolist()
        new_line_e = []
        # coords = new_line_s + new_line_w
        coords = new_line_w
        # coords[0] = original_plat[4]
        # for i in range(6):
        #     coords[14 + i] = original_plat[10 - i]
        #
        # for i in range(4):
        #     starting_pt =
        #
        # for i in range(4):
        #     coords[i + 1] = list(self.intersect_circle_and_line(coords[i][0], coords[i][1], lineS[i][1], lineS[i][0], 'E'))
            # coords[13 - i] = list(
            #     self.intersect_circle_and_line(coords[14 - i][0], coords[14 - i][1], lineN[i][1], lineN[i][0], 'E'))
        # coords[9] = coords[10]
        # coords[5] = coords[4]
        # for i in range(3):
        #     coords[8 - i] = list(
        #         self.intersectCircleAndLine(coords[9 - i][0], coords[9 - i][1], lineE[i][1], lineE[i][0], 'S'))

        self.grapher_two_plots(original_plat, coords)
        return coords
        pass

    def directionE2(self, coords, coordLst, valsLst, valsLstTot):
        lineS = [valsLst[0], valsLst[1], valsLst[2], valsLst[3]]
        lineN = [valsLst[11], valsLst[10], valsLst[9], valsLst[8]]
        lineE = [valsLst[7], valsLst[6], valsLst[5], valsLst[4]]
        lineW = [valsLst[12], valsLst[13], valsLst[14], valsLst[15]]

        if len(coordLst) == 4:
            coordLst = list(itertools.chain.from_iterable(coordLst))

        coords[0] = coordLst[4]

        for i in range(6):
            coords[14 + i] = coordLst[10 - i]

        for i in range(4):
            coords[i + 1] = list(self.intersectCircleAndLine(coords[i][0], coords[i][1], lineS[i][1], lineS[i][0], 'E'))
            coords[13 - i] = list(
                self.intersectCircleAndLine(coords[14 - i][0], coords[14 - i][1], lineN[i][1], lineN[i][0], 'E'))

        coords[9] = coords[10]
        coords[5] = coords[4]

        for i in range(3):
            coords[8 - i] = list(
                self.intersectCircleAndLine(coords[9 - i][0], coords[9 - i][1], lineE[i][1], lineE[i][0], 'S'))

        return coords, valsLst

    def intersect_circle_and_line(self, a, b, mr, r, dir):
        θ = math.radians(mr)
        dx = r * math.cos(θ)
        dy = r * math.sin(θ)
        return [a + dx, b + dy]

    def intersectCircleAndLine(self, a, b, mr, r, dir):
        if mr == 0 or mr == 180 or mr == 90 and r == 0:
            return a, b

        if mr < 90:
            m = math.tan(math.radians(90 - mr))
        if 95 > mr >= 90:
            m = math.tan(math.radians(90 - mr))
        if mr >= 180:
            m = math.tan(math.radians(90 - (mr - 180)))
        if 180 > mr > 175:
            m = math.tan(math.radians(90 - (mr - 180)))

        d = b - (m * a)

        den = (1 + m ** 2)
        ang = (r ** 2 * den) - (b - m * a - d) ** 2
        sqAng = math.sqrt(ang)
        x1 = (a + b * m - d * m + sqAng) / den
        x2 = (a + b * m - d * m - sqAng) / den

        y1 = (d + (a * m) + (b * m ** 2) + (m * sqAng)) / den
        y2 = (d + (a * m) + (b * m ** 2) - (m * sqAng)) / den

        if dir == 'E':
            if x1 > a:
                return [x1, y1]
            elif x2 > a:
                return [x2, y2]

        elif dir == 'W':
            if a > x1:
                return [x1, y1]
            elif a > x2:
                return [x2, y2]

        elif dir == 'S':
            if y1 < b:
                return [x1, y1]
            elif y2 < b:
                return [x2, y2]

        elif dir == 'N':
            if y1 > b:
                return [x1, y1]
            elif y2 > b:
                return [x2, y2]

    def gather_new_plat(self, version):
        pass

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

    def graph_plats_and_well(self, polygons, well):
        grouped = polygons.groupby("conc")
        fig, ax = plt.subplots()
        x = [point[0] for point in well]
        y = [point[1] for point in well]
        ax.plot(x, y, color='blue', linewidth=3)

        for i, k in grouped:
            x_coords_1 = k['x'].values.tolist()
            y_coords_1 = k['y'].values.tolist()
            ax.plot(x_coords_1, y_coords_1, color='red')
        ax.set_aspect('equal', 'box')
        plt.show()
        pass
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


class PlatEditorProcess:
    def __init__(self, conn, plat_df, plat_coords, shl, well_df):
        # self.load_surveys()
        # self.write_data_to_db()
        self.well_path = well_df
        self.location_db = conn
        self.initial_plat_conc, self.initial_plat = next(iter(plat_df))
        self.inital_plat_coords = plat_coords
        self.all_plats = [plat_df]
        self.shl = shl
        adj_sections = find_adjacent_sections(self.location_db, self.initial_plat_conc[0])
        fix_adj_sections(self.location_db, adj_sections, self.initial_plat_conc)
        self.run_finder_process(self.inital_plat_coords, self.well_path, self.initial_plat_conc[0])

    # def find_relevant_datasets(self):
    #     used_concs = self.used_data_df['Conc'].unique()
    #     query = f"select * from section_plat_data"
    #     output = pd.read_sql(query, self.location_db).drop_duplicates(keep="first")
    #     output['new_code'] = output['new_code'].apply(lambda row: row[:9])
    #     output = output[output['new_code'].isin(used_concs)]
    #     output = output.astype({"Length": float, "Degrees": float, "Minutes": float, "Seconds": float})
    #     output = output.astype({"Minutes": int, "Seconds": int})
    #     # output_foo = output.apply(
    #     #     self.decimal_converter(output['Side'], output['Degrees'], output['Minutes'], output['Seconds'],
    #     #                            output['Alignment']))
    #     output_foo = output.apply(
    #         lambda row: self.decimal_converter(row['Side'], row['Degrees'], row['Minutes'], row['Seconds'],
    #                                            row['Alignment']), axis=1)
    #     grouped = output.groupby(['new_code', 'Version'])
    #     return grouped
    def decimal_converter(self, side, deg, minutes, sec, dir_val):
        """
        Simplified version with clearer logic (mathematically equivalent to above).
        """
        dec_val_base = deg + minutes / 60 + sec / 3600
        side_lower = side.lower()

        # Base orientations for each side
        if 'west' in side_lower:
            base_azimuth = 90
        elif 'east' in side_lower:
            base_azimuth = 270
        elif 'north' in side_lower:
            if dir_val in [3, 2]:  # SW, NE
                base_azimuth = 90
            else:  # SE, NW
                base_azimuth = 270
        elif 'south' in side_lower:
            if dir_val in [4, 1]:  # NW, SE
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

    def run_finder_process(self, init_plat, well_path, conc):
        dirLst = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        starter_pt = get_starter_pt(self.well_path.iloc[0], init_plat)
        current_plat = Polygon([i[:2] for i in init_plat])
        xMin, xMax, yMin, yMax = current_plat.bounds
        used_pt = starter_pt
        well_path['rel_plat_conc'] = False
        used_conc = conc
        for x, row in well_path.iterrows():
            delta_x, delta_y = row['delta_x'] * 0.3048, row['delta_y'] * 0.3048
            used_pt = [used_pt[0] + delta_x, used_pt[1] + delta_y]
            dir_val, index = get_direction(used_pt, xMin, xMax, yMin, yMax)
            index = dirLst.index(dir_val)
            if not dir_val:
                return
            if current_plat.contains(Point(used_pt)):
                well_path.at[x, 'rel_plat_conc'] = conc
            else:
                # adj_sections = find_adjacent_sections(self.location_db, conc)
                new_plat = get_plat_adjacency_dict(conc, index)

    def get_new_plat_data(self):
        pass

    def get_new_coords_plat(self, newPlat, section, direction, path, coordLst, valsLstTot):
        valsLst = getPlatVals(newPlat, section, path)
        coords = [0] * 20
        if direction == "E":
            coords, valsLst = ExcelGetNewCoords.directionE(coords, coordLst, valsLst, valsLstTot)
            return coords, valsLst
        elif direction == 'W':
            coords, valsLst = ExcelGetNewCoords.directionW(coords, coordLst, valsLst, valsLstTot)
            return coords, valsLst
        elif direction == 'S':
            coords, valsLst = ExcelGetNewCoords.directionS(coords, coordLst, valsLst, valsLstTot)
            return coords, valsLst
        elif direction == 'N':
            coords, valsLst = ExcelGetNewCoords.directionN(coords, coordLst, valsLst, valsLstTot)
            return coords, valsLst

    def decimal_converter(self, side, deg, minutes, sec, dir_val):
        dec_val_base = deg + minutes / 60 + sec / 3600
        if 'west' in side.lower():
            if dir_val in [4, 1]:
                decVal = 90 + dec_val_base
            else:
                decVal = 90 - dec_val_base
        if 'east' in side.lower():
            if dir_val in [4, 1]:
                decVal = 270 + dec_val_base
            else:
                decVal = 270 - dec_val_base
        if 'north' in side.lower():
            if dir_val in [3, 2]:
                decVal = 360 - (270 + dec_val_base)
            else:
                decVal = 270 + dec_val_base
        if 'south' in side.lower():
            if dir_val in [4, 1]:
                decVal = 90 + dec_val_base
            else:
                decVal = 360 - (90 + dec_val_base)
        return side, decVal

    def dms_to_radians(self, deg, minu, sec):
        total_deg = deg + minu / 60.0 + sec / 3600.0
        return np.deg2rad(total_deg)

    def build_initial_coord_list(self, shl_xy, plat_df):
        """
        Assume:
          - shl_xy is the (x, y) coordinate of the SHL, which we treat as the first corner.
          - plat_df has exactly 4 rows, each describing one side of that same section.
            Columns: ['Side','Length','Degrees','Minutes','Seconds', ...].
          - The rows of plat_df must be in the exact sequential order of sides around the section.
            E.g., start at the SHL corner, then the next row leads to the next corner, etc.
        Returns:
          - coord_list: a length-4 list of (x, y) tuples representing the corners in order.
        """
        x0, y0 = shl_xy
        corners = [(x0, y0)]

        for _, row in plat_df.iterrows():
            theta = self.dms_to_radians(row['Degrees'], row['Minutes'], row['Seconds'])
            length = row['Length']
            dx = length * np.sin(theta)
            dy = length * np.cos(theta)
            x1 = x0 + dx
            y1 = y0 + dy
            corners.append((x1, y1))
            x0, y0 = x1, y1
        # If the last corner isn’t exactly the SHL, we can drop the repeated closure.
        # We only want four distinct corners; the final appended might be equal to the first.
        unique_corners = corners[:4]

        return unique_corners


# section_relative
# BaseData
# def write_data_to_db(self):
#     src_path = r'C:\Users\coltongoodrich\Documents\GitHub\RewriteAPD2\APD_Data.db'
#     dst_path = r'C:\Work\Databases\Board_DB_Plss_Sections.db'
#     with sqlite3.connect(src_path) as src_conn:
#         df = pd.read_sql_query("SELECT * FROM SectionPlatData", src_conn)
#     # # Append it into the destination DB
#     with sqlite3.connect(dst_path) as dst_conn:
#         df.to_sql(
#             'section_plat_data',
#             dst_conn,
#             if_exists='append',  # or 'replace' / 'fail'
#             index=False
#         )
#     pass


def mainPlats(platData, xMin, xMax, yMin, yMax, wellPath, path, coordLst, platAlphaCol, valsLst, minMaxSum, modPath):
    dirLst = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    section = platData[0]
    allCoords = [coordLst]
    maxLsts = [minMaxSum]
    valsLstTot = [valsLst]
    platLst = []
    i = 0
    sectionVals = [section]
    while len(wellPath) > 0:
        # using the current section, return the adjacent sections
        lst = platAdjacentLsts(section)
        # finds the direction that the well is traveling

        direction, wellPath = getDirection(xMin, xMax, yMin, yMax, wellPath)

        # if the direction equals null, the well has reached the end of the sections.
        if direction == 'Null':
            return allCoords, maxLsts, valsLstTot, wellPath, platLst

        # generate an index for figuring where the next section goes
        index = dirLst.index(direction)

        # marks down the previous section, and using the index value, looks for the next section
        oldSection = section
        section = lst[index]

        # this is used to check if the well is crossing section lines and adjusts accordingly
        platData[1], platData[2], platData[3], platData[4] = TSRMainCheck(direction, section, platData, oldSection)
        # get values for adjacent corners
        # this is the plat data
        valsLst2 = getPlatVals(platData, section, path)

        valsAddLst = []
        valsAddLst2 = []
        countLst = 0
        for k in range(4):
            valsAddLst.append(
                valsLst2[countLst][0] + valsLst2[countLst + 1][0] + valsLst2[countLst + 2][0] + valsLst2[countLst + 3][
                    0])
            valsAddLst2.append(
                valsLstTot[-1][countLst][0] + valsLstTot[-1][countLst + 1][0] + valsLstTot[-1][countLst + 2][0] +
                valsLstTot[-1][countLst + 3][0])
            countLst += 4

        # check to see if the sides match. This is for checking if there are corners that are different between plats.
        # this is used to get the new coordinates and values for the plat

        if section in sectionVals:
            indexSection = sectionVals.index(section)
            coordLst, valsLst = allCoords[indexSection], valsLstTot[indexSection]
            if len(coordLst) == 4:
                coordLst = ModuleAgnostic.manyToOne(coordLst)
        else:
            coordLst, valsLst = getNewCoords(platData, section, direction, path, coordLst, valsLstTot)

        # generates a new corners list based off the new data

        # generates the min maxes for helping determine the well's next direction.
        xMin, xMax, yMin, yMax = getXMinMax(coordLst)
        writeGraphic(coordLst, path, platAlphaCol[i + 1], modPath)

        # append to a amalgamation list for each specific value
        platLst.append([section, platData[1], platData[2], platData[3], platData[4], platData[5]])
        allCoords.append(coordLst)
        maxLsts.append([xMin, xMax, yMin, yMax])

        valsLstTot.append(valsLst)
        i += 1
        sectionVals.append(section)

    return allCoords, maxLsts, valsLstTot, wellPath, platLst


def platAdjacentLsts(index):
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
    return lst[index]


def getDirection(xMin, xMax, yMin, yMax, wellPath):
    minMaxLst = [False, False, False, False]
    NSBooLst = [False, False]
    EWBooLst = [False, False]
    vLst = []
    dirLst = []
    for i in range(len(wellPath)):
        if wellPath[i][0] > xMax:
            minMaxLst[0] = True
            EWBooLst[0] = True
            vLst.append(i)
            dirLst.append('E')

        elif wellPath[i][0] < xMin:
            minMaxLst[1] = True
            EWBooLst[1] = True
            vLst.append(i)
            dirLst.append('W')

        if wellPath[i][1] > yMax:
            minMaxLst[2] = True
            NSBooLst[0] = True
            vLst.append(i)
            dirLst.append('N')

        elif wellPath[i][1] < yMin:
            minMaxLst[3] = True
            NSBooLst[1] = True
            vLst.append(i)
            dirLst.append('S')

    if True not in minMaxLst:
        return "Null", wellPath

    # elif dirLst[0][1] == dirLst[1][1]:
    #     direction = dirLst[1][0]+dirLst[0][0]
    #     return direction, wellPath[vLst[0]:]
    else:
        modWellPath = wellPath[vLst[0]:]

        # if True in NSBooLst and True not in EWBooLst:
        #     return dirLst[0], modWellPath
        # elif True not in NSBooLst and True in EWBooLst:
        #     return dirLst[0], modWellPath
        return dirLst[0][0], modWellPath


def getPlatVals(newPlat, section, path):
    valsLst, platWS = ExcelDataValues.getDataVals(path, section, newPlat[1], newPlat[2], newPlat[3], newPlat[4],
                                                  newPlat[5])
    return valsLst


def getXMinMax(coordLst):
    xMinlst = [coordLst[i][0] for i in range(len(coordLst))]
    yMinlst = [coordLst[i][1] for i in range(len(coordLst))]
    xMin, xMax = min(xMinlst), max(xMinlst)
    yMin, yMax = min(yMinlst), max(yMinlst)

    return xMin, xMax, yMin, yMax


def writeGraphic(coordLst, path, alph, modPath):
    # modPath = os.path.join(path, 'Casing_Review V8-7Test.xlsm')
    # modPath = os.path.join(path, 'Casing_Review V8-7 Sage 16-19-18-2-1E-H2.xlsm')
    # modPath = os.path.join(path, 'Casing_Review V8-7 Myton City UT 16-23 3-2-25-36-7H.xlsm')
    wbxl = xw.Book(modPath)
    gSheet = wbxl.sheets['DisplayPlat']

    for i in range(len(coordLst)):
        gSheet.range(alph[0] + str(i + 3)).value = coordLst[i][0]
        gSheet.range(alph[1] + str(i + 3)).value = coordLst[i][1]


def TSRMainCheck(direction, section, platData, oldSection):
    foundBoo = False
    if direction == 'N':
        edgeSections = [1, 2, 3, 4, 5, 6]
        if oldSection in edgeSections:
            foundBoo = True

    elif direction == 'S':
        edgeSections = [31, 32, 33, 34, 35, 36]
        if oldSection in edgeSections:
            foundBoo = True

    elif direction == 'E':
        edgeSections = [1, 12, 13, 24, 25, 36]
        if oldSection in edgeSections:
            foundBoo = True

    elif direction == 'W':
        edgeSections = [6, 7, 18, 19, 30]
        if oldSection in edgeSections:
            foundBoo = True

    if not foundBoo:
        return platData[1], platData[2], platData[3], platData[4]

    else:
        township, townshipDir = changeTownship(platData[1], platData[2], direction)
        township, townshipDir = changeTownship(platData[1], platData[2], direction)
        rng, rngDir = changeRange(platData[3], platData[4], direction)

        return township, townshipDir, rng, rngDir


def changeRange(rng, rngDir, direction):
    if direction == 'W':
        # if the section is a western range moving to the west, increase the range by 1
        if rngDir == 2:
            rng += 1
        # if the section is an eastern range moving west:
        elif rngDir == 1:
            # if it is already at the 1E line, switch it to 1W
            if rng == 1:
                rngDir = 2
            # otherwise, decrease the number by 1
            else:
                rng -= 1

    elif direction == 'E':
        # if the section is a western range moving to the east:
        if rngDir == 2:
            # if it is already at the 1W line, switch it
            if rng == 1:
                rngDir = 1
            else:
                rng -= 1
        elif rngDir == 1:
            rng += 1
    return rng, rngDir


def changeTownship(township, townshipDir, direction):
    if direction == 'N':
        if townshipDir == 2:
            if township == 1:
                townshipDir = 1
            else:
                township -= 1
        elif townshipDir == 1:
            township += 1
    elif direction == 'S':
        if townshipDir == 2:
            township += 1
        elif townshipDir == 1:
            if township == 1:
                townshipDir = 2
            else:
                township -= 1
    return township, townshipDir
