import copy
import math
import sqlite3
import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.geometry import Polygon, Point, LineString
import matplotlib.pyplot as plt
import PyQt5

import matplotlib.pyplot as plt
from shapely.geometry import Polygon
import os
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QTableWidgetItem
import utm
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
from pyproj import Transformer
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QWidget, QRadioButton, QButtonGroup
from functools import partial
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import numpy as np
from matplotlib.textpath import TextPath
from matplotlib.patches import PathPatch
from PyQt5.QtWidgets import QAbstractItemView, QSizePolicy
from PyQt5.QtWidgets import QHeaderView, QAbstractItemView
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLineEdit, QSpinBox,
                             QCheckBox,
                             QDialog, QTabWidget, QTextBrowser, QTableWidget, QLabel, QTableView, QRadioButton,
                             QGraphicsView,
                             QComboBox, QMessageBox, QFileDialog, QButtonGroup)
import ModuleAgnostic
from main_project_drawer import ZoomPan
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import QTableWidget
import regex as re
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLineEdit, QSpinBox,
                             QCheckBox,
                             QDialog, QTabWidget, QTextBrowser, QTableWidget, QLabel, QTableView, QRadioButton,
                             QGraphicsView,
                             QComboBox, QMessageBox, QFileDialog, QButtonGroup)
import time


def convert_to_pts(plat):
    def new_point_finder(r, angle, center_x, center_y):
        x_new = center_x + (r * math.cos(math.radians(angle)))
        y_new = center_y + (r * math.sin(math.radians(angle)))
        return x_new, y_new

    xy_lst = []
    x, y = 0, 0
    custom_order = [3, 2, 1, 0, 8, 9, 10, 11, 4, 5, 6, 7, 15, 14, 13, 12]
    dir_order = ['west', 'north', 'east', 'south']
    # # Method 1: Using reindex
    df_reordered = plat.reindex(custom_order).reset_index()
    # print(df_reordered)
    for val, row in df_reordered.iterrows():
        test = math.floor(val / 4)

        # print(val, dir_order[test])
        xy_lst.append([x, y, dir_order[test]])
        x, y = new_point_finder(row['Length'], row['decimal_azimuth'], x, y)
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
    print(round(angle % (math.pi*2),2), round(math.degrees(angle) % 360,2))
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

    def get_starter_pt(self, row, current_plat):
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

    def run_finder_process(self, init_plat, well_path, conc):
        dirLst = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        starter_pt = self.get_starter_pt(self.well_path.iloc[0], init_plat)
        current_plat = Polygon([i[:2] for i in init_plat])
        xMin, xMax, yMin, yMax = current_plat.bounds
        used_pt = starter_pt
        well_path['rel_plat_conc'] = False
        used_conc = conc
        for x, row in well_path.iterrows():
            delta_x, delta_y = row['delta_x'] * 0.3048, row['delta_y'] * 0.3048
            used_pt = [used_pt[0] + delta_x, used_pt[1] + delta_y]
            dir_val,index = self.get_direction(used_pt, xMin, xMax, yMin, yMax)
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

    def get_direction(self, val, xMin, xMax, yMin, yMax):

        if val[0] > xMax:
            return 'E', 2
        elif val[0] < xMin:
            return 'W', 6
        if val[1] > yMax:
            return 'N', 0
        elif val[1] < yMin:
            return 'S', 4
        return False


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
