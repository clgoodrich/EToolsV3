import json
import textwrap

from tabulate import tabulate
from datetime import datetime
import time
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLineEdit, QSpinBox, QCheckBox,
                             QDialog, QTabWidget, QTextBrowser, QTableWidget, QLabel, QTableView, QRadioButton, QGraphicsView,
                             QComboBox, QMessageBox)
from matplotlib.collections import PatchCollection
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, QObject, QItemSelectionRange
from matplotlib.textpath import TextPath
from matplotlib.patches import PathPatch
from PyQt5.QtGui import QPainter, QMouseEvent, QGuiApplication, QStandardItemModel, QStandardItem, QFont, QDesktopServices, QTextCursor
import numpy as np
from scipy.spatial import ConvexHull
from shapely.geometry import Polygon
from rdp import rdp
import geopandas as gpd
from shapely.geometry import Polygon, Point
import numpy as np
# import collections
import collections.abc
from collections.abc import Iterable

import ModuleAgnostic
from shapely.affinity import scale
import geopy as gp
from scipy.spatial import ConvexHull
# import stateplane as sp
# hyper needs the four following aliases to be done manually.
collections.Iterable = collections.abc.Iterable
collections.Mapping = collections.abc.Mapping
collections.MutableSet = collections.abc.MutableSet
collections.MutableMapping = collections.abc.MutableMapping
from shapely.geometry import Polygon
from shapely.affinity import translate
import geopandas as gpd
from fiona.drvsupport import supported_drivers
# import wellMinimumCurvatureCalculation
import wellpathpy as wp
# from scipy.spatial import ConvexHull
import warnings
from PyQt5.QtCore import Qt
# import cv2
# from shapely.geometry import Polygon
# from shapely.ops import linemerge, unary_union, polygonize
# import math
# from pyproj import Proj, Geod
from pyproj import Proj, transform, Geod
from pyproj import Transformer
# from geopy.distance import distance
from geographiclib.geodesic import Geodesic
from math import sqrt
from geopy.distance import geodesic
from math import radians, cos, sin
import matplotlib.pyplot as plt
# from scipy import spatial
from shapely.geometry import Point, LineString
# from shapely.ops import simplify
from ast import literal_eval
import string
# import re
from shapely.geometry import Point
# from shapely.ops import cascaded_union
from shapely import buffer, simplify
import traceback
import matplotlib.colors as mcolors
from glob import glob
from functools import reduce
import operator
import inspect
import math
import os
import utm
import numpy as np
from rdp import rdp
import sqlite3
import pandas as pd
# import geopy
# import ModuleAgnostic
# from UIDataGather import *
# from shapely.geometry.polygon import Polygon
import copy
import cProfile
import pstats
from datetime import datetime
from io import StringIO
import time
import cProfile
import pstats
from io import StringIO
import pandas as pd
from functools import wraps

def search_db(path):
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    # query the sqlite_master table for all tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cur.fetchall()]

    conn.close()

def timeit(func):
    """
    Decorator: prints elapsed time each time the function is called.
    Usage:
        @timeit
        def foo(...):
            ...
    """
    @wraps(func)
    def wrapped(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"[timeit] {func.__name__!r} took {elapsed:.4f}s")
        return result
    return wrapped

def profile(func, *args, **kwargs):
    def strip_root(pathway):
        # normalize the incoming path so slashes/backslashes are consistent
        loc_norm = os.path.normpath(loc)
        if loc_norm.startswith(project_root):
            # slice off exactly the project_root length
            return loc_norm[len(project_root):]
        else:
            return loc
    """
    Profiles func(*args, **kwargs) with cProfile and returns a tuple:
      (df, total_tt, sum_self)

    df will have columns:
      ['ncalls','tottime','percall','cumtime','percall2','location','is_user']

    The function also prints:
     - the DataFrame
     - total_tt (overall wall time)
     - sum_self (sum of self-times)
     - split totals for user vs external code
    """
    # --- run profiler ---
    prof = cProfile.Profile()
    prof.runcall(func, *args, **kwargs)

    # --- capture & parse stats text ---
    s = StringIO()
    ps = pstats.Stats(prof, stream=s)
    ps.sort_stats('cumulative')
    total_tt = ps.total_tt
    ps.print_stats()

    lines = s.getvalue().split('\n')
    data = []
    cwd = os.getcwd()
    project_root = parent = os.path.dirname(cwd)
    excluded = f"{os.getcwd()}\\.venv"
    for line in lines[5:]:
        if not line.strip():
            continue
        parts = line.split(None, 5)
        if len(parts) == 6:
            ncalls, tottime, percall, cumtime, percall2, loc = parts
            loc_stripped = strip_root(loc)
            is_user = not loc.startswith(excluded)
            data.append({
                'ncalls':   ncalls,
                'tottime':  float(tottime),
                'percall':  float(percall),
                'cumtime':  float(cumtime),
                'percall2': float(percall2),
                'location': loc_stripped,
                'is_user':  is_user
            })

    df = pd.DataFrame(data)
    sum_self = df['tottime'].sum()

    # --- summarize & print ---
    print(df.sort_values('percall', ascending=False))
    print(f"\n[profile] total_tt: {total_tt:.6f}s, sum_self: {sum_self:.6f}s")

    # split‐out totals
    user_cum = df.loc[df['is_user'], 'cumtime'].sum()
    ext_cum  = df.loc[~df['is_user'], 'cumtime'].sum()
    print(f"user‐code cumulative time:     {user_cum:.6f}s")
    print(f"external (venv) cumulative time: {ext_cum:.6f}s")
    key = "{method 'execute' of 'sqlite3.Cursor' objects}"
    print(f"\nCallers of {key}:")
    ps.print_callers(key)
    return df, total_tt, sum_self

# def profile2(func, *args, **kwargs):
#     """
#     Profiles func(*args, **kwargs) with cProfile and returns a tuple:
#       (df, total_tt, sum_self)
#     - df: pandas.DataFrame with columns
#         ['ncalls','tottime','percall','cumtime','percall2','location']
#     - total_tt: total wall-clock seconds from cProfile
#     - sum_self: sum of all per-call self-times in df
#
#     Usage:
#         # no args
#         df, total, self_sum = profile(self.plat_editor.retrieve_all_data)
#
#         # with args
#         df, total, self_sum = profile(my_func, arg1, arg2, key=value)
#     """
#     prof = cProfile.Profile()
#     prof.runcall(func, *args, **kwargs)
#
#     # Capture the stats text
#     s = StringIO()
#     ps = pstats.Stats(prof, stream=s)
#     ps.sort_stats('cumulative')
#     total_tt = ps.total_tt
#     ps.print_stats()
#
#     # Parse into a DataFrame
#     lines = s.getvalue().split('\n')
#     data = []
#     str_to_remove = r"C:\Users\coltongoodrich\Documents\GitHub"
#     for line in lines[5:]:
#         if not line.strip():
#             continue
#         parts = line.split(None, 5)
#         if len(parts) == 6:
#             ncalls, tottime, percall, cumtime, percall2, loc = parts
#             data.append({
#                 'ncalls':   ncalls,
#                 'tottime':  float(tottime),
#                 'percall':  float(percall),
#                 'cumtime':  float(cumtime),
#                 'percall2': float(percall2),
#                 'location': loc.replace(str_to_remove, "", 1)
#             })
#
#     df = pd.DataFrame(data)
#     sum_self = df['tottime'].sum()
#
#     # Print results
#
#
#     return df, total_tt, sum_self
#

def analyze_time_no_args(func, *args, **kwargs):
    """
    Profiles `func(*args, **kwargs)`, prints a filtered DataFrame
    of the cumulative timings.
    """
    profiler = cProfile.Profile()
    profiler.runcall(func, *args, **kwargs)

    # capture the pstats output
    s = StringIO()
    ps = pstats.Stats(profiler, stream=s)
    ps.sort_stats('cumulative')
    ps.print_stats()

    # parse it into a DataFrame
    lines = s.getvalue().split('\n')
    data = []
    for line in lines[5:]:
        if not line.strip():
            continue
        parts = line.split(None, 5)
        if len(parts) == 6:
            ncalls, tottime, percall, cumtime, percall2, flfn = parts
            data.append({
                'ncalls':   ncalls,
                'tottime':  float(tottime),
                'percall':  float(percall),
                'cumtime':  float(cumtime),
                'percall2': float(percall2),
                'location': flfn
            })

    df = pd.DataFrame(data)
    # filter out your own profiler overhead if desired
    excluded = f"{os.getcwd()}\\.venv"
    df = df[~df['location'].str.contains(excluded, case=False, regex=False)]
    sum_self = df['tottime'].sum()
    print(f"Sum of all self‐times (df['tottime'].sum()): {sum_self:.6f} s")
    print(df)

def analyzeTime2(function_call, args_list ):

    profiler = cProfile.Profile()
    profiler.runcall(function_call, *args_list )

    # Redirect pstats output to a string stream
    s = StringIO()
    ps = pstats.Stats(profiler, stream=s)
    ps.sort_stats('cumulative')
    ps.print_stats()

    # Get the string output and process it
    lines = s.getvalue().split('\n')
    data = []
    for line in lines[5:]:  # Skip the header lines
        if line.strip():
            fields = line.split(None, 5)
            if len(fields) == 6:
                ncalls, tottime, percall, cumtime, percall2, filename_lineno_function = fields
                data.append({
                    'ncalls': ncalls,
                    'tottime': float(tottime),
                    'percall': float(percall),
                    'cumtime': float(cumtime),
                    'percall2': float(percall2),
                    'filename_lineno_function': filename_lineno_function
                })

    # Create DataFrame
    df = pd.DataFrame(data)
    excluded_location = r'C:\Work\RewriteAPD\ven2'
    filtered_df = df[~df['filename_lineno_function'].str.contains(excluded_location, case=False, regex=False)]
    # filtered_df = filtered_df[
    #     filtered_df['filename_lineno_function'].str.contains(r'C:\Work\RewriteAPD', case=False, regex=False)]


def insert_row_at_md(df, target_md):
    # Ensure the dataframe is sorted by MeasuredDepth
    df = df.sort_values('MeasuredDepth').reset_index(drop=True)

    # Find the index where the new row should be inserted
    insert_index = df['MeasuredDepth'].searchsorted(target_md)

    if insert_index == 0:
        raise ValueError("Target MeasuredDepth is below the range of existing data.")

    if insert_index == len(df):
        # Extrapolate using the last two rows
        lower_row = df.iloc[-2]
        upper_row = df.iloc[-1]
    else:
        # Interpolate using the surrounding rows
        lower_row = df.iloc[insert_index - 1]
        upper_row = df.iloc[insert_index]

    # Calculate the interpolation factor
    factor = (target_md - lower_row['MeasuredDepth']) / (upper_row['MeasuredDepth'] - lower_row['MeasuredDepth'])

    # Initialize new row with target_md
    new_row = {'MeasuredDepth': target_md}

    # Process each column
    for col in df.columns:
        if col == 'MeasuredDepth':
            continue

        # Check if column contains strings (object dtype)
        if df[col].dtype == 'object':
            # Use the value from the lower row for string columns
            new_row[col] = lower_row[col]
        else:
            try:
                # Attempt interpolation for numeric columns
                new_row[col] = np.interp(target_md,
                                         [lower_row['MeasuredDepth'], upper_row['MeasuredDepth']],
                                         [lower_row[col], upper_row[col]])
            except (TypeError, ValueError):
                # If interpolation fails, use the value from the lower row
                new_row[col] = lower_row[col]

    # Convert to Series and insert the new row
    new_row = pd.Series(new_row)
    df = pd.concat([df.iloc[:insert_index], pd.DataFrame([new_row]), df.iloc[insert_index:]]).reset_index(drop=True)

    return df
# def insert_row_at_md(df, target_md):
#     # Ensure the dataframe is sorted by MeasuredDepth
#     df = df.sort_values('MeasuredDepth').reset_index(drop=True)
#
#     # Find the index where the new row should be inserted
#     insert_index = df['MeasuredDepth'].searchsorted(target_md)
#
#
#     if insert_index == 0:
#         raise ValueError("Target MeasuredDepth is below the range of existing data.")
#
#     if insert_index == len(df):
#         # Extrapolate using the last two rows
#         lower_row = df.iloc[-2]
#         upper_row = df.iloc[-1]
#     else:
#         # Interpolate using the surrounding rows
#         lower_row = df.iloc[insert_index - 1]
#         upper_row = df.iloc[insert_index]
#     # Calculate the interpolation factor
#     factor = (target_md - lower_row['MeasuredDepth']) / (upper_row['MeasuredDepth'] - lower_row['MeasuredDepth'])
#
#     # Interpolate values for the new row
#     try:
#         new_row = pd.Series({
#             'MeasuredDepth': target_md,
#             'Inclination': np.interp(target_md, [lower_row['MeasuredDepth'], upper_row['MeasuredDepth']],
#                                      [lower_row['Inclination'], upper_row['Inclination']]),
#             'Azimuth': np.interp(target_md, [lower_row['MeasuredDepth'], upper_row['MeasuredDepth']],
#                                  [lower_row['Azimuth'], upper_row['Azimuth']]),
#             'TVD': np.interp(target_md, [lower_row['MeasuredDepth'], upper_row['MeasuredDepth']],
#                              [lower_row['TVD'], upper_row['TVD']])
#         })
#     except KeyError:
#         new_row = pd.Series({
#             'MeasuredDepth': target_md,
#             'Inclination': np.interp(target_md, [lower_row['MeasuredDepth'], upper_row['MeasuredDepth']],
#                                      [lower_row['Inclination'], upper_row['Inclination']]),
#             'Azimuth': np.interp(target_md, [lower_row['MeasuredDepth'], upper_row['MeasuredDepth']],
#                                  [lower_row['Azimuth'], upper_row['Azimuth']])
#         })
#
#     # Insert the new row
#     df = pd.concat([df.iloc[:insert_index], pd.DataFrame([new_row]), df.iloc[insert_index:]]).reset_index(drop=True)
#
#     return df


def get_dataframe_from_qtableview(table_view):
    # Get the model
    model = table_view.model()

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


def get_data_from_qtableview(table_view):
    """Uses data() method which is slightly faster than item().text()"""
    model = table_view.model()
    if not isinstance(model, QStandardItemModel):
        return None

    rows = model.rowCount()
    columns = model.columnCount()

    return [[model.data(model.index(row, col)) or ""
             for col in range(columns)]
            for row in range(rows)]


def get_all_data_from_qtableview(table_view):
    # Get the model
    model = table_view.model()

    if model is None:
        print("The QTableView does not have a model.")
        return None

    # Get the number of rows and columns
    rows = model.rowCount()
    columns = model.columnCount()

    # Create a list to store all the data
    all_data = []

    # Iterate through each cell in the table
    for row in range(rows):
        row_data = []
        for column in range(columns):
            index = model.index(row, column)
            # Get the data for the current cell
            cell_data = model.data(index, Qt.DisplayRole)
            row_data.append(cell_data)
        all_data.append(row_data)

    return all_data


def midpoint(x1, y1, x2, y2):
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def concCodeToLabel(data):
    new_line = str(int(float(data[:2]))) + " " + str(int(float(data[2:4]))) + data[4] + " " + str(
        int(float(data[5:7]))) + data[7] + " " + data[8]
    return new_line


# def labelToConcCode(data):
#     label = data.split(" ")
#     label[1] = [label[1][:-1], label[1][-1]]
#     label[2] = [label[2][:-1], label[2][-1]]
#     if len(label[0]) == 1:
#         label[0] = "0" + str(label[0])
#     if len(label[1][0]) == 1:
#         label[1][0] = "0" + str(label[1][0])
#
#     if len(label[2][0]) == 1:
#         label[2][0] = "0" + str(label[2][0])
#     label = list(itertools.chain.from_iterable(label))
#     label = "".join(label)
#     return label

def clearDatabaseOfDupes():
    conn = sqlite3.connect('Board_DB.db')

    # Read data from the table into a Pandas DataFrame
    df = pd.read_sql('SELECT * FROM WellInfo', conn)
    df = df.drop_duplicates()
    conn.execute('DROP TABLE IF EXISTS WellInfo')
    df.to_sql('WellInfo', conn, index=False)

    df = pd.read_sql('SELECT * FROM DX', conn)
    df = df.drop_duplicates()
    conn.execute('DROP TABLE IF EXISTS DX')
    df.to_sql('DX', conn, index=False)

    df = pd.read_sql('SELECT * FROM PlatData', conn)
    df = df.drop_duplicates()
    conn.execute('DROP TABLE IF EXISTS PlatData')
    df.to_sql('PlatData', conn, index=False)

    df = pd.read_sql('SELECT * FROM Production', conn)
    df = df.drop_duplicates()
    conn.execute('DROP TABLE IF EXISTS Production')
    df.to_sql('Production', conn, index=False)
    # Close the connection
    conn.close()
    print('done')


def createFileGDB(plat_df, all_plats_adjacent, base_dx_df_planned_true):
    conn_sample = sqlite3.connect('DX_sample.db')
    conn_sample.execute('DROP TABLE IF EXISTS PlatDF')
    conn_sample.execute('DROP TABLE IF EXISTS PlatAdj')
    conn_sample.execute('DROP TABLE IF EXISTS DX')
    plat_df['geometry'] = plat_df['geometry'].apply(lambda r: str(r))
    plat_df['centroid'] = plat_df['centroid'].apply(lambda r: str(r))

    all_plats_adjacent['geometry'] = all_plats_adjacent['geometry'].apply(lambda r: str(r))
    all_plats_adjacent['centroid'] = all_plats_adjacent['centroid'].apply(lambda r: str(r))
    base_dx_df_planned_true['shp_pt'] = base_dx_df_planned_true['shp_pt'].apply(lambda r: str(r))

    plat_df.to_sql('PlatDF', conn_sample, index=False)
    all_plats_adjacent.to_sql('PlatAdj', conn_sample, index=False)
    base_dx_df_planned_true.to_sql('DX', conn_sample, index=False)

    # query = "select * from DX"
    # df_out = pd.read_sql(query, conn_sample)
def interval_to_dict(interval):
    return {
        'left': float(interval.left),    # Convert to float to handle numpy types
        'right': float(interval.right),
        'closed': interval.closed
    }
def createFileGDB2(dx_df, depths):
    conn_sample = sqlite3.connect('DX_sample.db')
    conn_sample.execute('DROP TABLE IF EXISTS DX_Original')
    conn_sample.execute('DROP TABLE IF EXISTS Depths')
    dx_df = dx_df.drop(columns=['SurveySurfaceElevation', 'shp_pt'])

    depths['Interval'] = depths['Interval'].apply(
        lambda x: json.dumps(interval_to_dict(x))
    )
    conn_sample.execute('DROP TABLE IF EXISTS DX_Original')
    dx_df.to_sql('DX_Original', conn_sample, index=False)
    depths.to_sql('Depths', conn_sample, index=False)
    query = "select * from Depths"
    df_out = pd.read_sql(query, conn_sample)
# def createFileGDB2(df, stepped_boo, steps, label, drilled_depth):

def labelToConcCode(data):
    label = data.split()
    label[1], label[2] = label[1][:-1], label[2][:-1]
    label[0] = label[0].zfill(2)
    label[1] = label[1].zfill(2)
    label[2] = label[2].zfill(2)
    return "".join(label)


def labelToTable(data):
    label = data.split(" ")
    label[1] = [label[1][:-1], label[1][-1]]
    label[2] = [label[2][:-1], label[2][-1]]
    label = [label[0], label[1][0], label[1][1], label[2][0], label[2][1], label[-1]]
    return label


def tableToConcCode(label):
    label[0] = str(label[0]).zfill(2)
    label[1] = str(label[1]).zfill(2)
    label[3] = str(label[3]).zfill(2)
    return "".join(label)


# C:\Work\RewriteAPD>C:\Users\colto\AppData\Local\Programs\Python\Python37\Scripts\pyuic5.exe fileDialog.ui -o fileDialog.py
def writeFiles(cellLst, valuesLst, worksheet):
    for i in range(len(cellLst)):
        worksheet[cellLst[i]] = valuesLst[i]

def get_decimal_year():
    now = datetime.now()
    year_start = datetime(now.year, 1, 1)
    year_fraction = (now - year_start).total_seconds() / (365.25 * 24 * 3600)
    return now.year + year_fraction


def printFunctionName():
    curframe = inspect.currentframe()
    calframe = inspect.getouterframes(curframe, 2)
    print('\nFUNCTION CALLED:', calframe[1][3])

def printDataframe(df):
    df_wrapped = df.applymap(lambda x: wrap_cell(x, 30))
    print(tabulate(
        df_wrapped,
        headers="keys",
        tablefmt="psql",
        showindex=False
    ))
    # print(tabulate(df, headers='keys'))

def wrap_cell(txt, width=30):
    return "\n".join(textwrap.wrap(str(txt), width=width))
def conv_angle(I13, J13):
    E44 = 12
    # I13, J13 = 40.25773955113004, 109.93833062548505
    angle_a = 117 if E44 == 11 else 111
    angle_b = angle_a - J13
    result = round(math.atan(math.tan(math.radians(angle_b)) * math.sin(math.radians(I13))), 6)
    return round(math.degrees(result), 6)


def printLineBreak():
    print("_______________________________________________________")


def printLine(lst):
    if len(lst) != 0:
        print()
        for i in range(len(lst)):
            print(i, "\t", lst[i])
        print()


def printTupleCoords(lst):
    print([tuple(i) for i in lst])


def equationDistance(x1, y1, x2, y2):
    return math.sqrt((float(x2) - float(x1)) ** 2 + (float(y2) - float(y1)) ** 2)


def xyzEquationIncAzi(point1, point2):
    dx = point2[0] - point1[0]
    dy = point2[1] - point1[1]
    dz = point2[2] - point1[2]

    # azimuth = math.degrees(math.atan2(dy, dx))

    # Calculate the horizontal distance
    horizontal_distance = math.sqrt(dx ** 2 + dy ** 2)

    # Calculate the inclination (dip) in degrees
    inclination = math.degrees(math.atan2(dz, horizontal_distance))

    # Calculate the azimuth in degrees (0 to 360)
    azimuth = math.degrees(math.atan2(dy, dx))
    # Handle negative azimuth values (convert to 0-360 range)
    if azimuth < 0:
        azimuth += 360
    inclination = abs(90 - inclination)
    return inclination, azimuth


def convertAllPosibleStringsToFloats(lst):
    for i in range(len(lst)):
        if isinstance(lst[i], list):
            for j in range(len(lst[i])):
                try:
                    lst[i][j] = float(lst[i][j])
                except ValueError:
                    pass
        else:
            try:
                lst[i] = float(lst[i])
            except (ValueError, TypeError):
                pass

    return lst


def convertAllToStrings(lst):
    for i in range(len(lst)):
        if isinstance(lst[i], list):
            for j in range(len(lst[i])):
                lst[i][j] = str(lst[i][j])
        else:
            lst[i] = str(lst[i])
    return lst


def checkListOfListsIdentical(lst1, lst2):
    match_boos = []
    for i in range(len(lst1)):
        if set(lst1[i]) == set(lst2[i]):
            match_boos.append(True)
        else:
            match_boos.append(False)
    if False in match_boos:
        return False
    else:
        return True


def convertDecimalToDegrees(dd):
    mnt, sec = divmod(dd * 3600, 60)
    deg, mnt = divmod(mnt, 60)
    return int(deg), int(mnt), round(sec, 2)


def determineIfInside(pt, data):
    point = Point(pt[0], pt[1])
    polygon = Polygon(data)
    return polygon.contains(point)


def removeDupesListOfLists(lst):
    dup_free = []
    dup_free_set = set()
    for x in lst:
        if tuple(x) not in dup_free_set:
            dup_free.append(x)
            dup_free_set.add(tuple(x))
    return dup_free
def printDF(df):
    print(tabulate(df, headers='keys', tablefmt='psql'))

def geometryTransform(df):
    def transform_string_vectorized(s_series):
        # Assuming 's' is a string of at least 8 characters based on the original function
        part1 = s_series.str.slice(0, 2).astype(int).astype(str)
        part2 = s_series.str.slice(2, 4).astype(int).astype(str) + s_series.str.slice(4, 5)
        part3 = s_series.str.slice(5, 7).astype(int).astype(str) + s_series.str.slice(7, 8)
        part4 = s_series.str.slice(-1)
        return part1 + ' ' + part2 + ' ' + part3 + ' ' + part4

    # Assuming 'df' is your original DataFrame with 'Conc', 'Easting', 'Northing' columns

    # Step 1: Create GeoDataFrame with Point geometries
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df['Easting'], df['Northing']),
        crs="EPSG:32612"  # Replace with your coordinate reference system
    )

    # Step 2: Group by 'Conc' and create polygons
    # Ensure that the points are ordered correctly to form valid polygons
    # This example assumes that the points are ordered; otherwise, you may need to sort them appropriately
    polygons = gdf.groupby('Conc')['geometry'].apply(
        lambda points: Polygon([(point.x, point.y) for point in points])).reset_index()

    # Convert to GeoDataFrame
    polygons_gdf = gpd.GeoDataFrame(polygons, geometry='geometry', crs=gdf.crs)

    # Step 3: Calculate centroids
    polygons_gdf['centroid'] = polygons_gdf.geometry.centroid

    # Step 4: Create labels using vectorized string transformation
    polygons_gdf['label'] = transform_string_vectorized(polygons_gdf['Conc'])

    # Optional: If you need to keep only specific columns
    df_new = polygons_gdf[['Conc', 'geometry', 'centroid', 'label']]

    #
    # def transform_string(s):
    #     part1 = str(int(s[:2]))
    #     part2 = str(int(s[2:4])) + s[4]
    #     part3 = str(int(s[5:7])) + s[7]
    #     part4 = s[-1]
    #
    #     return f"{part1} {part2} {part3} {part4}"
    # df['geometry'] = df.apply(lambda row: Point(row['Easting'], row['Northing']), axis=1)
    # used_fields = df[['Conc', 'Easting', 'Northing', 'geometry']]
    # used_fields['geometry'] = used_fields.apply(lambda row: Point(row['Easting'], row['Northing']), axis=1)
    # polygons = used_fields.groupby('Conc').apply(lambda x: Polygon(zip(x['Easting'], x['Northing']))).reset_index()
    # merged_data = used_fields.merge(polygons, on='Conc')
    # merged_data = merged_data.drop('geometry', axis=1).rename(columns={0: 'geometry'})
    # df_new = merged_data.groupby('Conc').apply(lambda x: Polygon(zip(x['Easting'], x['Northing']))).reset_index()
    #
    # df_new.columns = ['Conc', 'geometry']
    # df_new['centroid'] = df_new.apply(lambda x: x['geometry'].centroid, axis=1)
    # df_new['label'] = df_new.apply(lambda x: transform_string(x['Conc']), axis=1)
    return df_new
# def cornersProcess2(points):
#     def detect_corners(points, epsilon=0.01, min_angle=30, max_angle=150):
#         # Convert points to numpy array
#         points = np.array(points)
#
#         # Simplify the polygon using Douglas-Peucker algorithm
#         simplified = cv2.approxPolyDP(points.reshape(-1, 1, 2), epsilon * cv2.arcLength(points.reshape(-1, 1, 2), True), True)
#         simplified = simplified.reshape(-1, 2)
#
#         # Detect corners using angle criterion
#         corners = []
#         n = len(simplified)
#         for i in range(n):
#             prev = simplified[i - 1]
#             curr = simplified[i]
#             next = simplified[(i + 1) % n]
#
#             v1 = prev - curr
#             v2 = next - curr
#             angle = np.degrees(np.arctan2(np.cross(v1, v2), np.dot(v1, v2)))
#
#             if min_angle < abs(angle) < max_angle:
#                 corners.append(curr)
#
#         return np.array(corners)
#
#     def cluster_corners(corners, eps=0.01, min_samples=1):
#         # Use DBSCAN to cluster nearby corners
#         clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(corners)
#
#         # Select the point closest to the centroid for each cluster
#         refined_corners = []
#         for label in set(clustering.labels_):
#             if label == -1:  # Noise points
#                 continue
#             cluster_points = corners[clustering.labels_ == label]
#             centroid = np.mean(cluster_points, axis=0)
#             closest_point = cluster_points[np.argmin(np.sum((cluster_points - centroid) ** 2, axis=1))]
#             refined_corners.append(closest_point)
#
#         return np.array(refined_corners)
#
#     def classify_corners(corners, centroid):
#         # Classify corners as North, South, East, West
#         classifications = []
#         for corner in corners:
#             angle = np.degrees(np.arctan2(corner[1] - centroid[1], corner[0] - centroid[0]))
#             if -45 <= angle < 45:
#                 classifications.append('East')
#             elif 45 <= angle < 135:
#                 classifications.append('North')
#             elif angle >= 135 or angle < -135:
#                 classifications.append('West')
#             else:
#                 classifications.append('South')
#         return classifications
#     points = np.array(points)
#     corners = detect_corners(points)
#
#     # Refine corners through clustering
#     refined_corners = cluster_corners(corners)

def cornersProcess2(points):
    def categorize_corners(corners):
        # Sort corners by latitude (y-coordinate)
        sorted_lat = sorted(corners, key=lambda p: p[1])
        north = sorted_lat[-2:]  # Two northernmost points
        south = sorted_lat[:2]  # Two southernmost points

        # Sort corners by longitude (x-coordinate)
        sorted_lon = sorted(corners, key=lambda p: p[0])
        west = sorted_lon[:2]  # Two westernmost points
        east = sorted_lon[-2:]  # Two easternmost points

        return {'north': north, 'south': south, 'east': east, 'west': west}
    def angle_between(p1, p2, p3):
        ang = math.degrees(math.atan2(p3[1] - p2[1], p3[0] - p2[0]) - math.atan2(p1[1] - p2[1], p1[0] - p2[0]))
        return ang + 360 if ang < 0 else ang

    def find_corners_angle(points, angle_threshold=45):
        corners = []
        for i in range(len(points)):
            p1, p2, p3 = points[i - 2], points[i - 1], points[i]
            angle = angle_between(p1, p2, p3)
            if abs(180 - angle) > angle_threshold:
                corners.append(p2)
        return corners

    def find_corners_douglas_peucker(points, tolerance=50):
        line = LineString(points)
        simplified = simplify(line, tolerance)
        return list(simplified.coords)

    def find_corners_convex_hull(points):
        hull = ConvexHull(points)
        return [points[i] for i in hull.vertices]
    # Try convex hull first
    corners = find_corners_convex_hull(points)
    # If we get more than 4 corners, try angle-based approach
    if len(corners) > 4:
        corners = find_corners_angle(points)
    # If we still have issues, try Douglas-Peucker
    if len(corners) != 4:
        corners = find_corners_douglas_peucker(points)
    # Ensure we have exactly 4 corners
    corners = corners[:4] if len(corners) > 4 else corners
    # return categorize_corners(corners)

def cornerGeneratorProcess(data_lengths):
    corner_arrange = optimized_corner_process(data_lengths)
    centroid = Polygon(data_lengths).centroid
    centroid = [centroid.x, centroid.y]
    corner_arrange = reorganizeLstPointsWithAngle([i[:2] for i in corner_arrange], centroid)
    corners = sorted(corner_arrange, key=lambda r: r[-1])
    corners = removeDupesListOfLists(corners)
    data_lengths = reorganizeLstPointsWithAngle(data_lengths, centroid)
    data_lengths = sorted(data_lengths, key=lambda r: r[-1])
    data_lengths = [list(i) for i in data_lengths]
    corners = [list(i) for i in corners]
    # all_data = regularCornerClass(corners, data_lengths)
    # corners_restricted = [i[:2] for i in corners]

    nw_pt = data_lengths.index([i for i in corners if 360 > i[-1] > 270][0])
    sw_pt = data_lengths.index([i for i in corners if 90 > i[-1] > 0][0])
    se_pt = data_lengths.index([i for i in corners if 180 > i[-1] > 90][0])
    ne_pt = data_lengths.index([i for i in corners if 270 > i[-1] > 180][0])
    east_side = [i for i in data_lengths if data_lengths[ne_pt][-1] >= i[-1] >= data_lengths[se_pt][-1]][::-1]
    south_side = [i for i in data_lengths if data_lengths[se_pt][-1] >= i[-1] >= data_lengths[sw_pt][-1]][::-1]
    north_side = [i for i in data_lengths if data_lengths[nw_pt][-1] >= i[-1] >= data_lengths[ne_pt][-1]][::-1]
    west_side = copy.deepcopy(data_lengths)
    west_side = [data_lengths[sw_pt]] + [i for i in west_side if
                                         i not in east_side and i not in south_side and i not in north_side] + [
                    data_lengths[nw_pt]]
    west_side = findUniqueListsInListOfLists(west_side)
    west_side = sorted(west_side, key=lambda r: r[-2])
    east_side = remove_duplicates_preserve_order(east_side)
    north_side = remove_duplicates_preserve_order(north_side)
    south_side = remove_duplicates_preserve_order(south_side)

    all_data = [west_side] + [north_side] + [east_side] + [south_side]

    return corners, all_data


def regularCornerClass(corners, data_lengths):
    def find_corner_point(corners, min_angle, max_angle):
        return next((i for i in corners if min_angle < i[-1] <= max_angle), None)

    def find_side_points(data_lengths, start_angle, end_angle, reverse=False):
        points = [i for i in data_lengths if start_angle <= i[-1] <= end_angle]
        return remove_duplicates_preserve_order(points[::-1] if reverse else points)

    def get_side(data_lengths, corners, start_angle, end_angle, reverse=False):
        start_point = find_corner_point(corners, start_angle, end_angle)
        end_point = find_corner_point(corners, start_angle - 90, start_angle)

        if start_point is None or end_point is None:
            return []

        start_idx = data_lengths.index(start_point)
        end_idx = data_lengths.index(end_point)

        side = find_side_points(data_lengths,
                                data_lengths[end_idx][-1],
                                data_lengths[start_idx][-1],
                                reverse)

        return side

    # Main code
    south_side = get_side(data_lengths, corners, 90, 180, reverse=True)
    east_side = get_side(data_lengths, corners, 180, 270, reverse=True)
    north_side = get_side(data_lengths, corners, 270, 360, reverse=True)

    # West side needs special handling due to the angle wrap-around
    nw_point = find_corner_point(corners, 270, 360)
    sw_point = find_corner_point(corners, 0, 90)

    if nw_point is not None and sw_point is not None:
        nw_idx = data_lengths.index(nw_point)
        sw_idx = data_lengths.index(sw_point)
        west_side = [sw_point] + [i for i in data_lengths if
                                  (i[-1] > data_lengths[nw_idx][-1] or
                                   i[-1] < data_lengths[sw_idx][-1]) and
                                  i not in (east_side + south_side + north_side)] + [nw_point]
        west_side = remove_duplicates_preserve_order(west_side)
    else:
        west_side = []


    #
    # try:
    #     sw_pt = data_lengths.index([i for i in corners if 90 > i[-1] > 0][0])
    #     se_pt = data_lengths.index([i for i in corners if 180 > i[-1] > 90][0])
    #     south_side = [i for i in data_lengths if data_lengths[se_pt][-1] >= i[-1] >= data_lengths[sw_pt][-1]][::-1]
    #     south_side = remove_duplicates_preserve_order(south_side)
    # except IndexError:
    #     south_side = []
    #
    # try:
    #     se_pt = data_lengths.index([i for i in corners if 180 > i[-1] > 90][0])
    #     ne_pt = data_lengths.index([i for i in corners if 270 > i[-1] > 180][0])
    #     east_side = [i for i in data_lengths if data_lengths[ne_pt][-1] >= i[-1] >= data_lengths[se_pt][-1]][::-1]
    #     east_side = remove_duplicates_preserve_order(east_side)
    # except IndexError:
    #     east_side = []
    #
    # try:
    #     ne_pt = data_lengths.index([i for i in corners if 270 > i[-1] > 180][0])
    #     nw_pt = data_lengths.index([i for i in corners if 360 > i[-1] > 270][0])
    #     north_side = [i for i in data_lengths if data_lengths[nw_pt][-1] >= i[-1] >= data_lengths[ne_pt][-1]][::-1]
    #     north_side = remove_duplicates_preserve_order(north_side)
    # except IndexError:
    #     north_side = []
    # try:
    #     nw_pt = data_lengths.index([i for i in corners if 360 > i[-1] > 270][0])
    #     sw_pt = data_lengths.index([i for i in corners if 90 > i[-1] > 0][0])
    #     west_side = copy.deepcopy(data_lengths)
    #     west_side = [data_lengths[sw_pt]] + [i for i in west_side if
    #                                          i not in east_side and i not in south_side and i not in north_side] + [data_lengths[nw_pt]]
    # except IndexError:
    #     west_side = []
    # east_side = [i for i in data_lengths if data_lengths[ne_pt][-1] >= i[-1] >= data_lengths[se_pt][-1]][::-1]
    # south_side = [i for i in data_lengths if data_lengths[se_pt][-1] >= i[-1] >= data_lengths[sw_pt][-1]][::-1]
    # north_side = [i for i in data_lengths if data_lengths[nw_pt][-1] >= i[-1] >= data_lengths[ne_pt][-1]][::-1]
    # west_side = copy.deepcopy(data_lengths)
    # west_side = [data_lengths[sw_pt]] + [i for i in west_side if
    #                                      i not in east_side and i not in south_side and i not in north_side] + [data_lengths[nw_pt]]
    # west_side = findUniqueListsInListOfLists(west_side)
    # west_side = sorted(west_side, key=lambda r: r[-2])
    # east_side = remove_duplicates_preserve_order(east_side)
    # north_side = remove_duplicates_preserve_order(north_side)
    # south_side = remove_duplicates_preserve_order(south_side)

    all_data = [west_side] + [north_side] + [east_side] + [south_side]
    return all_data


def wrapDataRotate(poly):
    used_data = [utm.from_latlon(i[0], i[1])[:2] for i in poly]
    polygon = Polygon(used_data)
    centroid = polygon.centroid

    # Calculate the centroid (in this case, outside the polygon)
    # centroid = Point(10, 0)
    # Calculate the angle between each vertex and the centroid

    angles = [np.arctan2(vertex[1] - centroid.y, vertex[0] - centroid.x) for vertex in polygon.exterior.coords[:-1]]
    # Sort the vertices based on the angles
    sorted_coords = [coord for _, coord in sorted(zip(angles, polygon.exterior.coords[:-1]))]
    # Create a new polygon with the sorted vertices
    # sorted_polygon = Polygon(sorted_coords)
    return sorted_coords


def calculate_bearing_latlon(point1, point2):
    # point1, point2 = (40.27327256666666, -109.944426225), (40.273272649999996, -109.93969608333333)
    lat1, lon1 = math.radians(point1[0]), math.radians(point1[1])
    lat2, lon2 = math.radians(point2[0]), math.radians(point2[1])
    delta_lon = lon2 - lon1
    x = math.sin(delta_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon))

    initial_bearing = math.atan2(x, y)

    # Convert the bearing from radians to degrees
    initial_bearing = math.degrees(initial_bearing)

    # Normalize the bearing to the range [0, 360)
    initial_bearing = (initial_bearing + 360) % 360
    return initial_bearing


def calculate_bearing(point1, point2):
    # point1 and point2 are tuples (easting, northing, zone_number, zone_letter)
    delta_easting = point2[0] - point1[0]
    delta_northing = point2[1] - point1[1]

    # Calculate the initial bearing using arctan2
    bearing = math.atan2(delta_easting, delta_northing)

    # Convert bearing to degrees
    bearing = math.degrees(bearing)

    # Adjust the bearing to be in the range [0, 360)
    bearing = (bearing + 360) % 360

    return bearing


def find_closest_latlon(target_latlon, latlon_list, threshold_distance=0.001):
    """
    Find the closest latitude-longitude pair in a list to the target pair.

    Parameters:
    - target_latlon: Tuple (latitude, longitude) of the target point.
    - latlon_list: List of tuples (latitude, longitude) representing candidate points.
    - threshold_distance: Maximum distance (in kilometers) for a match.

    Returns:
    - closest_latlon: Tuple (latitude, longitude) of the closest point.
    - index: Index of the closest point in the list, or None if no match is found.
    """
    closest_latlon = None
    min_distance = float('inf')
    index = None

    for i, latlon in enumerate(latlon_list):
        distance = geodesic(target_latlon, latlon).kilometers
        if distance < min_distance and distance < threshold_distance:
            min_distance = distance
            closest_latlon = latlon
            index = i

    return closest_latlon, index


def remove_duplicates_preserve_order(points_list):
    seen = set()
    result = []

    for point in points_list:
        point_tuple = tuple(point)
        if point_tuple not in seen:
            result.append(point_tuple)
            seen.add(point_tuple)

    return result


def corners2(data):
    polygon = Polygon(data)
    simplified_polygon = polygon.simplify(0.1, preserve_topology=True)
    x, y = polygon.exterior.xy
    x_simplified, y_simplified = simplified_polygon.exterior.xy

    # Create a figure and axis
    fig, ax = plt.subplots(1, 1, figsize=(8, 6))

    # Plot the original polygon
    ax.plot(x, y, label="Original Polygon", color='blue', linewidth=0.5)

    # Plot the simplified polygon
    ax.plot(x_simplified, y_simplified, label="Simplified Polygon", color='red', linewidth=1)

    # Add labels and legend
    ax.set_title("Original vs. Simplified Polygon")
    ax.legend()

    # Show the plot
    plt.show()
    pass


def sortPointsInClockwisePattern(coords):
    center = tuple(map(operator.truediv, reduce(lambda x, y: map(operator.add, x, y), coords), [len(coords)] * 2))
    output = sorted(coords, key=lambda coord: (-135 - math.degrees(
        math.atan2(*tuple(map(operator.sub, coord, center))[::-1]))) % 360)
    return output


def geopandas_corner_process(trajectory):
    # Create a GeoDataFrame from the trajectory
    gdf = gpd.GeoDataFrame(geometry=[Polygon(trajectory)])

    # Simplify the polygon
    simplified = gdf.simplify(tolerance=200)

    # Get the exterior coordinates of the simplified polygon
    coords = list(simplified.geometry.iloc[0].exterior.coords)

    # Calculate centroid
    centroid = simplified.centroid.iloc[0]

    # Calculate angles from centroid
    angles = [
        (np.degrees(np.arctan2(y - centroid.y, x - centroid.x)) + 360) % 360
        for x, y in coords[:-1]  # Exclude the last point as it's the same as the first
    ]

    # Combine coordinates and angles
    result = [(x, y, angle) for (x, y), angle in zip(coords[:-1], angles)]

    return result


def optimized_corner_process(trajectory):
    # Convert trajectory to numpy array
    trajectory = np.array(trajectory)

    # Calculate centroid
    centroid = Polygon(trajectory).centroid.coords[0]

    # Use ConvexHull for clockwise sorting
    hull = ConvexHull(trajectory)
    trajectory = trajectory[hull.vertices]

    # Simplify trajectory
    epsilon = 0.002 if (35 < trajectory[0, 0] < 55 or 35 < trajectory[0, 1] < 55) else 200
    simplified = rdp(np.vstack((trajectory, trajectory[0])), epsilon=epsilon)

    # Calculate angles
    vectors = np.diff(simplified, axis=0)
    angles = np.arctan2(vectors[:, 1], vectors[:, 0])
    angle_diffs = np.diff(angles, append=angles[0] - 2 * np.pi)
    angle_diffs = np.abs(np.where(angle_diffs > np.pi, angle_diffs - 2 * np.pi, angle_diffs))

    # Find corners
    corners = simplified[1:][angle_diffs > np.pi / 35]

    # Calculate angles from centroid
    centroid_vectors = corners - centroid
    centroid_angles = (np.degrees(np.arctan2(centroid_vectors[:, 1], centroid_vectors[:, 0])) + 360) % 360

    # Combine coordinates and angles
    result = np.column_stack((corners, centroid_angles))

    return result.tolist()


def cornerProcess(trajectory):

    centroid = Polygon(trajectory).centroid
    centroid = [centroid.x, centroid.y]
    trajectory = sortPointsInClockwisePattern(trajectory)
    # Duplicate trajectories
    trajectory = trajectory + trajectory

    old_traj = copy.deepcopy(trajectory)
    trajectory.append(trajectory[0])
    trajectory = np.array(trajectory)
    episole_foo = 200
    if 55 > trajectory[0][0] > 35 or 55 > trajectory[0][1] > 35:
        episole_foo = 0.002
    simplified_trajectory = rdp(trajectory, epsilon=episole_foo)
    sx, sy = simplified_trajectory.T

    min_angle = np.pi / 35
    directions = np.diff(simplified_trajectory, axis=0)
    theta = angleCornerProcess(directions)
    idx = np.where(theta > min_angle)[0] + 1

    data = list(zip(sx[idx].tolist(), sy[idx].tolist()))
    data = [list(i) for i in data]
    data = [i + [(math.degrees(math.atan2(centroid[1] - i[1], centroid[0] - i[0])) + 360) % 360] for i in data]
    data = [tuple(i) for i in data]
    trajectory_data = []
    for i in old_traj:
        trajectory_data.append(list(i) + [(math.degrees(math.atan2(centroid[1] - i[1], centroid[0] - i[0])) + 360) % 360])

    index_lst = []
    if len(data) == 3:
        for i in data:
            index_lst.append(trajectory_data.index(i))
        diff_lst = np.diff(sorted(index_lst))
        all_indexes = cycleIndexes(index_lst, diff_lst, len(trajectory_data))
        data = [trajectory_data[i] for i in all_indexes]
    # Create a figure and axis
    # fig, ax = plt.subplots(1, 1, figsize=(8, 6))
    # x, y = [i[0] for i in trajectory], [i[1] for i in trajectory]
    # x2, y2 = [i[0] for i in data], [i[1] for i in data]
    # # Plot the original polygon
    # ax.plot(x, y, label="Original Polygon", color='blue', linewidth = 0.5)
    # ax.scatter(x2, y2, label="Original Polygon", color='red')
    # # Plot the simplified polygon
    # # ax.plot(x_simplified, y_simplified, label="Simplified Polygon", color='red', linewidth = 1)
    #
    # # Add labels and legend
    # ax.set_title("Original vs. Simplified Polygon")
    # ax.legend()
    #
    # # Show the plot
    # plt.show()
    return data


def cycleIndexes(index_lst, diff_lst, total_length):
    extra_values = []
    diff_val = list(set(diff_lst))[0]

    for i in range(index_lst[0], total_length, diff_val):
        extra_values.append(i)
    for i in range(index_lst[0], 0, -1 * diff_val):
        extra_values.append(i)
    extra_values = [i for i in extra_values if i >= 0]
    extra_values = list(set(extra_values))
    extra_values = sorted(extra_values)
    return extra_values


def angleCornerProcess(directions):
    """Return the angle between vectors
    """
    vec2 = directions[1:]
    vec1 = directions[:-1]

    norm1 = np.sqrt((vec1 ** 2).sum(axis=1))
    norm2 = np.sqrt((vec2 ** 2).sum(axis=1))
    cos = (vec1 * vec2).sum(axis=1) / (norm1 * norm2)
    return np.arccos(cos)


def angleFinder(directions):
    """Return the angle between vectors
    """
    vec2 = directions[1:]
    vec1 = directions[:-1]

    norm1 = np.sqrt((vec1 ** 2).sum(axis=1))
    norm2 = np.sqrt((vec2 ** 2).sum(axis=1))
    cos = (vec1 * vec2).sum(axis=1) / (norm1 * norm2)
    return np.arccos(cos)


def reorganizeLstPointsWithAngle(lst, centroid):

    lst_arrange = [tuple(i) + ((math.degrees(math.atan2(centroid[1] - i[1], centroid[0] - i[0])) + 360) % 360,) for i in lst]
    return lst_arrange


def haversineWithXYDistance(lat1, lon1, distance_x, distance_y):
    # Earth radius in kilometers
    earth_radius = 6371.0088

    # Convert latitude and longitude from degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)

    # Convert distances from meters to kilometers
    distance_x_km = distance_x / 1000.0
    distance_y_km = distance_y / 1000.0

    # Calculate new latitude
    new_lat_rad = lat1_rad + (distance_y_km / earth_radius)

    # Calculate new longitude
    new_lon_rad = lon1_rad + (distance_x_km / (earth_radius * math.cos(lat1_rad)))

    # Convert latitude and longitude back to degrees
    new_lat = math.degrees(new_lat_rad)
    new_lon = math.degrees(new_lon_rad)

    return new_lat, new_lon


def arrangeDirectionData(corner, lst, label, centroid):
    found_side_data = []
    x_lst, y_lst = [i[0] for i in lst], [i[1] for i in lst]
    if label == 'west':
        xy1, xy2 = corner[0], corner[3]

    if label == 'north':
        xy1, xy2 = corner[3], corner[2]
    if label == 'east':
        xy1, xy2 = corner[2], corner[1]
    if label == 'south':
        xy1, xy2 = corner[1], corner[0]

    index1 = x_lst.index(xy1[0])
    index2 = x_lst.index(xy2[0])
    index2 = len(x_lst) if index2 == 0 else index2
    if index1 < index2:
        found_side_data_foo = lst[index1:index2 + 1]
    else:
        found_side_data_foo = lst[:index2 + 1]
    #

    angles = [xy1[-1], xy2[-1]]
    found_side_data.append(xy1)

    x_gap = abs(xy1[0] - abs(xy2[0]))
    for i in lst:
        if label == 'west':
            if 360 > i[-1] > max(angles) or min(angles) > i[-1] > 0:
                found_side_data.append(i)
        else:
            if max(angles) > i[-1] > min(angles):
                found_side_data.append(i)
    found_side_data.append(xy2)
    return found_side_data_foo


def organizeBoundsToPoints(bounds):
    nw = [bounds[0], bounds[3]]
    ne = [bounds[2], bounds[3]]
    sw = [bounds[0], bounds[1]]
    se = [bounds[2], bounds[1]]
    return nw, ne, sw, se


def determinePointProximity(bounds, lst):
    distance_lst = []
    for i in bounds:
        min_distance = 9999999
        dist_pt = []
        for j in lst:
            distance = findSegmentLength(i, j)
            if distance < min_distance:
                min_distance = distance
                dist_pt = j
        distance_lst.append(dist_pt)
    return distance_lst


def checkClockwisePts(coords):
    center = tuple(map(operator.truediv, reduce(lambda x, y: map(operator.add, x, y), coords), [len(coords)] * 2))
    output = sorted(coords, key=lambda coord: (-135 - math.degrees(
        math.atan2(*tuple(map(operator.sub, coord, center))[::-1]))) % 360)
    return output


def flatten(lst):
    if len(lst) == 1:
        if type(lst[0]) == list:
            result = flatten(lst[0])
        else:
            result = lst

    elif type(lst[0]) == list:
        result = flatten(lst[0]) + flatten(lst[1:])

    else:
        result = [lst[0]] + flatten(lst[1:])

    return result


# def transformPlatDataTowardsData(output, control_point, new_pt):
#     original_quad_points = np.array(output, dtype=np.float32)
#     original_center_point = np.array([control_point[0], control_point[1]], dtype=np.float32)
#     new_center_point = np.array([new_pt[0], new_pt[1]], dtype=np.float32)
#     translation_matrix = np.array([[1, 0, new_center_point[0] - original_center_point[0]],
#                                    [0, 1, new_center_point[1] - original_center_point[1]]], dtype=np.float32)
#     transformed_quad_points = cv2.transform(original_quad_points.reshape(1, -1, 2), translation_matrix).reshape(-1, 2).tolist()
#     return transformed_quad_points


def testRecovert(data_converted):
    data_original = []
    for i in range(len(data_converted)):
        side, decVal = data_converted[i]
        direction = ""

        if decVal >= 0 and decVal < 90:
            direction = "North"
            dir_val = 2 if decVal < 45 else 3
            dec_val_base = decVal
        elif decVal >= 90 and decVal < 180:
            direction = "West"
            dir_val = 1 if decVal < 135 else 4
            dec_val_base = 180 - decVal
        elif decVal >= 180 and decVal < 270:
            direction = "South"
            dir_val = 2 if decVal < 225 else 3
            dec_val_base = decVal - 180
        else:
            direction = "East"
            dir_val = 1 if decVal < 315 else 4
            dec_val_base = 360 - decVal

        deg = int(dec_val_base)
        min_val = int((dec_val_base - deg) * 60)
        sec_val = (dec_val_base - deg - min_val / 60) * 3600

        data_original.append([side, direction, deg, min_val, sec_val, dir_val])

    return data_original


def convertToDecimal(data):
    data_converted = []
    for i in range(len(data)):
        if len(data[i]) == 8:
            data[i] = data[i][:-2]
        elif len(data[i]) > 6:
            data[i] = data[i][6:12]
            data[i][1] = float(data[i][1])
        side, deg, min, sec, dir_val = float(data[i][1]), float(data[i][2]), float(data[i][3]), float(
            data[i][4]), float(data[i][5])
        dec_val_base = (deg + min / 60 + sec / 3600)
        if 'west' in data[i][0].lower():
            if dir_val in [4, 1]:
                decVal = 90 + dec_val_base
            else:
                decVal = 90 - dec_val_base
        if 'east' in data[i][0].lower():
            if dir_val in [4, 1]:
                decVal = 270 + dec_val_base
            else:
                decVal = 270 - dec_val_base
        if 'north' in data[i][0].lower():
            if dir_val in [3, 2]:
                decVal = 360 - (270 + dec_val_base)
            else:
                decVal = 270 + dec_val_base
        if 'south' in data[i][0].lower():
            if dir_val in [4, 1]:
                decVal = 90 + dec_val_base
            else:
                decVal = 360 - (90 + dec_val_base)
        data_converted.append([side, decVal])

    return data_converted


def dataConverterPlatToUtm(data):
    output = convertToDecimal2(data)
    data_converted = calculate_next_utm_points(output)
    return data_converted, output


def convertToDecimal2(data):
    data_converted = []
    for item in data:
        if len(item) > 6:
            item = item[6:12]
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


def correctPlatSidesAzimuths(label, data, direction):
    if 'west' in label.lower():
        output = 180 - data


def find_third_point(x1, y1, x2, y2):
    dy = y1 - y2
    dx = x1 - x2
    angle_rad = math.atan2(y2 - y1, x2 - x1)

    # Convert radians to degrees
    angle_deg = math.degrees(angle_rad)
    azimuth = math.degrees(math.atan2(dy, dx))

    # Adjust the azimuth to be in the range [0, 360)
    azimuth = (azimuth + 360) % 360

    # output = slopeFinder([x1, y1], [y1, y2])
    # Calculate the distance (hypotenuse length)
    # d = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
    #
    # # Calculate the change in x and y
    # dx = (x2 - x1) / d
    # dy = (y2 - y1) / d
    #
    # # Calculate the coordinates of the third point
    # x3 = x1 - dy * d
    # y3 = y1 + dx * d
    #
    # return x3, y3


def angleBetweenPoints(pt1, pt2):
    x1, y1 = pt1[0], pt1[1]
    x2, y2 = pt2[0], pt2[1]
    angle_rad = math.atan2(y2 - y1, x2 - x1)

    # Convert radians to degrees
    angle_deg = math.degrees(angle_rad)
    # Adjust the azimuth to be in the range [0, 360)
    azimuth_degrees = (angle_deg + 360) % 360
    return azimuth_degrees


# def test_convert(data):
#     degrees, minutes, seconds, direction = data[0], data[1], data[2], data[3]
#     if degrees == "":
#         result = 0
#     elif direction in [1, 4]:
#         result = 180 - (degrees + minutes / 60 + seconds / 3600)
#     else:
#         result = degrees + minutes / 60 + seconds / 3600
#     # return result
#     return [round(degrees + minutes / 60 + seconds / 3600,4), round(180 - (degrees + minutes / 60 + seconds / 3600),4)]
# data_converted = []
# for i in range(len(data)):
#
#     if len(data[i]) > 6:
#         data[i] = data[i][6:12]
#         data[i][1] = float(data[i][1])
#     side, deg, min, sec, dir_val = float(data[i][1]), float(data[i][2]), float(data[i][3]), float(data[i][4]), float(data[i][5])
#     dec_val_base = (deg + min / 60 + sec / 3600)
#
#     if 'west' in data[i][0].lower():
#         if dir_val in [4, 1]:
#             decVal = dec_val_base
#         elif int(dec_val_base) in [180,0,360,90]:
#             decVal = 0
#         else:
#             decVal = 360 - dec_val_base
#     if 'east' in data[i][0].lower():
#         if dir_val in [4, 1]:
#             decVal = 180 + dec_val_base
#         elif int(dec_val_base) in [180, 0, 360, 90]:
#             decVal = 180
#         else:
#             decVal = 180 - dec_val_base
#     if 'north' in data[i][0].lower():
#         if dir_val in [4, 1]:
#             decVal = (90 - dec_val_base) + 90
#         elif int(dec_val_base) in [180, 0, 360, 90]:
#             decVal = 90
#         else:
#             decVal = 180 - dec_val_base
#     if 'south' in data[i][0].lower():
#         if dir_val in [4, 1]:
#             decVal = (90 - dec_val_base) + 270
#         elif int(dec_val_base) in [180, 0, 360, 90]:
#             decVal = 270
#         else:
#             decVal = 360 - dec_val_base
#     data_converted.append([side, decVal])
# return data_converted
# def convertToDecimal(data):
#     data_converted = []
#     for i in range(len(data)):
#         if len(data[i]) > 6:
#             data[i] = data[i][6:12]
#             data[i][1] = float(data[i][1])
#         direction = data[i][0].lower()
#         side, deg, min, sec, dir_val = [float(x) for x in data[i][1:]]
#         dec_val_base = (deg + min / 60 + sec / 3600)
#         if 'west' in direction:
#             decVal = 90 - dec_val_base if dir_val not in [4, 1] else 90 + dec_val_base
#         elif 'east' in direction:
#             decVal = 270 - dec_val_base if dir_val not in [4, 1] else 270 + dec_val_base
#         elif 'north' in direction:
#             decVal = 270 + dec_val_base if dir_val in [1, 4] else 360 - (270 + dec_val_base)
#         elif 'south' in direction:
#             decVal = 90 + dec_val_base if dir_val not in [4, 1] else 360 - (90 + dec_val_base)
#         data_converted.append([side, decVal])
#     return data_converted


# 1322.71

# def statePlaneConversion(utm_data):
#     warnings.filterwarnings('ignore')
#     utm_easting = utm_data[0]
#     utm_northing = utm_data[1]
#     lat, lon = utm.to_latlon(utm_easting, utm_northing, 12, 'T')
#     epsg_sp, name_sp = sp.identify(lon, lat), sp.identify(lon, lat, 'short')
#     utm_proj = Proj(proj='utm', zone=12, datum='WGS84', ellps='WGS84')
#     state_plane_proj = Proj(init=f'epsg:{epsg_sp}', preserve_units=False)
#     state_plane_easting, state_plane_northing = transform(utm_proj, state_plane_proj, utm_easting, utm_northing)
#     state_plane_easting, state_plane_northing = state_plane_easting / 0.3048, state_plane_northing / 0.3048
#
#
#     return state_plane_easting, state_plane_northing

def statePlaneConversion2(data):
    state_plane_easting = data[0]
    state_plane_northing = data[1]
    # Unit Conversion (US Survey Feet to Feet)
    state_plane_easting = state_plane_easting * 0.3048
    state_plane_northing = state_plane_northing * 0.3048

    # Define projection objects
    utm_proj = Proj(proj='utm', zone=12, datum='WGS84', ellps='WGS84')
    state_plane_proj = Proj(init=f'epsg:{32143}', preserve_units=False)

    # State Plane to UTM Transformation
    utm_easting, utm_northing = transform(state_plane_proj, utm_proj, state_plane_easting, state_plane_northing)

    return Point(utm_easting, utm_northing)


def pointsConverter(data):
    data = reorderDecimalData(data)
    data = oneToMany(data, 4)
    x_pts, y_pts = [], []
    x, y = 0, 0
    foo_lst = []
    for i in range(len(data)):
        foo_lst.append([])
        for j in range(len(data[i])):
            x_pts.append(x)
            y_pts.append(y)
            foo_lst[-1].append([x, y])
            x, y = pointLineFinder(data[i][j], x, y)
    x_pts.append(x)
    y_pts.append(y)
    output = list(zip(x_pts, y_pts))
    output = [list(i) for i in output]
    return output


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


def calculateBearingToAzimuth(bearing):
    # Split the input bearing into degrees, minutes, and seconds

    direction, degrees, minutes, seconds = bearing[11], int(bearing[8]), int(bearing[9]), float(bearing[10])
    direction = translateNumberToDirection('alignment', str(direction)).upper()
    azimuth = degrees + minutes / 60 + seconds / 3600
    if direction.lower() == 'nw':
        output = 45 - azimuth
    elif direction.lower() == 'sw':
        output = 225 + azimuth
    elif direction.lower() == 'ne':
        output = 45 - azimuth
    elif direction.lower() == 'se':
        output = 135 + azimuth
    return output
    # # Convert minutes and seconds to decimal degrees
    # decimal_minutes = minutes / 60.0
    # decimal_seconds = seconds / 3600.0
    #
    # # Calculate the azimuth
    # if direction in ['N', 'S']:
    #     hemisphere = direction
    #     azimuth = 360 - degrees - decimal_minutes - decimal_seconds if direction == 'W' else degrees + decimal_minutes + decimal_seconds
    # elif direction in ['NE', 'SE', 'SW', 'NW']:
    #     azimuth = {'NE': 45, 'SE': 135, 'SW': 225, 'NW': 315}[direction]
    # else:
    #     raise ValueError("Invalid direction. Use 'N', 'S', 'NE', 'SE', 'SW', or 'NW'.")

    # return azimuth


# def convertAnglesRight(angle):
#     angle = angle % 360
#     if 90 > angle > 0:
#         pass
#     if 180 > angle > 90:
#         pass
#     if 270 > angle > 180:
#         pass
#     if 360 > angle > 270:
#         pass


def bearingToAzimuth(bearing):
    labels = {1: 'SE', 2: 'NE', 3: 'SW', 4: 'NW'}
    decimal_degrees = round(float(bearing[0]) + float(bearing[1]) / 60 + float(bearing[2]) / 3600, 7)
    label = labels[bearing[3]]
    converted_value = label[0] + str(decimal_degrees) + label[1]
    factors = {'NE': [0, 1], 'SE': [180, -1], 'SW': [180, 1], 'NW': [360, -1]}
    f = converted_value[0] + converted_value[-1]
    azimuth = factors[f][0] + (float(converted_value.strip('NESW')) * factors[f][1])
    return azimuth


def bearingToAzimuth2(bearing, dir):
    labels = {1: 'SE', 2: 'NE', 3: 'SW', 4: 'NW'}
    decimal_degrees = round(float(bearing[0]) + float(bearing[1]) / 60 + float(bearing[2]) / 3600, 7)
    label = labels[bearing[3]]
    if 'north' in dir.lower():
        if label == 'NE':
            label = 'SW'
        elif label == 'SE':
            label = 'NW'
    elif 'west' in dir.lower():
        if label == 'NW':
            label = 'SE'
        elif label == 'NE':
            label = 'SW'
    elif 'south' in dir.lower():
        if label == 'SW':
            label = 'NE'
        elif label == 'NW':
            label = 'SE'
    elif 'east' in dir.lower():
        if label == 'SW':
            label = 'NE'
        elif label == 'SE':
            label = 'NW'

    # if 'north' in dir.lower() or 'west' in dir.lower():
    #     if label == 'NE':
    #         label = 'SW'
    #     elif label == 'SE':
    #         label = 'NW'
    # elif 'south' in dir.lower() or 'east' in dir.lower():
    #     if label == 'SW':
    #         label = 'NE'
    #     elif label == 'NW':
    #         label = 'SE'
    converted_value = label[0] + str(decimal_degrees) + label[1]
    factors = {'NE': [0, 1], 'SE': [180, -1], 'SW': [180, 1], 'NW': [360, -1]}
    f = converted_value[0] + converted_value[-1]
    azimuth = factors[f][0] + (float(converted_value.strip('NESW')) * factors[f][1])
    return azimuth


def azimuthToBearing(azimuth):
    if 360 >= data > 270:
        quadrant, val = 4, 360 - data
    elif 270 >= data > 180:
        quadrant, val = 3, data - 180
    elif 180 >= data > 90:
        quadrant, val = 1, 180 - data
    else:
        quadrant, val = 2, data
    val = convertDecimalToDegrees(val)

    return val + [quadrant]


def convertPtsToSides(pts, tsr_data, conc_data):
    degrees_lst = []
    dirLst = [['West-Up2', 'West-Up1', 'West-Down1', 'West-Down2'],
              ['East-Up2', 'East-Up1', 'East-Down1', 'East-Down2'],
              ['North-Left2', 'North-Left1', 'North-Right1', 'North-Right2'],
              ['South-Left2', 'South-Left1', 'South-Right1', 'South-Right2']]
    pts_west, pts_north, pts_east, pts_south = pts

    # (500000, 5360194.4)
    # tst_1, tst_2 = [pts_west[0][1] + 500000, pts_west[0][0] + 5360194], [pts_west[1][1] + 500000, pts_west[1][0] + 5360194]
    # ll1, ll2 = utm.to_latlon(tst_1[0], tst_1[1], 12, 'T'), utm.to_latlon(tst_2[0], tst_2[1], 12, 'T')
    # latlon_azi = Geod(ellps='GRS80').inv(ll2[1], ll2[0], ll1[1], ll1[0])
    # side_data_dec = [latlon_azi[1:][::-1]]
    # reversed_data = [[i[0], (450 - i[1]) % 360] for i in side_data_dec]
    for i in range(len(pts_south) - 1):
        if equationDistance(pts_south[i][0], pts_south[i][1], pts_south[i + 1][0], pts_south[i + 1][1]) < 10:
            pts_south[i] = pts_south[i + 1]
    pts_south = remove_duplicates_preserve_order(pts_south)

    lens_w = angleAndLengths(pts_west)
    lens_n = angleAndLengths(pts_north)
    lens_e = angleAndLengths(pts_east)
    lens_s = angleAndLengths(pts_south)

    lens_w = lens_w[::-1]
    lens_s = lens_s[::-1]

    tsr_data[2] = translateDirectionToNumber('township', str(tsr_data[2])).upper()
    tsr_data[4] = translateDirectionToNumber('rng', str(tsr_data[4])).upper()
    tsr_data[5] = translateDirectionToNumber('baseline', str(tsr_data[5])).upper()
    tsr_data = [int(float(i)) for i in tsr_data]

    directions = ['West', 'East', 'South', 'North']
    positions = ['Up2', 'Up1', 'Down1', 'Down2']

    # Create simplified lists using loops and string formatting
    sides = [[0, 0, 0, 0, 0, 0, f'{dir}-{pos}', 0, 0, 0, 0, 0, '', '', ''] for dir in directions for pos in positions]
    side_w, side_e, side_s, side_n = oneToMany(sides, 4)
    # side_w = [[0, 0, 0, 0, 0, 0, 'West-Up2', 0, 0, 0, 0, 0, '', '', ''],
    #           [0, 0, 0, 0, 0, 0, 'West-Up1', 0, 0, 0, 0, 0, '', '', ''],
    #           [0, 0, 0, 0, 0, 0, 'West-Down1', 0, 0, 0, 0, 0, '', '', ''],
    #           [0, 0, 0, 0, 0, 0, 'West-Down2', 0, 0, 0, 0, 0, '', '', '']]
    # side_e = [[0, 0, 0, 0, 0, 0, 'East-Up2', 0, 0, 0, 0, 0, '', '', ''],
    #           [0, 0, 0, 0, 0, 0, 'East-Up1', 0, 0, 0, 0, 0, '', '', ''],
    #           [0, 0, 0, 0, 0, 0, 'East-Down1', 0, 0, 0, 0, 0, '', '', ''],
    #           [0, 0, 0, 0, 0, 0, 'East-Down2', 0, 0, 0, 0, 0, '', '', '']]
    # side_s = [[0, 0, 0, 0, 0, 0, 'South-Left2', 0, 0, 0, 0, 0, '', '', ''],
    #           [0, 0, 0, 0, 0, 0, 'South-Left1', 0, 0, 0, 0, 0, '', '', ''],
    #           [0, 0, 0, 0, 0, 0, 'South-Right1', 0, 0, 0, 0, 0, '', '', ''],
    #           [0, 0, 0, 0, 0, 0, 'South-Right2', 0, 0, 0, 0, 0, '', '', '']]
    # side_n = [[0, 0, 0, 0, 0, 0, 'North-Left2', 0, 0, 0, 0, 0, '', '', ''],
    #           [0, 0, 0, 0, 0, 0, 'North-Left1', 0, 0, 0, 0, 0, '', '', ''],
    #           [0, 0, 0, 0, 0, 0, 'North-Right1', 0, 0, 0, 0, 0, '', '', ''],
    #           [0, 0, 0, 0, 0, 0, 'North-Right2', 0, 0, 0, 0, 0, '', '', '']]
    south_lst, west_lst, east_lst, north_lst = [], [], [], []
    for i in range(len(lens_w)):
        degrees = reconvertToDegrees(lens_w[i][1], 'west')
        degrees_lst.append(tsr_data + [dirLst[0][i]] + [lens_w[i][0]] + degrees + ["T"] + [conc_data])
        west_lst.append(tsr_data + [dirLst[0][i]] + [lens_w[i][0]] + degrees + ["T"] + [conc_data])
    for i in range(len(lens_e)):
        degrees = reconvertToDegrees(lens_e[i][1], 'east')
        degrees_lst.append(tsr_data + [dirLst[1][i]] + [lens_e[i][0]] + degrees + ["T"] + [conc_data])
        east_lst.append(tsr_data + [dirLst[1][i]] + [lens_e[i][0]] + degrees + ["T"] + [conc_data])

    for i in range(len(lens_n)):
        degrees = reconvertToDegrees(lens_n[i][1], 'north')
        degrees_lst.append(tsr_data + [dirLst[2][i]] + [lens_n[i][0]] + degrees + ["T"] + [conc_data])
        north_lst.append(tsr_data + [dirLst[2][i]] + [lens_n[i][0]] + degrees + ["T"] + [conc_data])

    for i in range(len(lens_s)):
        degrees = reconvertToDegrees(lens_s[i][1], 'south')
        south_lst.append(tsr_data + [dirLst[3][i]] + [lens_s[i][0]] + degrees + ["T"] + [conc_data])
        degrees_lst.append(tsr_data + [dirLst[3][i]] + [lens_s[i][0]] + degrees + ["T"] + [conc_data])

    west_lst = sortSideData(west_lst, side_w)
    east_lst = sortSideData(east_lst, side_e)
    north_lst = sortSideData(north_lst, side_n)
    south_lst = sortSideData(south_lst, side_s)

    degrees_lst = west_lst + east_lst + north_lst + south_lst
    return degrees_lst


def sortSideData(lst, sides):
    if len(lst) == 1:
        sides[1] = lst[0]
        sides[0] = sides[1][:6] + sides[0][6:-3] + sides[1][-2:]
        sides[2] = sides[1][:6] + sides[2][6:-3] + sides[1][-2:]
        sides[3] = sides[1][:6] + sides[3][6:-3] + sides[1][-2:]

    elif len(lst) == 2:
        sides[1] = lst[0]
        sides[2] = lst[1]
        sides[0] = sides[1][:6] + sides[0][6:-3] + sides[1][-2:]
        sides[3] = sides[1][:6] + sides[3][6:-3] + sides[1][-2:]

    elif len(lst) == 3:
        if lst[0][7] > lst[-1][7]:
            sides[1] = lst[0]
            sides[2] = lst[1]
            sides[3] = lst[2]
            sides[0] = sides[1][:6] + sides[0][6:-3] + sides[1][-2:]

        else:
            sides[0] = lst[0]
            sides[1] = lst[1]
            sides[2] = lst[2]
            sides[3] = sides[1][:6] + sides[3][6:-2] + sides[1][-2:]
    elif len(lst) == 4:
        sides = lst

    return sides


def angleAndLengths(lst):
    alLst = []
    for i in range(len(lst) - 1):
        test = equationDistance(lst[i][0], lst[i][1], lst[i + 1][0], lst[i + 1][1])
        point1_ll = (utm.to_latlon(lst[i][0], lst[i][1], 12, 'T'))
        point2_ll = (utm.to_latlon(lst[i + 1][0], lst[i + 1][1], 12, 'T'))

        fwd_azimuth, back_azimuth, distance = Geod(ellps='WGS84').inv(point1_ll[1], point1_ll[0], point2_ll[1],
                                                                      point2_ll[0])
        pt1, pt2 = Point(lst[i]), Point(lst[i + 1])
        angle = (math.degrees(math.atan2(lst[i][1] - lst[i + 1][1], lst[i][0] - lst[i + 1][0])) + 360) % 360
        d = round(pt1.distance(pt2) / 0.3048, 2)
        alLst.append([d, angle])
    return alLst


def reconvertToDegrees(decVal, data):
    if data == 'west':
        decimal_value = abs(decVal - 270)
        if decVal < 270:
            dir_val = 3
        else:
            dir_val = 4
        deg_val = convertDecimalToDegrees(decimal_value)
    if data == 'east':  # or data == 'west':
        decimal_value = abs(90 - decVal)
        if decVal < 90:
            dir_val = 3
        else:
            dir_val = 4
        deg_val = convertDecimalToDegrees(decimal_value)
    if data == 'north':  # or data == 'south':
        if decVal < 180:
            decimal_value = abs(90 - decVal)
            dir_val = 4
        else:
            decimal_value = 90 - abs(180 - decVal)
            dir_val = 3
        deg_val = convertDecimalToDegrees(decimal_value)
    if data == 'south':
        data_360 = math.isclose(360, decVal, abs_tol=50)
        data_0 = math.isclose(0, decVal, abs_tol=50)
        if data_360 and not data_0:
            decimal_value = abs(decVal - 270)
            dir_val = 4
        elif not data_360 and data_0:
            decimal_value = abs(90 - decVal)
            dir_val = 3
        elif decVal < 90:
            decimal_value = abs(90 - decVal)
            dir_val = 3
        else:
            decimal_value = abs(decVal - 270)
            dir_val = 4
        deg_val = convertDecimalToDegrees(decimal_value)
    return list(deg_val) + [dir_val]


def changeAngles(label, angle, found_side_data):
    if label.lower() == 'west':
        if 360 > angle > 220:
            pass
        elif 150 > angle > 50:
            pass


def reassemble(lst):
    w_lst, n_lst, e_lst, s_lst = lst
    w_lst = [tuple(i) for i in w_lst]
    n_lst = [tuple(i) for i in n_lst]
    e_lst = [tuple(i) for i in e_lst]
    s_lst = [tuple(i) for i in s_lst]

    west_north_connector_pt = w_lst[-1]
    n_lst = [[i[0] + west_north_connector_pt[0], i[1] + west_north_connector_pt[1]] for i in n_lst]
    west_south_connector_pt = s_lst[-1]
    s_lst = [[i[0] - west_south_connector_pt[0], i[1] - west_south_connector_pt[1]] for i in s_lst]

    north_east_connector_pt = n_lst[-1]
    e_lst = [[i[0] + north_east_connector_pt[0], i[1] + north_east_connector_pt[1]] for i in e_lst]

    w_lst = [tuple(i) for i in w_lst]
    n_lst = [tuple(i) for i in n_lst]
    e_lst = [tuple(i) for i in e_lst]
    s_lst = [tuple(i) for i in s_lst]


def pointLineFinder(i, x, y):
    center_x, center_y = x, y
    r, angle = i[0], i[1]
    x = center_x + (r * math.cos(math.radians(angle)))
    y = center_y + (r * math.sin(math.radians(angle)))
    return x, y


def reorderDecimalData(data):
    return [data[3], data[2], data[1], data[0], data[8], data[9], data[10], data[11], data[4], data[5], data[6],
            data[7], data[15], data[14], data[13], data[12]]
    # return [data[0], data[1], data[2], data[3], data[8], data[9], data[10], data[11], data[4], data[5], data[6], data[7], data[15], data[14], data[13], data[12]]


def convertFromPointsToRelativeSides(lst):
    corners, all_data = cornerGeneratorProcess(lst)


# def checkIfTwoListOfListsAreIdentical(lst1, lst2):

# def sortOutListsRecursion(lst, new_lst):
#     for i in range(len(lst)):
#         if not isinstance(lst[i], list):
#             new_lst = new_lst + lst

#             # new_lst.append(lst)
#         else:
#             # new_lst.append([])
#             sortOutListsRecursion(lst[i], new_lst)
#     # new_lst = [i for i in new_lst if i]

#     return new_lst

# def checkDataTypes(lst, data_lst):
#     for i in range(len(lst)):
#         if not isinstance(lst[i], list):
#             data_lst.extend([findDataType(lst[i])])
#         else:
#             data_lst.append([])
#             checkDataTypes(lst[i], data_lst[-1])
#     data_lst = [i for i in data_lst if i]
#     return data_lst

def get_type(input_data):
    try:
        return type(literal_eval(input_data))
    except (ValueError, SyntaxError):
        return str


def convertSetsToList(lst):
    for i in range(len(lst)):
        if isinstance(lst[i], set):
            pass
        elif isinstance(lst[i], list):
            convertSetsToList(lst[i])
        elif not isinstance(lst[i], list) and not isinstance(lst[i], set):
            pass
    return lst

    # return [list(i) for i in lst if isinstance(i, set)]


def parseAllFoldersForString(new_path, searcher_var):
    files = glob(new_path + '/**/', recursive=True)
    for i in files:
        for j in os.listdir(i):
            if searcher_var in j:
                print(j)


def groupByLikeValues(lst, index):
    d = {}
    for row in lst:
        if row[index] not in d:
            d[row[index]] = []
        d[row[index]].append(row)
    d_lst = [j for i, j in d.items()]
    return d_lst


def reorderListByStringOrder(order_lst, lst, index):
    adjusted_lst = []
    for j in range(len(order_lst)):
        for i in range(len(lst)):
            if order_lst[j].lower() == lst[i][index].lower():
                adjusted_lst.append(lst[i])
    return adjusted_lst


def dataGather(lst):
    data = lst.replace("\n", " ").replace("†", "").lower().strip().replace(",", "")
    data = re.sub(r'[^0-9. ]+', '', data).strip()
    data_lst = data.split(" ")
    data_lst = [i for i in data_lst if i]
    if len(data_lst) > 1 or data_lst == []:
        return []
    elif len(data_lst[0]) * 2 < len(lst):
        return []
    else:
        return data_lst


def findAllNumbers(data):
    re_finder = re.sub(r'[^0-9. ]+', '', data).strip().split()
    re_data = [float(i) for i in re_finder]
    return re_data


# hole_washout = [self.model_string1_side.data(self.model_string1_side.index(3, 1)), self.model_string2_side.data(self.model_string2_side.index(3, 1)), self.model_string3_side.data(self.model_string3_side.index(3, 1)), self.model_string4_side.data(self.model_string4_side.index(3, 1))]
# internal_gradient = [self.model_string1_side.data(self.model_string1_side.index(4, 1)), self.model_string2_side.data(self.model_string2_side.index(4, 1)), self.model_string3_side.data(self.model_string3_side.index(4, 1)), self.model_string4_side.data(self.model_string4_side.index(4, 1))]
# backup_mud = [self.model_string1_side.data(self.model_string1_side.index(5, 1)), self.model_string2_side.data(self.model_string2_side.index(5, 1)), self.model_string3_side.data(self.model_string3_side.index(5, 1)), self.model_string4_side.data(self.model_string4_side.index(5, 1))]
# internal_mud = [self.model_string1_side.data(self.model_string1_side.index(6, 1)), self.model_string2_side.data(self.model_string2_side.index(6, 1)), self.model_string3_side.data(self.model_string3_side.index(6, 1)), self.model_string4_side.data(self.model_string4_side.index(6, 1))]
#
# hole_washout = [float(i) for i in hole_washout]
# internal_gradient = [float(i) for i in internal_gradient]
# backup_mud = [float(i) for i in backup_mud]
# internal_mud = [float(i) for i in internal_mud]

def grapher1(lst1, title):
    fig, ax = plt.subplots()
    colors = ['black', 'red', 'yellow', 'blue']

    counter = 0
    for i in lst1:
        x2, y2 = [k[0] for k in i], [k[1] for k in i]
        plt.scatter(x2, y2, c='black')
        plt.plot(x2, y2, c='black')
        counter += 1
    ax.set_title(title)
    # plt.scatter([shl[0]], [shl[1]], c='black')
    plt.show()


def grapher2(lst1, lst2, title):
    fig, ax = plt.subplots()
    colors = ['black', 'red', 'yellow', 'blue']

    counter = 0
    for i in lst1:
        x1, y1 = [k[0] for k in i], [k[1] for k in i]
        plt.scatter(x1, y1, c=colors[counter])
        plt.plot(x1, y1, c=colors[counter])
        counter += 1
    counter = 0

    for i in lst2:
        x2, y2 = [k[0] for k in i], [k[1] for k in i]
        plt.scatter(x2, y2, c=colors[counter])
        plt.plot(x2, y2, c=colors[counter])
        counter += 1
    ax.set_title(title)
    # plt.scatter([shl[0]], [shl[1]], c='black')
    plt.show()


def grapher3(lst, title):
    fig, ax = plt.subplots()
    colors = ['black', 'red', 'yellow', 'blue']

    counter = 0
    x2, y2 = [k[0] for k in lst], [k[1] for k in lst]
    plt.scatter(x2, y2, c=colors[0])
    plt.plot(x2, y2, c=colors[1])
    counter += 1
    ax.set_title(title)
    # plt.scatter([shl[0]], [shl[1]], c='black')
    plt.show()


def grapher4(lst1, lst2, title):
    fig, ax = plt.subplots()
    colors = ['black', 'red', 'yellow', 'blue']
    x1, y1 = [k[0] for k in lst1], [k[1] for k in lst1]
    plt.scatter(x1, y1, c=colors[0])
    plt.plot(x1, y1, c=colors[0])

    x2, y2 = [k[0] for k in lst2], [k[1] for k in lst2]
    plt.scatter(x2, y2, c=colors[1])
    plt.plot(x2, y2, c=colors[1])
    ax.set_title(title)
    # plt.scatter([shl[0]], [shl[1]], c='black')
    plt.show()


def printFormattedLine(lst):
    for row in lst:
        for col in row:
            print("{:10.2f}".format(col), end=" ")
        print("")


def getColors():
    by_hsv = sorted((tuple(mcolors.rgb_to_hsv(mcolors.to_rgb(color))),
                     name)
                    for name, color in mcolors.CSS4_COLORS.items())
    names = [name for hsv, name in by_hsv]
    return names


def isNotDigit(str):
    lstStringAll = list(string.printable)
    lstStringDigit = list(string.digits)
    lstStringRelevant = [x for x in lstStringAll if x not in lstStringDigit]
    lstStringRelevant.remove(".")
    strLst = list(str)
    count = 0
    for i in strLst:
        if i in lstStringRelevant:
            count += 1

    if count != 0:
        return True
    else:
        return False


def isNumericValue(str):
    lstStringDigit = list(string.digits)
    lstStringDigit.append('.')
    strLst = list(str)
    count = 0
    for i in strLst:
        if i not in lstStringDigit:
            count += 1
    if count != 0:
        return False
    else:
        return True


def lineIntersectionPt(m1, m2, b1, b2):
    xi = (b1 - b2) / (m2 - m1)
    yi = m1 * xi + b1
    return [xi, yi]


def slopeFinder(p1, p2):
    slopeValX, slopeValY = p2[0] - p1[0], p2[1] - p1[1]
    try:
        slopeVal = slopeValY / slopeValX
    except ZeroDivisionError:
        slopeVal = 0
    yIntercept = p1[1] - (slopeVal * p1[0])
    return slopeVal, yIntercept


def translateDirectionToNumber(variable, val):
    conversions = {
        'rng': {'W': '2', 'E': '1'},
        'township': {'S': '2', 'N': '1'},
        'baseline': {'U': '2', 'S': '1'},
        'alignment': {'SE': '1', 'NE': '2', 'SW': '3', 'NW': '4'}
    }
    if variable in conversions and val in conversions[variable]:
        return conversions[variable][val]
    else:
        return val


def compareLists(lst1, lst2):
    lst1 = [list(i) for i in lst1]
    lst2 = [list(i) for i in lst2]
    if len(lst1[0]) != len(lst2[0]):
        return
    else:
        missing_values_1 = [value for value in lst1 if value not in lst2]
        missing_values_2 = [value for value in lst2 if value not in lst1]
        print("Missing values from the second list:", missing_values_1)
        print("Missing values from the first list:", missing_values_2)


# def translateDirectionToNumber(variable, val):
#     if variable == 'rng':
#         if val == 'W':
#             return '2'
#         elif val == 'E':
#             return '1'
#         else:
#             return val
#     elif variable == 'township':
#         if val == 'S':
#             return '2'
#         elif val == 'N':
#             return '1'
#         else:
#             return val
#     elif variable == 'baseline':
#         if val == 'U':
#             return '2'
#         elif val == 'S':
#             return '1'
#         else:
#             return val
#     elif variable == 'alignment':
#         if val == 'SE':
#             return '1'
#         elif val == 'NE':
#             return '2'
#         elif val == 'SW':
#             return '3'
#         elif val == 'NW':
#             return '4'
#         else:
#             return val
#     return val

# def azimuthToBearing(azi_val):
#     if 90 > azi_val > 0:
#         bearing = azi_val
#         dir_val = 2
#     elif 180 > azi_val > 90:
#         bearing = 180 - azi_val
#         dir_val = 1
#     elif 270 > azi_val > 180:
#         bearing = azi_val - 180
#         dir_val = 3
#     else:
#         bearing = 360 - azi_val
#         dir_val = 4
#
#     # if 90 > azi_val > 0:
#     #     bearing = azi_val
#     #     dir_val = 2
#     # elif 180 > azi_val > 90:
#     #     bearing = 180 - azi_val
#     #     dir_val = 1
#     # elif 270 > azi_val > 180:
#     #     bearing = azi_val - 180
#     #     dir_val = 3
#     # else:
#     #     bearing = 360 - azi_val
#     #     dir_val = 4
#     # bearing = abs(bearing - 90)
#
#     return bearing, dir_val
#
#
# # 0 - 90 -> 90-0
# # 90 - 180 > 360 - 270
# # 180 - 270 > 270 - 180
# # 270 - 360 > 180 > 90
#
# def bearingToAzimuth(decVal, data):
#
#     # if 0 <= bearing < 90:
#     #     azi_val = 90 - bearing
#     # elif 90 <= bearing < 180:
#     #     azi_val = 630 - bearing
#     # elif 180 <= bearing < 270:
#     #     azi_val = 450 - bearing
#     # else:
#     #     azi_val = 180 - (bearing - 270) * (90 / 95)
#
#     # return round(azi_val % 360, 5)
#
#     if data == 'west':
#         decimal_value = abs(decVal - 270)
#         # if decVal < 270:
#         #     dir_val = 3
#         # else:
#         #     dir_val = 4
#         # deg_val = convertDecimalToDegrees(decimal_value)
#     if data == 'east':  # or data == 'west':
#         decimal_value = abs(90 - decVal)
#         # if decVal < 90:
#         #     dir_val = 3
#         # else:
#         #     dir_val = 4
#         # deg_val = convertDecimalToDegrees(decimal_value)
#     if data == 'north':  # or data == 'south':
#         if decVal < 180:
#             decimal_value = abs(90 - decVal)
#             # dir_val = 4
#         else:
#             decimal_value = 90 - abs(180 - decVal)
#             # dir_val = 3
#         # deg_val = convertDecimalToDegrees(decimal_value)
#     if data == 'south':
#         data_360 = math.isclose(360, decVal, abs_tol=50)
#         data_0 = math.isclose(0, decVal, abs_tol=50)
#         if data_360 and not data_0:
#             decimal_value = abs(decVal - 270)
#             # dir_val = 4
#         if not data_360 and data_0:
#             decimal_value = abs(90 - decVal)
#             # dir_val = 3
#         # deg_val = convertDecimalToDegrees(decimal_value)
#     return decimal_value


def checkOccurences(str, valuesLst):
    # ()
    rejectedLst = ['UT', 'KOP', 'IDENTIFICATION', 'Operator', 'Wellbore', 'HLD', 'County', 'Project', 'EOB',
                   "interpolated", "County", 'Project:', 'Reference:', 'NAD83', 'HLD',
                   "minimum", "database", "company", "reference", "Calculation", "Well", "Federal"]
    booVal = None
    valueCount = 0
    for j in rejectedLst:
        try:
            if j.lower() in str.lower():
                booVal = False
        except AttributeError:
            if j in str:
                booVal = False
    if booVal is not False:
        for i in valuesLst:
            try:
                if i.lower() in str.lower():
                    valueCount += 1
            except AttributeError:
                if i in str:
                    valueCount += 1
    if valueCount > 0:
        booVal = True
    if booVal is None:
        booVal = False
    return booVal


def oneToMany(lst, number):
    count = -1
    outLst = []
    for i in range(len(lst)):
        if i % number == 0:
            outLst.append([])
            count += 1
        outLst[count].append(lst[i])
    return outLst


def manyToOne(lst):
    return list(manyToOneParse(lst))


def manyToOneParse(lst):
    for item in lst:
        if isinstance(item, Iterable) and not isinstance(item, str):
            for x in manyToOne(item):
                yield x
        else:
            yield item


def removeInvalidDegreesAzimuth(lst):
    newLst = []
    for i in range(len(lst)):
        if lst[i][1] < 110 and lst[i][2] < 366 and lst[i][0] < 30000:
            newLst.append(lst[i])
    return newLst


def removeDuplicatesMany(lst):
    emptyLst = []
    emptyLstFull = []
    for i in range(len(lst)):
        if lst[i][0] not in emptyLst:
            emptyLstFull.append(lst[i])
            emptyLst.append(lst[i][0])
    return emptyLstFull


# def tikaParser(file):
#     parsed_data_full = parser.from_file(file, xmlContent=True)
#     parsed_data_full = parsed_data_full['content']
#
#     parsedDataLst = TemplateDataGenerate.DataGenerateNoDepth(parsed_data_full)


#     pageDataLst = [[]]
#     pageCounter = 0
#     pagesLst = [0]
#     for i in range(len(parsedDataLst)):
#         # search for occurnces of the mentioned strings and replace them with an empty space
#         parsedDataLst[i] = parsedDataLst[i].replace('<div class="page"><p />', " ").replace('<p>', ' ').replace('</p>', ' ')
#
#         # add the datalist row to the relative list for that page
#         pageDataLst[pageCounter].append(parsedDataLst[i])
#
#         # create a new list(page) when the following occurs
#         if parsedDataLst[i] == "</div>" and parsedDataLst[i + 1] == '<div class="page"><p />':
#             pagesLst.append(pageCounter + 1)
#             pageCounter += 1
#             pageDataLst.append([])
#
#     return pageDataLst, pagesLst
#

def cluster(data, maxgap):
    '''Arrange data into groups where successive elements
       differ by no more than *maxgap*

        >>> cluster([1, 6, 9, 100, 102, 105, 109, 134, 139], maxgap=10)
        [[1, 6, 9], [100, 102, 105, 109], [134, 139]]

        >>> cluster([1, 6, 9, 99, 100, 102, 105, 134, 139, 141], maxgap=10)
        [[1, 6, 9], [99, 100, 102, 105], [134, 139, 141]]

    '''
    data.sort()
    groups = [[data[0]]]
    for x in data[1:]:
        if abs(x - groups[-1][-1]) <= maxgap:
            groups[-1].append(x)
        else:
            groups.append([x])
    return groups


def grouper(iterable, val):
    prev = None
    group = []
    for item in iterable:
        if not prev or item - prev <= val:

            group.append(item)
        else:
            yield group
            group = [item]
        prev = item
    if group:
        yield group


def search_lua_files(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".lua"):
                file_path = os.path.join(root, file)
                search_file(file_path)


def search_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        line_number = 1
        for line in file:
            if "grounded" in line.lower():
                print(f"Found 'grounded' in {file_path} at line {line_number}")
            line_number += 1


def polyfit(x, degree):
    y = list(range(len(x)))
    results = {}

    coeffs = np.polyfit(x, y, degree)

    # Polynomial Coefficients
    results['polynomial'] = coeffs.tolist()

    # r-squared
    p = np.poly1d(coeffs)
    # fit values, and mean
    yhat = p(x)  # or [p(z) for z in x]
    ybar = np.sum(y) / len(y)  # or sum(y)/len(y)
    ssreg = np.sum((yhat - ybar) ** 2)  # or sum([ (yihat - ybar)**2 for yihat in yhat])
    sstot = np.sum((y - ybar) ** 2)  # or sum([ (yi - ybar)**2 for yi in y])
    results['determination'] = ssreg / sstot

    return results


def translateNumberToDirection(variable, val):
    translations = {
        'rng': {'2': 'W', '1': 'E'},
        'township': {'2': 'S', '1': 'N'},
        'baseline': {'2': 'U', '1': 'S'},
        'alignment': {'1': 'SE', '2': 'NE', '3': 'SW', '4': 'NW'}
    }
    return translations.get(variable, {}).get(val, val)


def reTranslateDataNoDF(i):
    conc_code_merged = i[:6]
    conc_code_merged[2] = translateNumberToDirection('township', str(conc_code_merged[2])).upper()
    conc_code_merged[4] = translateNumberToDirection('rng', str(conc_code_merged[4])).upper()
    conc_code_merged[5] = translateNumberToDirection('baseline', str(conc_code_merged[5])).upper()
    conc_code_merged[0], conc_code_merged[1], conc_code_merged[3] = str(int(float(conc_code_merged[0]))).zfill(2), str(int(float(conc_code_merged[1]))).zfill(2), str(int(float(conc_code_merged[3]))).zfill(2)
    conc_code = "".join([str(q) for q in conc_code_merged])
    return conc_code


def reTranslateData(i):
    conc_code_merged = i[:6]
    # conc_code_merged[2] = translateNumberToDirection('township', str(conc_code_merged[2])).upper()
    # conc_code_merged[4] = translateNumberToDirection('rng', str(conc_code_merged[4])).upper()
    # conc_code_merged[5] = translateNumberToDirection('baseline', str(conc_code_merged[5])).upper()

    conc_code_merged.iloc[2] = translateNumberToDirection('township', str(conc_code_merged.iloc[2])).upper()
    conc_code_merged.iloc[4] = translateNumberToDirection('rng', str(conc_code_merged.iloc[4])).upper()
    conc_code_merged.iloc[5] = translateNumberToDirection('baseline', str(conc_code_merged.iloc[5])).upper()
    conc_code_merged.iloc[0] = str(int(float(conc_code_merged.iloc[0]))).zfill(2)
    conc_code_merged.iloc[1] = str(int(float(conc_code_merged.iloc[1]))).zfill(2)
    conc_code_merged.iloc[3] = str(int(float(conc_code_merged.iloc[3]))).zfill(2)

    # conc_code_merged[0], conc_code_merged[1], conc_code_merged[3] = str(int(float(conc_code_merged[0]))).zfill(2), str(int(float(conc_code_merged[1]))).zfill(2), str(int(float(conc_code_merged[3]))).zfill(2)
    conc_code = "".join([str(q) for q in conc_code_merged])
    return conc_code
def testCalculateDistancesPoints(data):
    coord = [500001, 5360194.4]
    lats = utm.to_latlon(float(coord[0]), float(coord[1]), 12, 'T')
    start_point = gp.Point(lats[0], lats[1])
    points = [(start_point.latitude, start_point.longitude)]
    utm_lst = [coord]
    data = [i for i in data if i[0] > 0]
    for dist, bearing in data:
        # Calculate the next point using geodesic distance and bearing
        dist = dist * 0.0003048
        next_point = distance.distance(kilometers=dist).destination(start_point, bearing)

        points.append((next_point.latitude, next_point.longitude))
        utm_pt = utm.from_latlon(next_point.latitude, next_point.longitude)[:2]
        utm_lst.append(utm_pt)
        start_point = next_point

    # for i in utm_lst:
    #     pt1 = (i[0] - utm_lst[0][0]) / 0.3048
    #     pt2 = (i[1] - utm_lst[0][1]) / 0.3048
    #     utm_points_2.append([pt1, pt2])
    #
    return points


# def translateNumberToDirection(variable, val):
#     translations = {
#         'rng': {'2': 'W', '1': 'E'},
#         'township': {'2': 'S', '1': 'N'},
#         'baseline': {'2': 'U', '1': 'S'},
#         'alignment': {'1': 'SE', '2': 'NE', '3': 'SW', '4': 'NW'}
#     }
#     return translations.get(variable, {}).get(val, val)
#
#
# def reTranslateData(i):
#     conc_code_merged = i[:6]
#     conc_code_merged[2] = translateNumberToDirection('township', str(conc_code_merged[2])).upper()
#     conc_code_merged[4] = translateNumberToDirection('rng', str(conc_code_merged[4])).upper()
#     conc_code_merged[5] = translateNumberToDirection('baseline', str(conc_code_merged[5])).upper()
#     conc_code_merged[0], conc_code_merged[1], conc_code_merged[3] = str(int(float(conc_code_merged[0]))).zfill(2), str(int(float(conc_code_merged[1]))).zfill(2), str(int(float(conc_code_merged[3]))).zfill(2)
#     conc_code = "".join([str(q) for q in conc_code_merged])
#     return conc_code


def calculate_points(start_lat, start_lon, start_utm_easting, start_utm_northing, survey_data):
    start_lat = 40.20193652499225
    start_lon = -110.07027926738404
    start_utm_easting = 579127
    start_utm_northing = 4450585
    survey_data = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [1.11, -0.3], [0.01, -0.0],
                   [1.31, -0.35], [4.8, -1.28], [10.48, -2.79], [16.21, -4.32], [18.28, -4.87], [26.7, -7.11],
                   [35.12, -9.36], [43.54, -11.6], [51.96, -13.85], [60.39, -16.09], [68.81, -18.33], [79.7, -21.23],
                   [79.7, -21.23], [77.23, -20.58], [85.65, -22.82], [94.07, -25.07], [102.49, -27.31],
                   [110.92, -29.55], [119.34, -31.8], [127.76, -34.04], [134.08, -35.73], [136.18, -36.29],
                   [143.02, -38.11],
                   [144.63, -38.54], [154.21, -41.11], [165.45, -44.15], [178.37, -47.66], [192.94, -51.64],
                   [209.18, -56.09], [227.06, -61.0], [246.6, -66.38], [259.41, -69.91], [267.65, -72.18],
                   [289.0, -78.07], [310.36, -83.96], [331.72, -89.85], [353.08, -95.74], [374.43, -101.63],
                   [395.79, -107.52], [417.15, -113.42], [438.51, -119.31], [459.86, -125.2], [481.22, -131.09],
                   [502.58, -136.98], [523.93, -142.87], [545.29, -148.76], [566.65, -154.65], [588.01, -160.54],
                   [609.37, -166.43],
                   [630.72, -172.32], [652.08, -178.21], [673.44, -184.1], [694.79, -190.0], [716.15, -195.89],
                   [737.51, -201.78], [758.87, -207.67], [780.22, -213.56], [801.58, -219.45], [822.94, -225.34],
                   [844.29, -231.23], [865.65, -237.12], [887.01, -243.01], [908.37, -248.9], [929.73, -254.79],
                   [951.08, -260.69], [972.44, -266.58], [993.8, -272.47], [1015.15, -278.36], [1036.51, -284.25],
                   [1057.87, -290.14], [1079.23, -296.03], [1100.58, -301.92], [1121.94, -307.81], [1143.3, -313.7],
                   [1164.65, -319.59], [1186.01, -325.48], [1207.37, -331.38], [1228.73, -337.27], [1250.09, -343.16],
                   [1271.44, -349.05], [1294.33, -355.36], [1294.33, -355.36], [1292.8, -354.94], [1314.16, -360.83],
                   [1335.51, -366.72], [1350.68, -370.9], [1356.87, -372.61], [1361.44, -373.87], [1378.2, -384.92],
                   [1398.96, -417.1], [1418.23, -468.21], [1435.19, -536.03], [1449.08, -617.59], [1459.3, -709.33],
                   [1465.41, -807.22], [1467.08, -877.14], [1467.32, -907.08], [1468.14, -1006.9],
                   [1468.96, -1106.72], [1469.78, -1206.54], [1470.6, -1306.36], [1471.42, -1406.18],
                   [1472.24, -1506.0], [1473.06, -1605.82], [1473.88, -1705.64], [1474.69, -1805.46],
                   [1475.51, -1905.28], [1476.33, -2005.1], [1477.15, -2104.92], [1477.97, -2204.74],
                   [1478.79, -2304.56], [1479.61, -2404.38], [1480.43, -2504.2], [1481.24, -2604.01],
                   [1482.06, -2703.83], [1482.88, -2803.65], [1483.7, -2903.47], [1484.52, -3003.29],
                   [1485.34, -3103.11], [1486.16, -3202.93], [1486.98, -3302.75],
                   [1487.8, -3402.57], [1488.61, -3502.39], [1489.43, -3602.21], [1490.25, -3702.03],
                   [1491.07, -3801.85], [1491.89, -3901.67], [1492.71, -4001.49], [1493.53, -4101.31],
                   [1494.35, -4201.13], [1495.16, -4300.95], [1495.98, -4400.77], [1496.8, -4500.59],
                   [1497.62, -4600.41], [1498.44, -4700.23], [1499.26, -4800.05], [1500.08, -4899.86],
                   [1500.9, -4999.69], [1501.72, -5099.51], [1502.53, -5199.32], [1503.35, -5299.14],
                   [1504.17, -5398.96], [1504.99, -5498.78], [1505.81, -5598.6],
                   [1506.63, -5698.42], [1507.45, -5798.24], [1508.27, -5898.06], [1509.09, -5997.88],
                   [1509.9, -6097.7], [1510.72, -6197.52], [1511.54, -6297.34], [1512.36, -6397.16],
                   [1513.18, -6496.98], [1514.0, -6596.8], [1514.82, -6696.62], [1515.64, -6796.44],
                   [1516.45, -6896.26], [1517.27, -6996.08], [1518.09, -7095.9], [1518.91, -7195.72],
                   [1519.73, -7295.53], [1520.55, -7395.35], [1521.37, -7495.18], [1522.19, -7594.99],
                   [1523.01, -7694.81], [1523.82, -7794.63], [1524.64, -7894.45],
                   [1525.46, -7994.27], [1526.28, -8094.09], [1527.1, -8193.91], [1527.92, -8293.73],
                   [1528.74, -8393.55], [1529.56, -8493.37], [1530.38, -8593.19], [1531.19, -8693.01],
                   [1532.01, -8792.83], [1532.83, -8892.65], [1533.65, -8992.47], [1534.47, -9092.29],
                   [1535.29, -9192.11], [1536.11, -9291.93], [1536.93, -9391.75], [1537.74, -9491.57],
                   [1538.56, -9591.39], [1539.38, -9691.21], [1540.2, -9791.02], [1541.02, -9890.84],
                   [1541.84, -9990.66], [1542.66, -10090.48], [1543.48, -10190.3],
                   [1544.3, -10290.12], [1545.11, -10389.94], [1545.93, -10489.76], [1546.75, -10589.58],
                   [1547.57, -10689.4], [1548.12, -10756.28]]

    # Convert starting lat/lon to ECEF coordinates
    a = 6378137.0  # Earth's radius in meters
    f = 1 / 298.257223563  # Earth's flattening factor
    e2 = 1 - (1 - f) ** 2  # Eccentricity squared
    start_lat_rad = radians(start_lat)
    start_lon_rad = radians(start_lon)
    N = a / sqrt(1 - e2 * sin(start_lat_rad) ** 2)
    X0 = (N + start_utm_easting) * cos(start_lat_rad) * cos(start_lon_rad)
    Y0 = (N + start_utm_easting) * cos(start_lat_rad) * sin(start_lon_rad)
    Z0 = (N * (1 - e2) + start_utm_northing) * sin(start_lat_rad)

    # Define a transformer from ECEF to lat/lon
    transformer = Transformer.from_crs("EPSG:4978", "EPSG:4326")

    # Calculate the ECEF coordinates for each survey point
    ecef_points = []
    for north_offset, east_offset in survey_data:
        north_offset_m = north_offset * 0.3048  # Convert feet to meters
        east_offset_m = east_offset * 0.3048  # Convert feet to meters
        X = X0 + east_offset_m * cos(start_lon_rad) - north_offset_m * sin(start_lon_rad)
        Y = Y0 + east_offset_m * sin(start_lon_rad) + north_offset_m * cos(start_lon_rad)
        Z = Z0
        ecef_points.append((X, Y, Z))

    # Convert ECEF coordinates to lat/lon coordinates
    lat_lon_points = []
    for x, y, z in ecef_points:
        lat, lon, _ = transformer.transform(x, y, z)
        lat_lon_points.append((lat, lon))

    return lat_lon_points


def determine_coordinate_type(coord_pair):
    # Check if the coordinates represent UTM coordinates
    if (166021.443 <= coord_pair[0] <= 833978.556 or 500000 <= coord_pair[0] <= 999999) and (
            0 <= coord_pair[1] <= 10000000):
        return "utm"
    # Check if the coordinates represent lat/lon coordinates
    elif (-90 <= coord_pair[0] <= 90) and (-180 <= coord_pair[1] <= 180):
        return "latlon"
    else:
        return "Unknown"


def determineCoordsAndConvert(coords, type):
    if all(isinstance(item, list) for item in coords):
        coords = [convertAllPosibleStringsToFloats(i) for i in coords]
        result = determine_coordinate_type(coords[0])
    else:
        coords = convertAllPosibleStringsToFloats(coords)
        result = determine_coordinate_type(coords)

    if result == type:
        return coords
    if result == 'utm' and type == 'latlon':
        return [utm.to_latlon(i[0], i[1], 12, 'T') for i in coords]
    if result == 'latlon' and type == 'utm':
        return [utm.from_latlon(i[0], i[1])[:2] for i in coords]
    else:
        return coords


def calculate_lat_lon(start_lat, start_lon, start_utm_easting, start_utm_northing, points):
    start_lat = 40.20193652499225
    start_lon = -110.07027926738404
    start_utm_easting = 579127
    start_utm_northing = 4450585
    points = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [1.11, -0.3], [0.01, -0.0], [1.31, -0.35],
              [4.8, -1.28], [10.48, -2.79], [16.21, -4.32], [18.28, -4.87], [26.7, -7.11], [35.12, -9.36],
              [43.54, -11.6], [51.96, -13.85], [60.39, -16.09], [68.81, -18.33], [79.7, -21.23], [79.7, -21.23],
              [77.23, -20.58], [85.65, -22.82], [94.07, -25.07], [102.49, -27.31], [110.92, -29.55], [119.34, -31.8],
              [127.76, -34.04], [134.08, -35.73], [136.18, -36.29], [143.02, -38.11],
              [144.63, -38.54], [154.21, -41.11], [165.45, -44.15], [178.37, -47.66], [192.94, -51.64],
              [209.18, -56.09], [227.06, -61.0], [246.6, -66.38], [259.41, -69.91], [267.65, -72.18], [289.0, -78.07],
              [310.36, -83.96], [331.72, -89.85], [353.08, -95.74], [374.43, -101.63], [395.79, -107.52],
              [417.15, -113.42], [438.51, -119.31], [459.86, -125.2], [481.22, -131.09], [502.58, -136.98],
              [523.93, -142.87], [545.29, -148.76], [566.65, -154.65], [588.01, -160.54], [609.37, -166.43],
              [630.72, -172.32], [652.08, -178.21], [673.44, -184.1], [694.79, -190.0], [716.15, -195.89],
              [737.51, -201.78], [758.87, -207.67], [780.22, -213.56], [801.58, -219.45], [822.94, -225.34],
              [844.29, -231.23], [865.65, -237.12], [887.01, -243.01], [908.37, -248.9], [929.73, -254.79],
              [951.08, -260.69], [972.44, -266.58], [993.8, -272.47], [1015.15, -278.36], [1036.51, -284.25],
              [1057.87, -290.14], [1079.23, -296.03], [1100.58, -301.92], [1121.94, -307.81], [1143.3, -313.7],
              [1164.65, -319.59], [1186.01, -325.48], [1207.37, -331.38], [1228.73, -337.27], [1250.09, -343.16],
              [1271.44, -349.05], [1294.33, -355.36], [1294.33, -355.36], [1292.8, -354.94], [1314.16, -360.83],
              [1335.51, -366.72], [1350.68, -370.9], [1356.87, -372.61], [1361.44, -373.87], [1378.2, -384.92],
              [1398.96, -417.1], [1418.23, -468.21], [1435.19, -536.03], [1449.08, -617.59], [1459.3, -709.33],
              [1465.41, -807.22], [1467.08, -877.14], [1467.32, -907.08], [1468.14, -1006.9],
              [1468.96, -1106.72], [1469.78, -1206.54], [1470.6, -1306.36], [1471.42, -1406.18], [1472.24, -1506.0],
              [1473.06, -1605.82], [1473.88, -1705.64], [1474.69, -1805.46], [1475.51, -1905.28], [1476.33, -2005.1],
              [1477.15, -2104.92], [1477.97, -2204.74], [1478.79, -2304.56], [1479.61, -2404.38], [1480.43, -2504.2],
              [1481.24, -2604.01], [1482.06, -2703.83], [1482.88, -2803.65], [1483.7, -2903.47], [1484.52, -3003.29],
              [1485.34, -3103.11], [1486.16, -3202.93], [1486.98, -3302.75],
              [1487.8, -3402.57], [1488.61, -3502.39], [1489.43, -3602.21], [1490.25, -3702.03], [1491.07, -3801.85],
              [1491.89, -3901.67], [1492.71, -4001.49], [1493.53, -4101.31], [1494.35, -4201.13], [1495.16, -4300.95],
              [1495.98, -4400.77], [1496.8, -4500.59], [1497.62, -4600.41], [1498.44, -4700.23], [1499.26, -4800.05],
              [1500.08, -4899.86], [1500.9, -4999.69], [1501.72, -5099.51], [1502.53, -5199.32], [1503.35, -5299.14],
              [1504.17, -5398.96], [1504.99, -5498.78], [1505.81, -5598.6],
              [1506.63, -5698.42], [1507.45, -5798.24], [1508.27, -5898.06], [1509.09, -5997.88], [1509.9, -6097.7],
              [1510.72, -6197.52], [1511.54, -6297.34], [1512.36, -6397.16], [1513.18, -6496.98], [1514.0, -6596.8],
              [1514.82, -6696.62], [1515.64, -6796.44], [1516.45, -6896.26], [1517.27, -6996.08], [1518.09, -7095.9],
              [1518.91, -7195.72], [1519.73, -7295.53], [1520.55, -7395.35], [1521.37, -7495.18], [1522.19, -7594.99],
              [1523.01, -7694.81], [1523.82, -7794.63], [1524.64, -7894.45],
              [1525.46, -7994.27], [1526.28, -8094.09], [1527.1, -8193.91], [1527.92, -8293.73], [1528.74, -8393.55],
              [1529.56, -8493.37], [1530.38, -8593.19], [1531.19, -8693.01], [1532.01, -8792.83], [1532.83, -8892.65],
              [1533.65, -8992.47], [1534.47, -9092.29], [1535.29, -9192.11], [1536.11, -9291.93], [1536.93, -9391.75],
              [1537.74, -9491.57], [1538.56, -9591.39], [1539.38, -9691.21], [1540.2, -9791.02], [1541.02, -9890.84],
              [1541.84, -9990.66], [1542.66, -10090.48], [1543.48, -10190.3],
              [1544.3, -10290.12], [1545.11, -10389.94], [1545.93, -10489.76], [1546.75, -10589.58],
              [1547.57, -10689.4], [1548.12, -10756.28]]

    p = Proj(proj='utm', zone=12, ellps='WGS84', datum='WGS84')

    latitudes = []
    longitudes = []

    for point in points:
        easting = start_utm_easting + point[0]
        northing = start_utm_northing + point[1]
        lon, lat = p(easting, northing, inverse=True)
        latitudes.append(lat)
        longitudes.append(lon)

    return latitudes, longitudes


def get_distance_and_bearing(lat1, lon1, lat2, lon2):
    # Create a Geodesic object with the WGS84 ellipsoid
    geod = Geodesic.WGS84

    # Calculate the geodesic between the two points
    g = geod.Inverse(lat1, lon1, lat2, lon2)

    # Extract the distance and initial bearing
    distance = g['s12'] / 0.3048
    bearing = g['azi1']

    return distance, bearing


def get_lat_lon(lat1, lon1, distance_feet, bearing):
    # Convert feet to meters
    distance_meters = distance_feet / 3.2808

    # Create a Geodesic object with the WGS84 ellipsoid
    geod = Geodesic.WGS84

    # Calculate the destination point
    g = geod.Direct(lat1, lon1, bearing, distance_meters)

    # Extract the latitude and longitude
    lat2 = g['lat2']
    lon2 = g['lon2']

    return lat2, lon2

    # Return the distance and bearing
    # return distance, bearing


# def convert_all_bearings(bearing):
#     deg = int(bearing)
#     min_float = (bearing - deg) * 60
#     min = int(min_float)
#     sec = int((min_float - min) * 60)

#     # Determine new direction and adjust degrees if necessary
#     if 0 <= bearing < 90:
#         new_deg, new_min, new_sec = deg, min, sec
#     elif 90 <= bearing < 180:
#         new_deg, new_min, new_sec = 180 - deg, 59 - min, 60 - sec
#     elif 180 <= bearing < 270:
#         new_deg, new_min, new_sec = deg - 180, min, sec
#     else:
#         new_deg, new_min, new_sec = 360 - deg, 59 - min, 60 - sec
#     output = new_deg + (new_min/60) + (new_sec/3600)
#     return output
#     # return converted_data


def convAngleDelta(survey_north_ref, plat_north_ref, convergence_angle, azi):
    result_conv = -1
    if survey_north_ref.lower() == "M":
        pass
    elif survey_north_ref.lower() == "t" and plat_north_ref.lower() == "g":
        result_conv = azi - convergence_angle
    elif survey_north_ref.lower() == "g" and plat_north_ref.lower() == "t":
        result_conv = azi + convergence_angle
    else:
        result_conv = azi
    return result_conv


# def countyDict(number):
#     utah_counties = {
#         1: "BEAVER",
#         3: "BOX ELDER",
#         5: "CACHE",
#         7: "CARBON",
#         9: "DAGGETT",
#         11: "DAVIS",
#         13: "DUCHESNE",
#         15: "EMERY",
#         17: "GARFIELD",
#         19: "GRAND",
#         21: "IRON",
#         23: "JUAB",
#         25: "KANE",
#         27: "MILLARD",
#         29: "MORGAN",
#         31: "PIUTE",
#         33: "RICH",
#         35: "SALT LAKE",
#         37: "SAN JUAN",
#         39: "SANPETE",
#         41: "SEVIER",
#         43: "SUMMIT",
#         45: "TOOELE",
#         47: "UINTAH",
#         49: "UTAH",
#         51: "WASATCH",
#         53: "WASHINGTON",
#         55: "WAYNE",
#         57: "WEBER"
#     }
#     return utah_counties[number]

def countyDict(number):
    utah_counties = {
        1: "BEAVER",
        3: "BOX ELDER",
        5: "CACHE",
        7: "CARBON",
        9: "DAGGETT",
        11: "DAVIS",
        13: "DUCHESNE",
        15: "EMERY",
        17: "GARFIELD",
        19: "GRAND",
        21: "IRON",
        23: "JUAB",
        25: "KANE",
        27: "MILLARD",
        29: "MORGAN",
        31: "PIUTE",
        33: "RICH",
        35: "SALT LAKE",
        37: "SAN JUAN",
        39: "SANPETE",
        41: "SEVIER",
        43: "SUMMIT",
        45: "TOOELE",
        47: "UINTAH",
        49: "UTAH",
        51: "WASATCH",
        53: "WASHINGTON",
        55: "WAYNE",
        57: "WEBER"
    }
    return utah_counties[number]


def countDictReversed(county_name):
    utah_counties = {
        "BEAVER": 1,
        "BOX ELDER": 3,
        "CACHE": 5,
        "CARBON": 7,
        "DAGGETT": 9,
        "DAVIS": 11,
        "DUCHESNE": 13,
        "EMERY": 15,
        "GARFIELD": 17,
        "GRAND": 19,
        "IRON": 21,
        "JUAB": 23,
        "KANE": 25,
        "MILLARD": 27,
        "MORGAN": 29,
        "PIUTE": 31,
        "RICH": 33,
        "SALT LAKE": 35,
        "SAN JUAN": 37,
        "SANPETE": 39,
        "SEVIER": 41,
        "SUMMIT": 43,
        "TOOELE": 45,
        "UINTAH": 47,
        "UTAH": 49,
        "WASATCH": 51,
        "WASHINGTON": 53,
        "WAYNE": 55,
        "WEBER": 57
    }
    return utah_counties[county_name]


def findSPZone(county):
    lst1 = ['BOX ELDER', 'CACHE', 'DAGGETT', 'DAVIS', 'MORGAN', 'RICH', 'SUMMIT', 'WEBER']
    lst2 = ['CARBON', 'DUCHESNE', 'EMERY', 'GRAND', 'JUAB', 'MILLARD', 'SALT LAKE', 'SANPETE', 'SEVIER', 'TOOELE',
            'UINTAH', 'UTAH', 'WASATCH']
    lst3 = ['BEAVER', 'GARFIELD', 'IRON', 'KANE', 'PIUTE', 'SAN JUAN', 'WASHINGTON', 'WAYNE']
    if county.upper() in lst1:
        return 1
    elif county.upper() in lst2:
        return 2
    elif county.upper() in lst3:
        return 3


def convAngleSP(G44, pt):
    pt = [float(i) for i in pt]
    if abs(pt[1]) < 180 and abs(pt[0]) < 90:
        pass
    else:
        pt = utm.to_latlon(pt[0], pt[1], 12, 'T')

    I13, J13 = pt[0], abs(pt[1])
    AB16, AC16, AD16 = 0.659355482, 0.640578596, 0.612687337
    result = (111.5 - J13) * (AB16 if zone == 1 else (AC16 if zone == 2 else AD16))
    result = (111.5 - J13) * (AB16 if G44 == 1 else (AC16 if G44 == 2 else AD16))
    return result


def calcProposedAzimuth(survey):
    md = [i[0] for i in survey]
    inc = [i[1] for i in survey]
    azimuth = [i[2] for i in survey]
    md_lst = [i / 0.3048 for i in md]
    dev = wp.deviation(md=md_lst, inc=inc, azi=azimuth)
    pos = dev.minimum_curvature(course_length=30)
    offsetNS_lst = pos.northing
    offsetEW_lst = pos.easting
    output = wellMinimumCurvatureCalculation.bhl_Direction(offsetNS_lst.tolist()[-1] * 0.3048,
                                                           offsetEW_lst.tolist()[-1] * 0.3048)
    return output
    # pass


def findKickOffPoint(lst):
    directionalCode = ["=+-+", "=+-", "=+-+-+", "=+", "=-+-+-+", "=+-+-"]
    # incValues = [round(lst[i][1], 1) for i in range(len(lst))]
    incIncreases = '='
    incSig = []

    for i in range(len(lst) - 1):
        if lst[i] > lst[i + 1] and incIncreases[-1] != "-":
            incIncreases = incIncreases + "-"
            incSig.append(i)
        elif lst[i] < lst[i + 1] and incIncreases[-1] != "+":
            incIncreases = incIncreases + "+"
            incSig.append(i)
    if incIncreases == directionalCode[1] or incIncreases == directionalCode[3]:
        return incSig[0]

    elif incIncreases == directionalCode[0] or incIncreases == directionalCode[2] or incIncreases == directionalCode[4]:
        return incSig[-1]


def determineDirectionalType(surveyLst):
    incValues = [round(surveyLst[i][1], 0) for i in range(len(surveyLst))]
    maxVal = round(max(incValues), 0)
    end_val = incValues[-1]
    # horizontals, look for the first occurence of the max inclination
    if round(incValues[-1], 1) == round(maxVal, 1):
        prodIndex = incValues.index(maxVal)
        return prodIndex
    # directionals

    elif end_val < 20:
        back_lst = copy.deepcopy(incValues[::-1])
        for i in range(len(back_lst)):
            if back_lst[i] > end_val:
                return len(back_lst) - i + 1


    elif round(maxVal, 1) > 0 and round(maxVal, 1) != round(incValues[-1], 1):
        prodIndex = incValues.index(maxVal)
        for i in range(prodIndex, len(incValues)):
            if incValues[i] == 0 or incValues[i] == 0.0:
                dxProd = i
                return dxProd

    return len(surveyLst) - 2


def find_kickoff_point(md, inclination, azimuth):
    deviation_threshold = 2.0
    for depth, inclination, azimuth in zip(md, inclination, azimuth):
        deviation_from_vertical = np.abs(90 - inclination)
        if deviation_from_vertical >= deviation_threshold:
            print('depth', depth)
    """
  Identifies the kickoff point (KOP) in a directional survey data.

  Args:
    md (np.ndarray): Array of measured depths.
    inclination (np.ndarray): Array of inclinations (degrees).
    azimuth (np.ndarray): Array of azimuths (degrees).

  Returns:
    kop_index (int): Index of the KOP in the data arrays.

  """
    # Calculate change in inclination from previous point for each depth.
    inclination_diff = np.diff(inclination)

    # Find the maximum change in inclination, indicating the start of build-up.
    max_inclination_diff = np.argmax(inclination_diff)

    # Check for cases with multiple build-ups or flat wells.
    if max_inclination_diff == 0 or inclination[0] > 0:
        # Search for the first non-zero inclination.
        kop_index = np.where(inclination != 0)[0][0]
    else:
        # Use the index of maximum inclination difference.
        kop_index = max_inclination_diff
    return kop_index


# def reTranslateData(i):
#     conc_code_merged = i[:6]
#     conc_code_merged[2] = translateNumberToDirection('township', str(conc_code_merged[2])).upper()
#     conc_code_merged[4] = translateNumberToDirection('rng', str(conc_code_merged[4])).upper()
#     conc_code_merged[5] = translateNumberToDirection('baseline', str(conc_code_merged[5])).upper()
#     conc_code_merged[1], conc_code_merged[3] = str(int(float(conc_code_merged[1]))), str(int(float(conc_code_merged[3])))
#     conc_code = [str(r) for r in conc_code_merged]
#     len_lst = [len(r) for r in conc_code]
#     if len_lst[0] == 1:
#         conc_code[0] = "0" + str(int(float(conc_code[0])))
#     if len_lst[1] == 1:
#         conc_code[1] = "0" + str(int(float(conc_code[1])))
#     if len_lst[3] == 1:
#         conc_code[3] = "0" + str(int(float(conc_code[3])))
#     conc_code = "".join([str(q) for q in conc_code])
#     return conc_code
#
#
#
#
#
# def translateNumberToDirection(variable, val):
#     if variable == 'rng':
#         if val == '2':
#             return 'W'
#         elif val == '1':
#             return 'E'
#         else:
#             return val
#     elif variable == 'township':
#         if val == '2':
#             return 'S'
#         elif val == '1':
#             return 'N'
#         else:
#             return val
#     elif variable == 'baseline':
#         if val == '2':
#             return 'U'
#         elif val == '1':
#             return 'S'
#         else:
#             return val
#     elif variable == 'alignment':
#         if val == '1':
#             return 'SE'
#         elif val == '2':
#             return 'NE'
#         elif val == '3':
#             return 'SW'
#         elif val == '4':
#             return 'NW'
#         else:
#             return val


def format_exception(e):
    exception_list = traceback.format_stack()
    exception_list = exception_list[:-2]
    exception_list.extend(traceback.format_tb(e[2]))
    exception_list.extend(traceback.format_exception_only(e[0], e[1]))

    exception_str = "Traceback (most recent call last):\n"
    exception_str += "".join(exception_list)
    # Removing the last \n
    exception_str = exception_str[:-1]

    return exception_str


def polyfit2(x, y, degree):
    results = {}

    coeffs = np.polyfit(x, y, degree)

    # Polynomial Coefficients
    results['polynomial'] = coeffs.tolist()

    # r-squared
    p = np.poly1d(coeffs)
    # fit values, and mean
    yhat = p(x)  # or [p(z) for z in x]
    ybar = np.sum(y) / len(y)  # or sum(y)/len(y)
    ssreg = np.sum((yhat - ybar) ** 2)  # or sum([ (yihat - ybar)**2 for yihat in yhat])
    sstot = np.sum((y - ybar) ** 2)  # or sum([ (yi - ybar)**2 for yi in y])
    results['determination'] = ssreg / sstot

    return results


def searcher(dir, text):
    for subdir, dirs, files in os.walk(r"C:\Google Drive"):

        for name in files:
            if text.lower() in name.lower():  # or '.mp4' in file or '.rm' in file:
                print(os.path.join(subdir, name))


def findSegmentLength(xy1, xy2):
    return np.sqrt((xy1[0] - xy2[0]) ** 2 + (xy1[1] - xy2[1]) ** 2)


def matchAndRemergeLists(original_lst, new_lst, index):
    matched_lst = []
    for i in original_lst:
        if i[index] in new_lst:
            matched_lst.append(i)
    return matched_lst


def findUniqueListsInListOfLists(lst):
    lst_unique = []
    for i in lst:
        if i not in lst_unique:
            lst_unique.append(i)
    return lst_unique


def findListInListOfLists(lst, lol_lst):
    for i, sublist in enumerate(lol_lst):
        if sublist == lst:
            return i
    # for sublist in lol_lst:
    #     if sublist == lst:
    #         return sublist
    else:
        return 0


def zoom_pan_ax(ax):
    def on_scroll(event):
        """Zoom in or out on scroll."""
        # Get current x and y limits
        cur_xlim = ax.get_xlim()
        cur_ylim = ax.get_ylim()

        # Get the x and y coordinates of the mouse click
        x = event.xdata
        y = event.ydata

        # Get the amount of zoom and direction (up or down)
        zoom_scale = 1.1 if event.button == 'up' else 0.9

        # Calculate the new x and y limits
        new_xlim = [x - (x - cur_xlim[0]) / zoom_scale,
                    x + (cur_xlim[1] - x) / zoom_scale]
        new_ylim = [y - (y - cur_ylim[0]) / zoom_scale,
                    y + (cur_ylim[1] - y) / zoom_scale]

        # Set the new x and y limits
        ax.set_xlim(new_xlim)
        ax.set_ylim(new_ylim)
        plt.draw()

    def on_click(event):
        """Start the click-and-drag for panning."""
        if event.button == 1:
            ax._dragging = True
            ax._xclick = event.xdata
            ax._yclick = event.ydata

    def on_release(event):
        """End the click-and-drag for panning."""
        if event.button == 1:
            ax._dragging = False

    def on_motion(event):
        """Pan the plot."""
        if ax._dragging:
            dx = event.xdata - ax._xclick
            dy = event.ydata - ax._yclick
            ax._xclick = event.xdata
            ax._yclick = event.ydata
            ax.set_xlim(ax.get_xlim() - dx)
            ax.set_ylim(ax.get_ylim() - dy)
            plt.draw()

    # Connect the event handlers to the plot
    ax.figure.canvas.mpl_connect('scroll_event', on_scroll)
    ax.figure.canvas.mpl_connect('button_press_event', on_click)
    ax.figure.canvas.mpl_connect('button_release_event', on_release)
    ax.figure.canvas.mpl_connect('motion_notify_event', on_motion)

    # Return the Axes object
    return ax


def findMiteredCorner(polygon):
    north_pts = []
    south_pts = []
    east_pts = []
    west_pts = []

    # polygon = polygon.representative_point()  # get the centroid
    # polygon = polygon.convex_hull  # get the convex hull
    # polygon = polygon.exterior  # get the exterior ring
    # polygon = polygon.coords[:-1]
    # polygon = list(polygon.convex_hull.exterior.coords)
    polygon = Polygon(polygon)
    vertices = []
    for i in range(len(polygon.exterior.coords)):

        # Get the previous, current, and next coordinates
        if i == 0:
            prev_coord = polygon.exterior.coords[-2]

        else:
            prev_coord = polygon.exterior.coords[i - 1]
        curr_coord = polygon.exterior.coords[i]
        if i == len(polygon.exterior.coords) - 1:
            next_coord = polygon.exterior.coords[1]
        else:
            next_coord = polygon.exterior.coords[(i + 1) % len(polygon.exterior.coords)]

        # prev_coord = polygon.exterior.coords[i - 1]
        # curr_coord = polygon.exterior.coords[i]
        # next_coord = polygon.exterior.coords[(i + 1) % len(polygon.exterior.coords)]

        # Calculate the angle between the previous, current, and next coordinates
        angle = math.degrees(math.atan2(curr_coord[1] - prev_coord[1], curr_coord[0] - prev_coord[0]) -
                             math.atan2(next_coord[1] - curr_coord[1], next_coord[0] - curr_coord[0]))
        angle = abs(angle)
        if math.isclose(270, angle, abs_tol=1):
            angle = 360 - angle

        if math.isclose(90, angle, abs_tol=3):
            # if angle > 90:
            # Calculate the miter ratio of the corner
            miter_ratio = 1 / math.sin(math.radians(angle / 2))
            # Check if the miter ratio is less than a threshold
            if miter_ratio < 1.5:
                vertices.append(curr_coord)
    midpoints, segments = get_segment_midpoints(Polygon(vertices))
    # find the farthest up, down, left, and right points in the polygon
    farthest_up = Point(max(midpoints.exterior.coords, key=lambda p: p[1]))
    farthest_down = Point(min(midpoints.exterior.coords, key=lambda p: p[1]))
    farthest_left = Point(min(midpoints.exterior.coords, key=lambda p: p[0]))
    farthest_right = Point(max(midpoints.exterior.coords, key=lambda p: p[0]))
    all_pts = list(midpoints.exterior.coords)
    north_data = [Point(i) for i in segments[all_pts.index((farthest_up.x, farthest_up.y))]]
    south_data = [Point(i) for i in segments[all_pts.index((farthest_down.x, farthest_down.y))]]
    east_data = [Point(i) for i in segments[all_pts.index((farthest_right.x, farthest_right.y))]]
    west_data = [Point(i) for i in segments[all_pts.index((farthest_left.x, farthest_left.y))]]
    all_pts_full = list(polygon.exterior.coords)
    north_bound_1, north_bound_2 = all_pts_full.index((north_data[0].x, north_data[0].y)), all_pts_full.index(
        (north_data[1].x, north_data[1].y))
    south_bound_1, south_bound_2 = all_pts_full.index((south_data[0].x, south_data[0].y)), all_pts_full.index(
        (south_data[1].x, south_data[1].y))
    east_bound_1, east_bound_2 = all_pts_full.index((east_data[0].x, east_data[0].y)), all_pts_full.index(
        (east_data[1].x, east_data[1].y))
    west_bound_1, west_bound_2 = all_pts_full.index((west_data[0].x, west_data[0].y)), all_pts_full.index(
        (west_data[1].x, west_data[1].y))

    # Define the bounds for each direction as a tuple of (start_index, end_index)
    bounds = [(north_bound_1, north_bound_2),
              (south_bound_1, south_bound_2),
              (east_bound_1, east_bound_2),
              (west_bound_1, west_bound_2)]

    # Define the names for each direction
    directions = ['north', 'south', 'east', 'west']

    # Loop over the directions
    for i, dir in enumerate(directions):
        start, end = bounds[i]
        if end == 0:
            # If end is 0, wrap around to the beginning of the list
            pts = all_pts_full[start:] + all_pts_full[:1]
        else:
            pts = all_pts_full[start:end + 1]
        if dir == 'north':
            north_pts = pts
        elif dir == 'south':
            south_pts = pts
        elif dir == 'east':
            east_pts = pts
        elif dir == 'west':
            west_pts = pts


def interpolatePoint(lst):
    for i in range(len(lst)):
        if lst[i][1] == -1:
            if i == 0:
                lst[i][1] = lst[i + 1][1]
            elif i == len(lst):
                lst[i][1] = lst[i - 1][1]
        if lst[i][2] == -1:
            if i == 0:
                lst[i][2] = lst[i + 1][2]
            elif i == len(lst):
                lst[i][2] = lst[i - 1][2]

        if lst[i][1] == -1:
            next_inc, prev_inc = lst[i + 1][1], lst[i - 1][1]
            next_depth, prev_depth, target_depth = lst[i + 1][0], lst[i - 1][0], lst[i][0]
            interpolated_inc = ((next_inc - prev_inc) / (next_depth - prev_depth)) * (
                    target_depth - prev_depth) + prev_inc
            lst[i][1] = interpolated_inc
        if lst[i][2] == -1:
            next_azi, prev_azi = lst[i + 1][2], lst[i - 1][2]
            next_depth, prev_depth, target_depth = lst[i + 1][0], lst[i - 1][0], lst[i][0]
            interpolated_azi = ((next_azi - prev_azi) / (next_depth - prev_depth)) * (
                    target_depth - prev_depth) + prev_azi
            lst[i][2] = interpolated_azi
    return lst


def closest_point_on_line(point, line_start, line_end):
    """
  Finds the point on the line segment (line_start, line_end) closest to the given point.

  Args:
    point: A tuple (x, y) representing the point.
    line_start: A tuple (x, y) representing the start of the line segment.
    line_end: A tuple (x, y) representing the end of the line segment.

  Returns:
    A tuple (x, y) representing the closest point on the line segment.
  """

    # Vector from line start to point
    point_vec = (point[0] - line_start[0], point[1] - line_start[1])
    # Vector from line start to end
    line_vec = (line_end[0] - line_start[0], line_end[1] - line_start[1])

    # Project point_vec onto line_vec
    projection = (point_vec[0] * line_vec[0] + point_vec[1] * line_vec[1]) / (line_vec[0] ** 2 + line_vec[1] ** 2)

    # Check if projection is within the line segment
    if projection <= 0:
        return line_start
    elif projection >= 1:
        return line_end
    else:
        # Calculate projected point
        projected_point = (line_start[0] + projection * line_vec[0], line_start[1] + projection * line_vec[1])
        return projected_point


def bearingFromPoints(p1, p2):
    distance = equationDistance(p1[0], p1[1], p2[0], p2[1])
    azimuth = angleBetweenPoints(p1, p2)
    bearing = azimuth_to_bearing(azimuth)
    direction = bearing[0]
    degrees, minutes, seconds = map(int, bearing[1:-1].replace('°', ' ').replace("'", ' ').replace('"', ' ').split())
    quadrant = bearing[-1]
    dir_val = direction + quadrant

    return bearing, degrees, minutes, seconds, dir_val, azimuth, distance


# def testerBearings2(data, labels):
#     factors = {'NE': [1, 1],
#                'SE': [180, -1],
#                'SW': [180, 1],
#                'NW': [360, -1], }
#     data = [i for i in data if i[11] != 0]
#     lst = []
#     for i in range(len(data)):
#         if len(data[i]) > 6:
#             data[i] = data[i][6:12]
#         side, deg, min, sec, dir_val = float(data[i][1]), float(data[i][2]), float(data[i][3]), float(data[i][4]), int(float(data[i][5]))
#         decimal_degrees = round(deg + (min / 60) + (sec / 3600), 3)
#         if 'north' in data[i][0].lower() or 'east' in data[i][0].lower():
#             decimal_degrees = (decimal_degrees - 180) % 360
#         dir_val_str = labels[dir_val]
#         direction, final_direction = dir_val_str[:1], dir_val_str[1:]
#         lst.append([data[i][0], f"{direction}{str(decimal_degrees)}{final_direction}"])
#
#     columns = ['Length', 'Bearing']
#     dir_lst = [{'Length': i[0], 'Bearing': i[1]} for i in lst]
#     df_used = pd.DataFrame(data=dir_lst, columns=columns)
#     factors = pd.DataFrame(factors).T
#     f = df_used['Bearing'].str[0] + df_used['Bearing'].str[-1]
#     df_used['Azimuth'] = (factors.loc[f, 0].tolist() + (df_used['Bearing'].str.strip('NESW').astype(float) * factors.loc[f, 1].tolist())) % 360

def translatePlatRelativeMeasurementsToXY(data):
    def runProcessMultiple(output_data, conv_angle):
        output_data = [[adjustAzimuthForGridConvergence(True, conv_angle, i[0]), i[1]] for i in output_data]
        coordinates = calculate_section_coordinates(output_data)

        target_x, target_y = 10000, 10000
        current_centroid = Polygon(coordinates).centroid

        # Calculate the shift required
        shift_x = target_x - current_centroid.x
        shift_y = target_y - current_centroid.y

        # Shift the polygon
        shifted_polygon = translate(Polygon(coordinates), xoff=shift_x, yoff=shift_y)
        return list(shifted_polygon.exterior.coords)
    labels = {1: 'SE', 2: 'NE', 3: 'SW', 4: 'NW'}
    data = reorderDecimalData(data)
    conv_angle = 0
    # testerBearings2(data, labels)

    output_data = [assembleDataFromRelativeToAziLength(data, i, labels) for i, val in enumerate(data)]
    output_data = [i for i in output_data if i is not None]
    used_data = []
    polygon1 = Polygon([(7362.711568510507, 9949.759438062792), (7336.798182683527, 11267.78876877188), (7310.883327040539, 12585.818952499725), (8629.418550137565, 12610.903073233878), (9947.953271266464, 12636.123381631724), (11266.53988215857, 12661.348709717691), (12585.075577696698, 12686.709274021123), (12611.17297927156, 11368.609995804518), (12637.218222053823, 10050.510094231226), (12663.312365754307, 8732.412456434837), (12689.353838851473, 7414.314424940774), (11370.634901843845, 7389.088473495062), (10051.96786116115, 7363.868493180649), (8733.249409717704, 7338.783453810443), (7414.5833565680805, 7313.7036637843175), (7388.623235176896, 8631.730894755163), (7362.711568510507, 9949.759438062792)])
    match_percent = 0
    match_conv_angle = 0
    for i in range(-20000, 20000):
        polygon2 = Polygon(runProcessMultiple(output_data, i/10000))
        intersection = polygon1.intersection(polygon2)

        # Calculate the union of the two polygons
        union = polygon1.union(polygon2)

        # Calculate the Intersection over Union (IoU)
        iou = intersection.area / union.area

        # Calculate the percentage of overlap
        overlap_percentage = iou * 100
        # if percentage_not_contained < 0.1:
        if overlap_percentage > match_percent:
            match_percent = overlap_percentage
            match_conv_angle = i/10000

        # used_data.append(runProcessMultiple(output_data, i/20))
    #     # print(i/10)


    # fig, ax = plt.subplots()
    # # colors = ['black', 'red', 'yellow', 'blue']
    # #
    # # counter = 0
    # for i in used_data:
    #     x1, y1 = [k[0] for k in i], [k[1] for k in i]
    #     plt.plot(x1, y1, c='black')
    #     # counter += 1
    # counter = 0
    # #
    # # # plt.scatter([shl[0]], [shl[1]], c='black')
    # plt.show()
    #

    output_data = [[adjustAzimuthForGridConvergence(True, match_conv_angle, i[0]), i[1]] for i in output_data]
    coordinates = calculate_section_coordinates(output_data)

    target_x, target_y = 10000, 10000
    current_centroid = Polygon(coordinates).centroid

    # Calculate the shift required
    shift_x = target_x - current_centroid.x
    shift_y = target_y - current_centroid.y

    # Shift the polygon
    shifted_polygon = translate(Polygon(coordinates), xoff=shift_x, yoff=shift_y)


# 27851741.804064814
# 27818882.181834493
def assembleDataFromRelativeToAziLength(data, i, labels):
    if len(data[i]) > 6:
        data[i] = data[i][6:12]
    side, deg, min, sec, dir_val = float(data[i][1]), float(data[i][2]), float(data[i][3]), float(data[i][4]), int(float(data[i][5]))
    if side != 0:

        dir_val_str = labels[dir_val]
        dir_val_str = refineDirectionValue(data[i][0], dir_val_str)
        direction, final_direction = dir_val_str[:1], dir_val_str[1:]
        azi = bearing_to_azimuth(direction, deg, min, sec, final_direction)


        return [azi, side]


def refineDirectionValue(label, dir_val):
    if 'east' in label.lower():
        if dir_val == 'NW':
            return 'SE'
        elif dir_val == 'NE':
            return 'SW'

    if 'west' in label.lower():
        if dir_val == 'SE':
            return 'NW'
        elif dir_val == 'SW':
            return 'NE'

    if 'north' in label.lower():
        if dir_val == 'SW':
            return 'NE'
        elif dir_val == 'SE':
            return 'NW'
    #
    if 'south' in label.lower():
        if dir_val == 'NE':
            return 'SW'
        elif dir_val == 'NW':
            return 'SE'
    return dir_val


def get_segment_midpoints(poly):
    # Get the midpoints of all segments in a polygon.
    # Returns a list of (x, y) tuples representing the midpoints.
    midpoints = []
    segments = []
    if isinstance(poly, Polygon):
        boundary = [poly.exterior] + list(poly.interiors)
    elif isinstance(poly, MultiPolygon):
        boundary = [p.exterior for p in poly] + [hole for p in poly for hole in p.interiors]
    else:
        raise ValueError("Input must be a Polygon or MultiPolygon")
    for line in boundary:
        for i in range(1, len(line.coords)):
            start = line.coords[i - 1]
            end = line.coords[i]
            midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
            midpoints.append(midpoint)
            segments.append([start, end])
    return Polygon(midpoints), segments


def azimuth_to_xy(start_x, start_y, azimuth, distance):
    """Convert azimuth and distance to XY coordinates."""
    # Convert azimuth to radians
    azimuth_rad = math.radians(azimuth)

    # Calculate change in x and y
    dx = distance * math.sin(azimuth_rad)
    dy = distance * math.cos(azimuth_rad)

    # Calculate new x and y
    new_x = start_x + dx
    new_y = start_y + dy

    return new_x, new_y


def calculate_section_coordinates(segments):
    """Calculate coordinates for all points in the section."""
    coordinates = [(0, 0)]  # Start at (0, 0)
    current_x, current_y = 0, 0

    for azimuth, distance in segments:
        new_x, new_y = azimuth_to_xy(current_x, current_y, azimuth, distance)
        coordinates.append((new_x, new_y))
        current_x, current_y = new_x, new_y

    return coordinates


def azimuth_to_bearing(azimuth):
    # Ensure azimuth is within 0-360 range
    azimuth = azimuth % 360

    # Determine the quadrant and calculate the angle within the quadrant
    if 0 <= azimuth < 90:
        quadrant = "N{:02d}°{:02d}'{:02d}\"E"
        angle = azimuth
    elif 90 <= azimuth < 180:
        quadrant = "S{:02d}°{:02d}'{:02d}\"E"
        angle = 180 - azimuth
    elif 180 <= azimuth < 270:
        quadrant = "S{:02d}°{:02d}'{:02d}\"W"
        angle = azimuth - 180
    else:  # 270 <= azimuth < 360
        quadrant = "N{:02d}°{:02d}'{:02d}\"W"
        angle = 360 - azimuth

    # Convert decimal degrees to degrees, minutes, seconds
    degrees = int(angle)
    minutes = int((angle - degrees) * 60)
    seconds = int(((angle - degrees) * 60 - minutes) * 60)

    # Format the bearing string
    bearing = quadrant.format(degrees, minutes, seconds)

    return bearing


def bearing_to_azimuth(direction, degrees, minutes, seconds, final_direction):
    decimal_degrees = degrees + (minutes / 60) + (seconds / 3600)
    # Calculate the azimuth based on the quadrant
    if direction == 'S' and final_direction == 'E':
        azimuth = 180 - decimal_degrees
    elif direction == 'S' and final_direction == 'W':
        azimuth = 180 + decimal_degrees
    elif direction == 'N' and final_direction == 'W':
        azimuth = 360 - decimal_degrees
    elif direction == 'N' and final_direction == 'E':
        azimuth = decimal_degrees
    # Ensure the azimuth is within 0-360 range
    azimuth = azimuth % 360
    return azimuth


def adjustAzimuthForGridConvergence(is_grid, angle, azimuth):
    if is_grid:
        # Converting from grid to true
        azimuth += angle
    else:
        # Converting from true to grid
        azimuth -= angle

    return azimuth

def decdeg2dms(dd):
    dd = float(dd)
    is_positive = dd >= 0
    dd = abs(dd)
    minutes, seconds = divmod(dd * 3600, 60)
    degrees, minutes = divmod(minutes, 60)
    degrees = degrees if is_positive else -degrees
    return degrees, minutes, seconds
def dms_to_decimal(lst):
    degrees, minutes, seconds = lst[0], lst[1], lst[2]
    """Convert degrees, minutes, seconds to decimal degrees."""
    return degrees + minutes / 60 + seconds / 3600

def findDistances(pt1, pt2, pt3):
    def decimialify(pt):
        return pt[0] + (pt[1]/60) + (pt[2]/3600)
    # pt1 = decimialify([40,17,26.04446]), decimialify([110,9,42.444])*-1
    # pt2 = decimialify([40,17,12.98917]), decimialify([110,9,42.44928]) *-1
    pt1 = decimialify([pt1[0][0],pt1[0][1],pt1[0][2]]), decimialify([pt1[1][0],pt1[1][1],pt1[1][2]])*-1
    pt2 = decimialify([pt2[0][0],pt2[0][1],pt2[0][2]]), decimialify([pt2[1][0],pt2[1][1],pt2[1][2]])*-1
    # pt1 = [40.28694143805556, -110.16179146666667]
    # pt2 = [40.28701516666667, -110.14321536111111]

    # pt3 = [40.287290, -110.159837]
    pt1_utm = utm.from_latlon(pt1[0], pt1[1])[:2]
    pt2_utm = utm.from_latlon(pt2[0], pt2[1])[:2]
    pt3_utm = utm.from_latlon(pt3[0], pt3[1])[:2]

    line_point1 = np.array(pt1_utm)
    line_point2 = np.array(pt2_utm)
    point = np.array(pt3_utm)

    # Calculate the direction vector of the line
    line_vec = line_point2 - line_point1

    # Calculate the vector from line_point1 to the point
    point_vec = point - line_point1

    # Calculate the unit vector of the line
    line_unit_vec = line_vec / np.linalg.norm(line_vec)

    # Calculate the projection of point_vec onto the line
    projection = np.dot(point_vec, line_unit_vec) * line_unit_vec

    # Calculate the perpendicular vector
    perpendicular_vec = point_vec - projection

    # Calculate the shortest distance
    shortest_distance = np.linalg.norm(perpendicular_vec)
