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


def convert_to_pts(plat):
    def new_point_finder(r, angle, center_x, center_y):
        x_new = center_x + (r * math.cos(math.radians(angle)))
        y_new = center_y + (r * math.sin(math.radians(angle)))
        return x_new, y_new

    xy_lst = []
    x, y = 0, 0
    custom_order = [3, 2, 1, 0, 8, 9, 10, 11, 4, 5, 6, 7, 15, 14, 13, 12]
    # dirLst = ['South_Left_2', 'South_Left_1', 'South_Right_1', 'South_Right_2',
    #           'East_Up_2', 'East_Up_1', 'East_Down_1', 'East_Down_2',
    #           'North_Left_2', 'North_Left_1', 'North_Right_1', 'North_Right_2',
    #           'West_Up_2', 'West_Up_1', 'West_Down_1', 'West_Down_2']
    dir_lst = ['west_down_2', 'west_down_1', 'west_up_1', 'west_up_2', 'north_left_2', 'north_left_1', 'north_right_1',
               'north_right_2', 'east_up_2', 'east_up_1', 'east_down_1', 'east_down_2', 'south_right_2',
               'south_right_1',
               'south_left_1', 'south_left_2']

    dir_order = ['west', 'north', 'east', 'south']
    # # Method 1: Using reindex
    print(plat)
    print(plat['side'].unique())

    # plat['side'] = pd.Categorical(plat['side'], categories=dir_lst, ordered=True)
    plat['side'] = pd.Categorical(plat['side'], categories=dir_lst, ordered=True)
    df_reordered = plat.reindex(custom_order).reset_index()
    # print(df_reordered)
    for val, row in df_reordered.iterrows():
        test = math.floor(val / 4)

        # print(val, dir_order[test])
        xy_lst.append([x, y, dir_order[test]])
        x, y = new_point_finder(float(row['length']), float(row['decimal_azimuth']), x, y)
    xy_lst.append([x, y, dir_order[test]])
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
    # print(used direction)
    dirLst = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    # return adjacency_dict[val]


def calculate_angle(point1, point2):
    angle = math.atan2(point2.y - point1.y, point2.x - point1.x)
    print(round(angle % (math.pi * 2), 2), round(math.degrees(angle) % 360, 2))
    return math.degrees(angle)


def fix_adj_sections(conn, adj_sections, init_plat):
    # print(adj_sections, init_plat )
    used_concs = adj_sections + [init_plat[0]]
    # print(used_concs)
    df = pd.DataFrame(columns=['conc', 'geometry'])
    query = f"SELECT * FROM BaseData"
    output = pd.read_sql(query, conn)
    used_data = output[output['Conc'].isin(used_concs)]
    init = used_data[used_data['Conc'] == init_plat[0]]
    init_ref_plat = Polygon(init[['Easting', 'Northing']].values.tolist())
    grouped = used_data.groupby(['Conc'])
    # print(init_ref_plat)
    for i, row in grouped:
        geo_vals = Polygon(row[['Easting', 'Northing']].values.tolist())
        angle = calculate_angle(init_ref_plat.centroid, geo_vals.centroid)

        # shared_len, direction = classify_with_buffer(init_ref_plat, geo_vals, epsilon=1e-4)
        # print(shared_len, direction)
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
    print(ns_distance, ns_type, ew_distance, ew_type)
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
    if len(ns_coords) > 1:
        for i in range(len(ns_coords) - 1):
            ns_segments.append((tuple(ns_coords[i]), tuple(ns_coords[i + 1])))

    ew_segments = []
    if len(ew_coords) > 1:
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
        try:
            parallel = line.parallel_offset(ew_distance, 'right')

            # if ns_type == 'FEL':
            #     parallel = line.parallel_offset(-ew_distance, ew_offset_side)
            # elif ns_type == 'FWL':
            #     parallel = line.parallel_offset(ew_distance, ew_offset_side)

            # parallel = line.parallel_offset(ew_distance, ew_offset_side)
            if hasattr(parallel, 'coords'):
                ew_parallel_segments.append(list(parallel.coords))
        except:
            continue

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
        all_rel_surveys = self.get_all_rel_wells()
        self.setup_combo_boxes(all_rel_surveys)

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

        cols = ["length", "degrees", "minutes", "seconds", "bearing_str"]
        current_label = combo.itemText(index)
        query = f"select * from tsr_plats_surveys where label = '{current_label}'"
        output = pd.read_sql(query, self.conn)
        fill_tsr_data()
        fill_calls_models()
        fill_calls_data()
        self.currently_used_plat_data = self.collect_relative_data()
        used_indexes = self.currently_used_plat_data['order'].unique()
        self.run_plat_well_tracer(plat_data=self.currently_used_plat_data)

    def collect_relative_data(self):
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
                print('version', version)
                rec['order'] = version
                records.append(rec)
        df = pd.DataFrame.from_records(records)

        df['decimal_azimuth'] = df.apply(lambda row: decimal_converter(row['side'], row['degrees'], row['minutes'], row['seconds'], row['baseline_str']), axis=1)
        return df
        #
        # # 2) for each side-table, read every row
        # for side in side_names:
        #     tbl: QTableView = getattr(self.ui, f"{side}_table_rel_{version}")
        #     model = tbl.model()
        #     if model is None:
        #         continue
        #     rows = model.rowCount()
        #     columns = model.columnCount()
        #     rec = {
        #         "section": section,
        #         "township": township,
        #         "township_bearing_str": town_dir,
        #         "rng": rng,
        #         "rng_bearing_str": rng_dir,
        #         "baseline_str": baseline,
        #         "side": side,
        #     }
        # for side in side_names:
        #     tbl: QTableView = getattr(self.ui, f"{side}_table_rel_{version}")
        #     model = tbl.model()
        #     if model is None:
        #         continue
        #
        #     # start a fresh record for this side
        #     rec = dict(rec_base)
        #     rec["side"] = side
        #
        #     # iterate each row in the single column
        #     for row_idx, field in enumerate(table_fields):
        #         # safe‐guard if someone changed row-count
        #         if row_idx < model.rowCount():
        #             item = model.item(row_idx, 0)
        #             rec[field] = item.text() if item is not None else ""
        #         else:
        #             rec[field] = ""
        #
        #     records.append(rec)
        #     #
        #     # for row in range(rows):
        #     #     row_data = []
        #     #     for column in range(columns):
        #     #         index = model.index(row, column)
        #     #         # Get the data for the current cell
        #     #         cell_data = model.data(index, Qt.DisplayRole)
        #             row_data.append(cell_data)
        # data.append(row_data)

        # for col_idx, col_name in enumerate(row_cols):
        #     print(col_idx, col_name)
        #     item = model.item(row, col_idx)
        # for row_idx, row_name in enumerate(row_cols):
        #     print([row_idx])
        #     # index = model.index(row_idx, 0)
        #     cell_data = model.data(row_idx, 0)
        #     print(cell_data)
        # build one record per row

        # pull out each column value
        # for column in range(columns):
        #     index = model.index(row, column)
        #     # Get the data for the current cell
        #     cell_data = model.data(index, Qt.DisplayRole)
        #     # print('cell', cell_data)
        #     # row_data.append(cell_data)
        #
        # for col_idx, col_name in enumerate(table_cols):
        #     print(col_idx, col_name)
        #     item = model.item(row, col_idx)
        #     # print(item)
        #     val = item.text() if item is not None else ""
        #     rec[col_name] = val

        # records.append(rec)

        # 3) turn into a DataFrame
        # df = pd.DataFrame.from_records(records)
        # print(df)
        # # 4) optionally cast numeric columns back to numbers
        # for numcol in ["section","township","rng","length","degrees","minutes","seconds","decimal_azimuth"]:
        #     if numcol in df:
        #         df[numcol] = pd.to_numeric(df[numcol], errors="coerce")
        # print(df)
        # return df

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
        # print(output)

    def run_plat_well_tracer(self, plat_data):
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

        print(plat_data)
        grouped = plat_data.groupby(['order'])
        # init_plat_data = next(iter(grouped))
        initial_plat_conc, init_plat_data = next(iter(grouped))
        init_plat = convert_to_pts(init_plat_data)

        # for i, k in grouped:
        #     print(i)
        well_path = get_dataframe_from_qtableview()
        dirLst = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        starter_pt = get_starter_pt(well_path.iloc[0], init_plat)
        print(starter_pt)
        used_pt = starter_pt
        for x, row in well_path.iterrows():
            print([row['delta_x'], row['delta_y']])
            delta_x, delta_y = float(row['delta_x']) * 0.3048, float(row['delta_y']) * 0.3048
            used_pt = [used_pt[0] + delta_x, used_pt[1] + delta_y]
            print(used_pt)
            # dir_val, index = get_direction(used_pt, xMin, xMax, yMin, yMax)
        #     index = dirLst.index(dir_val)
        #     if not dir_val:
        #         return
        #     if current_plat.contains(Point(used_pt)):
        #         well_path.at[x, 'rel_plat_conc'] = conc
        #     pass

    # self.ui.plat_searcher_combo_box.activated.connect(self.plat_searcher_combo_process)


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
    out = find_point_from_footages(current_plat, fnsl_val, fnsl, fewl_val, fewl)
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
        # print(adj_sections)
        self.run_finder_process(self.inital_plat_coords, self.well_path, self.initial_plat_conc[0])
        # self.initial_plat = first_group_name, first_group_data = next(iter(grouped))
        # print(self.initial_plat)

        # self.used_data_df = plat_df
        # self.grouped_df = self.find_relevant_datasets()

        # print()
        # print(well_df.columns)

        # query = f"SELECT * FROM section_plat_data"
        # print(pd.read_sql(query, self.location_db))

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
        # print(corners)
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
#     # print(df)
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
