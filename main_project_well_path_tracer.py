import traceback

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
import regex as re
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from shapely.geometry import Point, LineString, Polygon, MultiPoint
from shapely.geometry.base import BaseGeometry
import operator
from main_project_clearance import ClearanceProcess


# from main_project_well_path_tracer import main_tracer_process


def get_direction_sides(all_plats_df, current_plat_conc, intersection_pt):
    used_df = all_plats_df[all_plats_df['conc'] == current_plat_conc]
    grouped_df = used_df.groupby('side')
    dict_index = {'e': 2, 'w': 6, 'n': 0, 's': 4}
    for r, group_df in grouped_df:
        line_string_side = Polygon(group_df[['x', 'y']].values.tolist())
        on_line3 = intersection_pt.within(line_string_side.buffer(1e-8))
        # if on_line3:
        #     print(r)
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


def check_for_multipoint(intersection_pt, intersection_pt_current):
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


def check_intersection_pts(intersection_result, intersection_segment):
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


def check_full_inter_pts(intersection_result, current_well_path_section, current_plat_coords, intersection_segment):
    print('intersect')
    dict_index = {'e': 2, 'w': 6, 'n': 0, 's': 4}

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
    all_coords = list(zip(current_well_path_section['e_offset_delta'], current_well_path_section['n_offset_delta']))

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
            return everything_but_first, pts_1[0], cardinal_direction, dict_index[cardinal_direction]
    # print(everything_but_first)
    return everything_but_first, [0, 0], None, 0


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


def tracer_process_2(well_path_dict, original_all_plats_df, current_plat_coords, well_path, current_plat_conc, currently_used_plat_data):
    well_paths_lst = [k for k, v in well_path_dict.items()]
    all_plats_df = original_all_plats_df
    # well_path = well_path_dict[i].clearance_data
    result_coords = current_plat_coords[['x', 'y', 'side']].values.tolist()
    # print(current_plat_coords)
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
    print("____________________________________________")
    while True:
        polygon_plat = current_polygon
        # pts = [Point(x, y) for x, y in zip(current_well_path_section.e_offset_delta, current_well_path_section.n_offset_delta)]
        intersection_segment = LineString(
            list(zip(current_well_path_section['e_offset_delta'], current_well_path_section['n_offset_delta'])))
        boundary = polygon_plat.exterior
        intersection_pt = intersection_segment.intersection(boundary)

        # print(current_well_path_section, intersection_pt_current)

        # plot_shapely_and_dataframe(polygon_plat, intersection_pt_current, current_well_path_section)

        # intersection_pt = check_intersection_pts(intersection_pt, intersection_segment)
        # intersection_pt_current = intersection_pt
        try:
            current_well_path_section, intersection_pt, dir_val, index = check_full_inter_pts(intersection_pt, current_well_path_section, current_plat_coords, intersection_segment)
            intersection_pt_current = intersection_pt
        except KeyError:
            all_plats_df[['x_delta', 'y_delta']] = (
                all_plats_df.apply(
                    lambda row: get_offset_added_delta(row['x'] * 0.3048, row['y'] * 0.3048, dx_start, dy_start),
                    axis=1,
                    result_type='expand'))
            # print(all_plats_df)
            # graph_plats_and_well(all_plats_df, list(zip(well_path.easting, well_path.northing)), title)
            return all_plats_df
        print(intersection_pt, dir_val, index)
        next_plat_df = currently_used_plat_data[currently_used_plat_data['range'] == counter]
        try:
            next_plat_conc = next_plat_df['conc'].iloc[0]
            if next_plat_conc == [used_conc_sections[-1]]:
                break
            if next_plat_conc not in used_conc_sections:
                rewritten_coords = all_plats_df[all_plats_df['conc'] == next_plat_conc]
            else:
                used_conc_sections.append(next_plat_conc)

                next_plat_coords_dict = all_plats_df[all_plats_df['conc'] == next_plat_conc]

                well_prox_boo = well_path_prox(intersection=intersection_pt_current, side_dict_all=next_plat_coords_dict,
                                               direction=dir_val)
                rewritten_coords = coords_stitcher(next_plat_coords_dict,
                                                   all_plats_df[all_plats_df['conc'] == current_plat_conc],
                                                   dir_val, well_prox_boo)
                print(rewritten_coords)


        except IndexError as f:
            error_traceback = traceback.format_exc()
            print(f"Error details:\n{error_traceback}")
            print('broke here 2')

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

def tracer_process(well_path_dict, original_all_plats_df, current_plat_coords, well_path, current_plat_conc, currently_used_plat_data):
    well_paths_lst = [k for k, v in well_path_dict.items()]
    all_plats_df = original_all_plats_df
    # well_path = well_path_dict[i].clearance_data
    result_coords = current_plat_coords[['x', 'y', 'side']].values.tolist()
    starter_pt = get_starter_pt(well_path.iloc[0], result_coords)
    starter_utm = well_path.iloc[0][['easting', 'northing']].values.tolist()
    dx_start, dy_start = (float(well_path['easting'].iloc[0]) / 0.3048) - starter_pt[0], (float(well_path['northing'].iloc[0]) / 0.3048) - starter_pt[1]
    well_path[['e_offset_delta', 'n_offset_delta']] = (well_path.apply(lambda row: get_offset_added_delta(starter_pt[0], starter_pt[1], row['e_offset'], row['n_offset']), axis=1, result_type='expand'))
    well_path['rel_data_order'] = 99
    # print(well_path[['e_offset_delta', 'n_offset_delta']])

    current_plat_coords_modified = [i[:2] for i in result_coords]
    current_polygon = Polygon(current_plat_coords_modified)
    counter = 2
    intersection_pt_current = Point(0, 0)
    while True:
        polygon_plat = current_polygon
        pts = [Point(x, y) for x, y in zip(well_path.e_offset_delta, well_path.n_offset_delta)]
        mask = [polygon_plat.contains(pt) for pt in pts]
        well_path.loc[mask, 'rel_data_order'] = counter - 1
        used_well_path_df = well_path[well_path['rel_data_order'] >= counter - 1]
        intersection_segment = LineString(list(zip(used_well_path_df['e_offset_delta'], used_well_path_df['n_offset_delta'])))
        boundary = polygon_plat.exterior
        intersection_pt = intersection_segment.intersection(boundary)
        intersection_pt = check_for_multipoint(intersection_pt, intersection_pt_current)
        intersection_pt_current = intersection_pt
        try:
            dir_val, index = get_direction_sides(all_plats_df, current_plat_conc, intersection_pt)
        except (AttributeError, TypeError) as e:
            print(e)
            all_plats_df[['x_delta', 'y_delta']] = (
                all_plats_df.apply(lambda row: get_offset_added_delta(row['x'] / 0.3048, row['y'] / 0.3048, starter_utm[0], starter_utm[1]), axis=1,
                                     result_type='expand'))
            # break
            return all_plats_df

        next_plat_df = currently_used_plat_data[currently_used_plat_data['range'] == counter]
        try:
            next_plat_conc = next_plat_df['conc'].iloc[0]
        except IndexError as f:
            break
        next_plat_coords_dict = all_plats_df[all_plats_df['conc'] == next_plat_conc]

        well_prox_boo = well_path_prox(intersection=intersection_pt, side_dict_all=next_plat_coords_dict, direction=dir_val)
        rewritten_coords = coords_stitcher(next_plat_coords_dict, all_plats_df[all_plats_df['conc'] == current_plat_conc], dir_val, well_prox_boo)
        current_polygon = df_to_polygon(rewritten_coords)
        new_dict = pd.DataFrame(data=rewritten_coords.to_dict(orient='list'))

        try:
            all_plats_df = update_original_dataframe(all_plats_df, new_dict)
            counter += 1
            current_plat_conc = next_plat_conc
        except ValueError as e:
            all_plats_df[['x_delta', 'y_delta']] = (
                all_plats_df.apply(lambda row: get_offset_added_delta(row['x'] / 0.3048, row['y'] / 0.3048, starter_utm[0], starter_utm[1]), axis=1,
                                     result_type='expand'))
            # break
            return all_plats_df
    return pd.DataFrame()
def coords_stitcher(next_coords_df, current_coords_df, direction, direction_boo):
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
            current_coords_df[(current_coords_df['side'] == start_col) & (current_coords_df['point_i'] == start_row)][
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



def triangulatorWithKnownDataProcess(tsr_data, well_path, pts, df, conc, survey_data, well_parameter_data, shl, versions, conc_data, v_labels):
    survey_data = alterSurveyForLargeSpacingBetweenPts(survey_data)
    used_points = [pts[i][versions[i]] for i in range(len(pts))]
    counter = 0
    initial_data = df[df['new_code'] == conc].to_numpy().tolist()
    initial_data = initial_data[:16]
    plat_north_ref = initial_data[0][-3]
    plat_north_refs_lst = [plat_north_ref]
    foo = [survey_data[0] + [0] * 11]
    survey_data = survey_data[1:]
    known_conc_data = [conc]
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
    section_degrees_data = [used_points[0]]
    section = int(float(tsr_data[0][6]))
    data = used_points[0]
    md_lst = [i[0] for i in survey_data]
    inc_lst = [i[1] for i in survey_data]
    azi_lst = [i[2] for i in survey_data]
    north_reference, magnetic_declination, convergence_angle, target_azimuth = well_parameter_data[0], well_parameter_data[1], float(well_parameter_data[2]), float(well_parameter_data[3])
    min_curv_data = wmc.mainCalculation(md_lst, inc_lst, azi_lst, convergence_angle, north_reference, plat_north_ref, magnetic_declination, target_azimuth)
    df = editDFForTriangulator(df, versions, v_labels, conc_data)
    offset_pts_lst = [[i[8] + shl[0], i[7] + shl[1]] for i in min_curv_data]
    test_path = copy.deepcopy(offset_pts_lst)
    prev_section_data = tsr_data[0][6:]

    while True:
        corners, sides_generated = ma.cornerGeneratorProcess(data)
        sides_generated = [[j[:-1] for j in i] for i in sides_generated]
        segment_lst = [[[i[j], i[j + 1]] for j in range(len(i) - 1)] for i in sides_generated]
        # test_path, direction = findIntersectionBetweenWellAndSection(segment_lst, offset_pts_lst, shl)
        intersection, direction, well_index_end, foo, well_path_tester = findWellPathBoundaryIntersection(segment_lst, survey_data, well_parameter_data, plat_north_ref, foo, shl)
        if not well_path_tester or direction == 'Null':
            return min_curv_data, known_conc_data, section_degrees_data, plat_north_refs_lst
        index = dirLst.index(direction)
        new_section = lst[section][index]
        township, townshipDir, rng, rngDir, prev_section_data = modifySection(section, new_section, prev_section_data)
        conc_info = [new_section, township, townshipDir, rng, rngDir, tsr_data[0][-1]]
        new_conc = ma.reTranslateData(conc_info)
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
            all_data = west_data + east_data + north_data + south_data
            data_new_deg, data_new_dec = ma.dataConverterPlatToUtm(all_data)
            # data_new_dec = ma.convertToDecimal(copy.deepcopy(data_new))
            # data_new_deg = ma.pointsConverter(data_new_dec)
            rewritten_coords = coordsAdjuster(data_new_deg, data, direction, proxBoo)
            data = rewritten_coords
            section_degrees_data.append(data)
            counter += 1
        section = new_section
    return min_curv_data, known_conc_data, section_degrees_data, plat_north_refs_lst
