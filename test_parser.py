import pyproj

import GUIDataAdd
import time
from sympy import Point, Line
from haversine import haversine, Unit
from scipy.spatial import ConvexHull
import math

import pandas as pd
from shapely.geometry import Point, LineString
from shapely.geometry.polygon import Polygon
import operator
import ModuleAgnostic as ma
from shapely.geometry import Point, LineString
from shapely.ops import nearest_points, polygonize
from shapely import MultiPoint
import copy
import utm
import itertools
import matplotlib.pyplot as plt
import sqlite3
import openpyxl
import wellMinimumCurvatureCalculation as wmc
from shapely.ops import unary_union

"""Adjust the wellpath by the shl location"""


def adjustWellPathBySHLLocation(well_path, shl):
    x_adjust, y_adjust = float(shl[0]), float(shl[1])
    new_well_path = [[j[0] + x_adjust, j[1] + y_adjust] for j in well_path]
    return new_well_path


"""Chart the sections that the wellbore passes through"""


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


def editDFForTriangulator(df, versions, v_labels, conc_data):
    used_labels = [v_labels[i][versions[i]] for i in range(len(v_labels))]
    original_df = copy.deepcopy(df)
    df_used = original_df[(original_df['new_code'] == conc_data[0]) & (original_df['Version'] == used_labels[0])]
    for i in range(1, len(conc_data)):
        df_used = pd.concat([df_used, original_df[(original_df['new_code'] == conc_data[i]) & (original_df['Version'] == used_labels[i])]])

    df_unused = original_df[~original_df['new_code'].isin(conc_data)]

    df_final = pd.concat([df_used, df_unused])

    return df_final


def triangulatorWithKnownData(tsr_data, well_path, pts, df, conc, survey_data, well_parameter_data, shl, versions, conc_data, v_labels):
    survey_data = alterSurveyForLargeSpacingBetweenPts(survey_data)

    used_points = [pts[i][versions[i]] for i in range(len(pts))]
    used_labels = [v_labels[i][versions[i]] for i in range(len(v_labels))]
    plat_north_refs = []
    known_conc_data = [conc]
    for i in range(len(used_labels)):
        if used_labels[i] != 'GENERIC':
            plat_north_refs.append(df[(df['new_code'] == conc_data[i]) & (df['Version'] == used_labels[i])].to_numpy().tolist()[0][-3])
        else:
            plat_north_refs.append('T')
    min_curv_data = [survey_data[0] + [0] * 11]
    survey_data = survey_data[1:]
    section_degrees_data = [used_points[0]]
    data = used_points[0]
    counter = 0
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
    used_index = 0
    md_lst = [i[0] for i in survey_data]
    inc_lst = [i[1] for i in survey_data]
    azi_lst = [i[2] for i in survey_data]
    north_reference, magnetic_declination, convergence_angle, target_azimuth = well_parameter_data[0], well_parameter_data[1], float(well_parameter_data[2]), float(well_parameter_data[3])
    wmc_output = wmc.mainCalculation(md_lst, inc_lst, azi_lst, convergence_angle, north_reference, plat_north_refs[used_index], magnetic_declination, target_azimuth)
    prev_section_data = tsr_data[0][6:]
    while True:
        corners, sides_generated = ma.cornerGeneratorProcess(data)
        sides_generated = [[j[:-1] for j in i] for i in sides_generated]
        segment_lst = [[[i[j], i[j + 1]] for j in range(len(i) - 1)] for i in sides_generated]
        time_start = time.perf_counter()
        intersection, direction, well_index_end, min_curv_data, well_path_tester = findWellPathBoundaryIntersection(segment_lst, survey_data, well_parameter_data, plat_north_refs[used_index], min_curv_data, shl)
        if not well_path_tester or direction == 'Null':
            return min_curv_data, section_degrees_data, plat_north_refs
        index = dirLst.index(direction)
        new_section = lst[section][index]
        township, townshipDir, rng, rngDir, prev_section_data = modifySection(section, new_section, prev_section_data)
        new_conc = ma.reTranslateData([new_section, township, townshipDir, rng, rngDir, tsr_data[0][-1]])
        old_well_path_tester = well_path_tester[:well_index_end + 1]
        proxBoo = getBooProx(data, old_well_path_tester, direction)
        try:
            used_index = conc_data.index(new_conc)
            rewritten_coords = coordsAdjuster(used_points[used_index], data, direction, proxBoo)
        except ValueError:
            data_new = df[df['new_code'] == new_conc]
            df_conc_used_v = data_new[(data_new['Version'] != 'AGRC V.1')].to_numpy().tolist()
            data_new = sorted(df_conc_used_v, key=lambda x: x[-1], reverse=True)
            plat_north_ref = data_new[0][-3]
            data_new_dec = ma.convertToDecimal(copy.deepcopy(data_new))
            data_new_deg = ma.pointsConverter(data_new_dec)
            # data_new_deg, data_new_dec = ma.dataConverterPlatToUtm(data_new)
            rewritten_coords = coordsAdjuster(data_new_deg, data, direction, proxBoo)

        data = rewritten_coords
        if new_conc not in known_conc_data:
            known_conc_data.append(new_conc)
            section_degrees_data.append(data)
            counter += 1

        section = new_section

    return min_curv_data, section_degrees_data, plat_north_refs


def sideDetermine(side):
    if side == 'S':
        return 1
    elif side == 'W':
        return 2
    elif side == 'N':
        return 3
    elif side == 'E':
        return 0
    else:
        return "NULL"


def mainTriangulator(conn, tsr_data, data, df, conc, survey_data, well_parameter_data, shl):
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


def roundMinCurv(lst):
    return [[round(lst[i][j], 2) for j in range(len(lst[i]))] for i in range(len(lst))]


def adjustIntersection(direction, intersection, well_path, data_lst):
    if direction.lower() == 'e':
        transform_x, transform_y = -1 * intersection[0], 0
    well_path = [[i[0] + transform_x, i[1] + transform_y] for i in well_path]
    return well_path


def findIntersectionBetweenWellAndSection(segment_lst, available_well_path, shl):
    direction = ['W', 'N', 'E', 'S']
    # offset_pts_lst = [[i[8] + shl[0], i[7] + shl[1]] for i in min_curv_data]
    for i in range(len(available_well_path) - 1):
        well_polyline = LineString([available_well_path[i], available_well_path[i + 1]])
        for j in range(len(segment_lst)):
            side_list = list(itertools.chain.from_iterable(segment_lst[j]))
            side_list = ma.findUniqueListsInListOfLists(side_list)
            side_list = ma.sortPointsInClockwisePattern(side_list)
            side_polyline = LineString(side_list)
            if well_polyline.intersects(side_polyline):
                return available_well_path[i:], direction[j]
            #


# def findWellPathBoundaryIntersection(well_path, segment_lst, survey_data, well_parameter_data, plat_ref, min_curv_data, shl):
def findWellPathBoundaryIntersection(segment_lst, survey_data, well_parameter_data, plat_ref, min_curv_data, shl):
    direction = ['W', 'N', 'E', 'S']
    north_reference, magnetic_declination, convergence_angle, target_azimuth = well_parameter_data[0], well_parameter_data[1], float(well_parameter_data[2]), float(well_parameter_data[3])
    md_lst, inc_lst, azi_lst = [i[0] for i in survey_data], [i[1] for i in survey_data], [i[2] for i in survey_data]
    bearing_lst = [wmc.bearing(float(azi_lst[i]), float(convergence_angle), north_reference, plat_ref, float(magnetic_declination)) for i in range(len(md_lst))]
    section_offset_lst = []
    if len(min_curv_data) > 0:
        offsetNS_lst, offsetEW_lst, tvd_lst = [i[7] for i in min_curv_data], [i[8] for i in min_curv_data], [i[6] for i in min_curv_data]
        dogLeg_lst, fFactor_lst = [i[4] for i in min_curv_data], [i[5] for i in min_curv_data]
        bhl_dep_lst, bhl_dir_lst, delta_ns_lst, delta_ew_lst, vert_sec_lst = [i[9] for i in min_curv_data], [i[10] for i in min_curv_data], [i[12] for i in min_curv_data], [i[13] for i in min_curv_data], [i[11] for i in min_curv_data]
        offset_pts_lst = [[offsetEW_lst[i] + shl[0], offsetNS_lst[i] + shl[1]] for i in range(len(offsetNS_lst))]
        output = min_curv_data

    for i in range(len(min_curv_data), len(bearing_lst)):
        dogLeg_lst.append(wmc.dogLegAngle(inc_lst[i - 1], inc_lst[i], bearing_lst[i - 1], bearing_lst[i]))
        fFactor_lst.append(wmc.fFactor(dogLeg_lst[i]))
        tvd_lst.append(wmc.tvd(md_lst[i - 1], md_lst[i], inc_lst[i - 1], inc_lst[i], fFactor_lst[i], tvd_lst[i - 1]))
        offsetNS_lst.append(wmc.offsetNS(fFactor_lst[i], md_lst[i - 1], md_lst[i], bearing_lst[i - 1], bearing_lst[i], inc_lst[i - 1], inc_lst[i], offsetNS_lst[i - 1]))
        offsetEW_lst.append(wmc.offsetEW(fFactor_lst[i], md_lst[i - 1], md_lst[i], bearing_lst[i - 1], bearing_lst[i], inc_lst[i - 1], inc_lst[i], offsetEW_lst[i - 1]))
        bhl_dep_lst.append(wmc.bhlDeparture(offsetNS_lst[i], offsetEW_lst[i]))
        bhl_dir_lst.append(wmc.bhl_Direction(float(offsetNS_lst[i]), float(offsetEW_lst[i])))
        delta_ns_lst.append(wmc.deltaNS(md_lst[i - 1], md_lst[i], fFactor_lst[i], bearing_lst[i - 1], bearing_lst[i], inc_lst[i - 1], inc_lst[i]))
        delta_ew_lst.append(wmc.deltaEW(md_lst[i - 1], md_lst[i], fFactor_lst[i], bearing_lst[i - 1], bearing_lst[i], inc_lst[i - 1], inc_lst[i]))
        vert_sec_lst.append(wmc.verticalSection(target_azimuth, offsetNS_lst[i], offsetEW_lst[i]))
        offset_pts_lst.append([offsetEW_lst[i] + shl[0], offsetNS_lst[i] + shl[1]])
        section_offset_lst.append(offset_pts_lst[-1])
        output.append([md_lst[i], inc_lst[i], azi_lst[i], bearing_lst[i], dogLeg_lst[i], fFactor_lst[i], tvd_lst[i], offsetNS_lst[i], offsetEW_lst[i], bhl_dep_lst[i], bhl_dir_lst[i], vert_sec_lst[i], delta_ns_lst[i], delta_ew_lst[i]])
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


def areAllPointsInsidePolygon(polygon, lst):
    polygon = Polygon(polygon)
    for i in lst:
        pt = Point(i)
        if not polygon.contains(pt):
            return False
    return True


def getBooProx(coordinates, inside_pts, direction):
    side_bounds = Polygon(coordinates).bounds
    north_bound, south_bound, east_bound, west_bound = side_bounds[3], side_bounds[1], side_bounds[2], side_bounds[0]
    inside_pt_ns, inside_pt_ew = inside_pts[-1][1], inside_pts[-1][0]
    n_diff, s_diff = abs(north_bound - inside_pt_ns), abs(south_bound - inside_pt_ns)
    e_diff, w_diff = abs(east_bound - inside_pt_ew), abs(west_bound - inside_pt_ew)
    ns_diffs, ew_diffs = [n_diff, s_diff], [e_diff, w_diff]

    if direction.lower() in ['n', 's']:
        ew_prox, minDiff = min(enumerate(ew_diffs), key=operator.itemgetter(1))
        if ew_prox == 0:
            sideProximal = False
            # sideProximal = True
        elif ew_prox == 1:
            sideProximal = True
            # sideProximal = False
        return sideProximal
    elif direction.lower() in ['e', 'w']:
        ns_prox, minDiff = min(enumerate(ns_diffs), key=operator.itemgetter(1))
        if ns_prox == 1:
            sideProximal = False
            # sideProximal = True
        elif ns_prox == 0:
            sideProximal = True
            # sideProximal = False
        return sideProximal


def coordsRewriter(last_coords, new_coords, direction, direction_boo):
    # 0 - N, 1 - E, 2 - S, 3 - W
    return coordsAdjuster(new_coords, last_coords, direction, direction_boo)


def coordsAdjuster(new_coords, last_coords, direction, direction_boo):
    colors = ['black', 'red', 'yellow', 'blue']
    last_coords_set = [tuple(i) for i in last_coords]
    directions_dict = {"W": '0', "N": '1', "E": "2", "S": "3"}
    direction = directions_dict[direction]
    test_corners, old_data_organized = ma.cornerGeneratorProcess(last_coords)
    old_data_organized = [[j[:2] for j in i] for i in old_data_organized]
    old_data_organized = [[[round(k, 1) for k in j] for j in i] for i in old_data_organized]
    old_data_organized = [ma.findUniqueListsInListOfLists(i) for i in old_data_organized]

    lst_dict = {"0": [0, 4], "1": [4, 8], "2": [8, 12], "3": [12, 16]}
    matched_lst_dict = {"0": [12, 8], "1": [16, 12], "2": [4, 0], "3": [8, 4]}
    opp_direction_list = {"0": '2', "1": '3', "2": '0', "3": '1'}
    lst_dict_boo = {True: 0, False: 1}
    starting_pts = lst_dict[str(direction)][lst_dict_boo[direction_boo]]
    matched_pt = matched_lst_dict[str(direction)][lst_dict_boo[direction_boo]]

    new_coords = [list(i) for i in new_coords]
    diff_x, diff_y = last_coords[starting_pts][0] - new_coords[matched_pt][0], last_coords[starting_pts][1] - new_coords[matched_pt][1]
    new_coords_test = [[i[0] + diff_x, i[1] + diff_y] for i in new_coords]

    test_corners, new_coords_test_organized = ma.cornerGeneratorProcess(new_coords_test)
    new_coords_test_organized = [[j[:2] for j in i] for i in new_coords_test_organized]
    # ma.grapher1(new_coords_test_organized, 'after')
    new_coords_test_organized = [[[round(k, 1) for k in j] for j in i] for i in new_coords_test_organized]
    new_coords_test_organized = [ma.findUniqueListsInListOfLists(i) for i in new_coords_test_organized]
    # ma.grapher1(new_coords_test_organized, 'after')
    new_coords_test_organized[int(opp_direction_list[str(direction)])] = old_data_organized[int(direction)][::-1]

    return new_coords_test


def modifySection(prev, new, section_data):
    previous_section_data = section_data
    township_dir = ma.translateNumberToDirection('township', str(previous_section_data[2]))
    rng_dir = ma.translateNumberToDirection('rng', str(previous_section_data[4]))

    township = int(float(previous_section_data[1]))  # , int(float(previous_section_data[2]))
    rng = int(float(previous_section_data[3]))  # , int(float(previous_section_data[4]))
    # ts_dir = int(float(previous_section_data[2]))
    # rng_dir = int(float(previous_section_data[4 ]))
    if prev in [1, 12, 13, 24, 25, 36] and new in [6, 7, 18, 19, 30, 31]:
        if rng == 1:
            rng = 1
            rng_dir = 'E'
        else:
            rng = rng - 1
    if prev in [6, 7, 18, 19, 30, 31] and new in [1, 12, 13, 24, 25, 36]:
        if rng == 1:
            rng = 1
            rng_dir = 'W'
        else:
            rng = rng + 1
    if prev in [6, 5, 4, 3, 2, 1] and new in [31, 32, 33, 34, 35, 36]:
        if township_dir == 'S':
            if township == 1:
                township = 1
                township_dir = "N"
            else:
                township = township - 1
        else:
            township = township + 1
        # if township == 1:
        #     township = 1
        #     township_dir = "N"
        # else:
        #     township = township + 1
    if prev in [31, 32, 33, 34, 35, 36] and new in [6, 5, 4, 3, 2, 1]:
        if township == 1:
            township = 1
            township_dir = "S"
        else:
            township = township - 1
    prev_section_data = [new, int(float(township)), township_dir, int(float(rng)), rng_dir, previous_section_data[-1]]
    return int(float(township)), township_dir, int(float(rng)), rng_dir, prev_section_data


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
        return int(float(platData[1])), platData[2], int(float(platData[3])), platData[4]

    else:
        township, townshipDir = changeTownship(platData[1], platData[2], direction)
        rng, rngDir = changeRange(platData[3], platData[4], direction)

        return int(float(township)), townshipDir, int(float(rng)), rngDir


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


def adjustPlats():
    pass


def lineSegmentsForManualPointing(data, pt):

    ix, iy = pt[0], pt[1]
    output, ns_side, ew_side = sortAllDataIntoSides(data, pt)
    ns_m1, ns_b1 = ma.slopeFinder(ns_side[0], ns_side[1])
    if ns_m1 == 0:
        ns_m1 = 0.00000001
    ns_m2 = -1 / ns_m1
    ns_b2 = iy - (ns_m2 * ix)
    ew_m1, ew_b1 = ma.slopeFinder(ew_side[0], ew_side[1])
    if ew_m1 == 0:
        ew_m1 = 0.00000000000001
    ew_m2 = -1 / ew_m1
    ew_b2 = iy - (ew_m2 * ix)
    if ew_side[0][0] == ew_side[1][0]:
        intersect_ew = [ew_side[1][0], iy]
    else:
        intersect_ew = ma.lineIntersectionPt(ew_m1, ew_m2, ew_b1, ew_b2)
    if ns_side[0][1] == ns_side[1][1]:
        intersect_ns = [ix, ns_side[1][1]]
    else:
        intersect_ns = ma.lineIntersectionPt(ns_m1, ns_m2, ns_b1, ns_b2)
    pts = [intersect_ns, [ix, iy], intersect_ew]
    mp_ns, mp_ew = [(intersect_ns[0] + ix) / 2, (intersect_ns[1] + iy) / 2], [(intersect_ew[0] + ix) / 2, (intersect_ew[1] + iy) / 2]
    return round(int(float(output[0])), 0), round(int(float(output[2])), 0), mp_ns, mp_ew, ns_side, ew_side, pts


"""Given distances and tsr data, find the relative location of a point. Use for finding starting point"""


def findSurfaceCoordinate(data, tsr_data):
    # def findSurfaceCoordinate(data, ns_dir, ew_dir, ns_d, ew_d):
    data = [data[:5], data[4:9], data[8:13], data[12:]]
    ns_d, ns_dir, ew_d, ew_dir = float(tsr_data[0][1]), tsr_data[0][2], float(tsr_data[0][3]), tsr_data[0][4]
    ns_points = generateParallelLineSegments(data[1], ns_d) if ns_dir == 'FNL' else generateParallelLineSegments(data[3], ns_d)
    ew_points = generateParallelLineSegments(data[0], ew_d) if ew_dir == 'FWL' else generateParallelLineSegments(data[2], ew_d)
    for i in ns_points:
        pt1 = LineString(i)
        for j in ew_points:
            pt2 = LineString(j)
            outcome = pt1.intersection(pt2)
            try:
                intersection = [outcome.x, outcome.y]
                return intersection
            except:
                pass


def generateParallelLineSegments(data, distance):
    output = []
    for i in range(len(data) - 1):
        try:
            line_str_seg = LineString([data[i], data[i + 1]])
            new_data = line_str_seg.parallel_offset(distance, 'right', resolution=1, join_style=2, mitre_limit=5)
            output.append(list(new_data.coords))
        except ValueError:
            pass
    return output


"""Find distances from lease line to a point"""


def findDistancesFromPoint(deg_lst, pt):
    return sortAllDataIntoSides(deg_lst, pt)


def sortAllDataIntoSides(lst, pt):
    ma.printFunctionName()
    ew_labels = ['FEL', 'FWL']
    ns_labels = ['FSL', 'FNL']
    corners, sides_generated = ma.cornerGeneratorProcess(lst)

    sides_generated = [[j[:-1] for j in i] for i in sides_generated]
    left_lst, up_lst, right_lst, down_lst = sides_generated[0], sides_generated[1], sides_generated[2], sides_generated[3]
    left_lst, up_lst, right_lst, down_lst = sorted(left_lst, key=lambda x: x[1]), sorted(up_lst, key=lambda x: x[0]), sorted(right_lst, key=lambda x: x[1], reverse=True), sorted(down_lst, key=lambda x: x[0], reverse=True)
    right_lst_segments = [[right_lst[i], right_lst[i + 1]] for i in range(len(right_lst) - 1)]
    left_lst_segments = [[left_lst[i], left_lst[i + 1]] for i in range(len(left_lst) - 1)]

    down_lst_segments = [[down_lst[i], down_lst[i + 1]] for i in range(len(down_lst) - 1)]
    up_lst_segments = [[up_lst[i], up_lst[i + 1]] for i in range(len(up_lst) - 1)]

    ew_lsts = [right_lst_segments, left_lst_segments]
    ns_lsts = [down_lst_segments, up_lst_segments]
    distance_down, down_index = directionDistanceFinder(down_lst, pt, 'down')
    distance_up, up_index = directionDistanceFinder(up_lst, pt, 'up')
    distance_right, right_index = directionDistanceFinder(right_lst, pt, 'right')
    distance_left, left_index = directionDistanceFinder(left_lst, pt, 'left')
    ns_lst, ew_lst = [distance_down, distance_up], [distance_right, distance_left]

    ns_index_lst, ew_index_lst = [down_index, up_index], [right_index, left_index]

    ew_true_index = ew_lst.index(min(ew_lst))
    ns_true_index = ns_lst.index(min(ns_lst))

    ew_correct_sides = ew_lsts[ew_true_index]
    ns_correct_sides = ns_lsts[ns_true_index]

    ns_index = ns_index_lst[ns_true_index]
    ew_index = ew_index_lst[ew_true_index]

    ns_side = ns_correct_sides[ns_index]
    ew_side = ew_correct_sides[ew_index]

    ew_true_label = ew_labels[ew_true_index]
    ns_true_label = ns_labels[ns_true_index]

    ns_distance = min(ns_lst)
    ew_distance = min(ew_lst)
    return [str(ns_distance), ns_true_label, str(ew_distance), ew_true_label], ns_side, ew_side


def distance_finder(polygon, pt, label):
    line_string = LineString(nearest_points(polygon, pt))
    line_string = line_string.coords
    try:
        pt1 = utm.to_latlon(line_string[0][0], line_string[0][1], 12, 'T')
        pt2 = utm.to_latlon(line_string[1][0], line_string[1][1], 12, 'T')
        output_distance = haversine(pt1, pt2, unit=Unit.FEET)
    except utm.error.OutOfRangeError:
        output_distance = ma.equationDistance(line_string[0][0], line_string[0][1], line_string[1][0], line_string[1][1])


def directionDistanceFinder(lst, pt, dir):

    seen = [set()]
    result = []
    for point in lst:
        if point not in seen:
            result.append(point)
            seen.append(point)
    lst = result
    line_segments = [(lst[i], lst[i + 1]) for i in range(len(lst) - 1)]
    index = sideFinder(lst, pt, dir)
    distance_lst = parallelLineDistancePointFinder(lst, pt)

    # index = sideFinder(lst, pt, dir)
    if index == -1:
        distance = 9999999
    else:
        distance = distance_lst[index]
    return distance, index

def distanceSegmentPoint(segment, point):
    x0, y0 = point[0], point[1]
    x1, y1, x2, y2 = segment[0][0], segment[0][1], segment[1][0], segment[1][1]
    numerator = abs((x2 - x1) * (y1 - y0) - (x1 - x0) * (y2 - y1))
    denominator = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    distance = numerator / denominator
    return distance
def sideFinder(lst, pt, dir):
    pts_used_lst = [[lst[i], lst[i + 1]] for i in range(len(lst) - 1)]
    pts_used_lst = [list(i) for i in pts_used_lst]
    # boo_poly = testSlopeFinderProcess(lst, pt, pts_used_lst)
    polygons = [polygonGenerator(i, pt) for i in pts_used_lst]
    boo_poly = [polygonContainsPoint(i, Point(pt)) for i in polygons]
    if True in boo_poly:

        return boo_poly.index(True)
    return -1


def calculate_slope(point1, point2):
    x1, y1 = point1
    x2, y2 = point2
    if x1 == x2:
        return float('inf')  # Vertical line, slope is infinity
    return (y2 - y1) / (x2 - x1)




# 585071.1239049804, 4440044.967793028, 585069.7832602182, 4441362.657963015
def testSlopeFinderProcess(segments, hole_pt, segments_lst):
    boo_poly = []
    point_C = Point(hole_pt)
    output = parallelLineDistancePointFinder(segments, hole_pt)
    for i in range(len(segments_lst)):
        output[i] = output[i] + output[i]/100
        shape_poly = LineString(segments_lst[i]).buffer(-1 * output[i], single_sided=True)
        new_thing = shape_poly.exterior.coords

        if polygonContainsPoint(shape_poly, point_C):
            boo_poly.append(True)
        else:
            distance_c = shape_poly.exterior.distance(point_C)
            # nearest_point_on_boundary = nearest_points(shape_poly.exterior, point_C)[1]
            # distance_c = point_C.distance(nearest_point_on_boundary)
            boo_poly.append(False)
            # return i
    return boo_poly


def testerFoo(point1, point2, point3):
    point3 = Point(point3)
    # Define the two endpoints of the line segment
    # Calculate the minimum and maximum coordinates
    min_x = min(point1.x, point2.x, point3.x)
    max_x = max(point1.x, point2.x, point3.x)
    min_y = min(point1.y, point2.y, point3.y)
    max_y = max(point1.y, point2.y, point3.y)

    # Create a bounding rectangle
    envelope = Polygon([(min_x, min_y), (min_x, max_y), (max_x, max_y), (max_x, min_y)])

    # Optionally, add the original line segment as a LineString to the envelope
    envelope_with_line = envelope.union(LineString([point1, point2]))
    return envelope_with_line



def polygonContainsPoint(polygon, pt):
    if polygon is not None:
        if polygon.contains(pt):
            return True
    return False


def polygonGenerator(lst, pt):
    tolerance = 5
    tolerance_2 = 50
    buffer_size = 3000
    if 55 > lst[0][0] > 35:
        tolerance = 0.002
        tolerance_2 = 0.02
        buffer_size = 0.11
    distance = [ma.equationDistance(pt[0], pt[1], lst[j][0], lst[j][1]) for j in range(len(lst))]
    if ma.equationDistance(lst[0][0], lst[0][1], lst[1][0], lst[1][1]) > tolerance_2:
    # if not math.isclose(distance[0], distance[1], abs_tol=tolerance):
        shape_poly = LineString(lst).buffer(-1 * buffer_size, single_sided=True)
        return shape_poly
    return None


def parallelLineDistancePointFinder(line, pt):
    in_feet_conversion = 1
    if pt[0] < 100:
        pt = utm.from_latlon(pt[0], pt[1])[:2]
        line = [utm.from_latlon(float(j[0]), float(j[1]))[:2] for j in line]
        in_feet_conversion = 3.28084

    eq_lst = [list(ma.slopeFinder(line[i], line[i + 1])) for i in range(len(line) - 1)]
    pts_lst = [[line[i], line[i + 1]] for i in range(len(line) - 1)]
    eq_lst = [i for i in eq_lst if str(i[0]) != 'nan']  # and i[0] != 0]
    distance_lst = []
    counter = 0
    for i in range(len(eq_lst)):
        x1, x2 = pts_lst[i][0][0], pts_lst[i][1][0]
        y1, y2 = pts_lst[i][0][1], pts_lst[i][1][1]

        if eq_lst[i][0] != 0:
            m = eq_lst[i][0]
            b = pt[1] - (m * pt[0])
            distance_lst.append(dist(m, eq_lst[i][1], b))
        else:
            if x1 == x2:
                distance = abs(pt[0] - line[counter][0])
                distance_lst.append(distance)
            elif y1 == y2:
                distance = abs(pt[1] - line[counter][1])
                distance_lst.append(distance)
        counter += 1
    return distance_lst


def dist(m, b1, b2):
    top = abs(b2 - b1)
    bottom = math.sqrt(m ** 2 + 1)
    d = top / bottom
    return d


def findProximalIndex(lst, pt, dir):
    x, y = pt[0], pt[1]
    eq_lst = [ma.slopeFinder(lst[i], lst[i + 1]) for i in range(len(lst) - 1)]
    eq_lst = [list(i) for i in eq_lst]
    pts_used_lst = [[lst[i], lst[i + 1]] for i in range(len(lst) - 1)]
    pts_used_lst = [list(i) for i in pts_used_lst]
    combo_list = list(zip(pts_used_lst, eq_lst))
    combo_list = [i for i in combo_list if str(i[1][0]) != 'nan']  # and i[1][0] != 0]
    pts_used_lst = [i[0] for i in combo_list]
    eq_lst = [i[1] for i in combo_list]
    polyPt = copy.deepcopy(pt)
    for i in range(len(pts_used_lst)):
        x1, y1 = pts_used_lst[i][0][0], pts_used_lst[i][0][1]
        x2, y2 = pts_used_lst[i][1][0], pts_used_lst[i][1][1]
        m = eq_lst[i][0]
        if m != 0:
            m = 1 / m * -1
            b1 = y1 - (m * x1)
            b2 = y2 - (m * x2)
            line1 = (m * x) + b1 - y
            line2 = (m * x) + b2 - y

            between_line_boo = True if line1 * line2 < 0 else False
            if between_line_boo:
                return i
        if round(m, 1) == 0:
            if x1 == x2:
                if y1 > pt[1] > y2 or y2 > pt[1] > y1:
                    return i
            elif y1 == y2:
                if x1 > pt[0] > x2 or x2 > pt[0] > x1:
                    return i


def changePoints(pt1, pt2, rise, run):
    np1, np2 = [0, 0], [0, 0]
    np1[0], np2[0] = pt1[0] + run, pt2[0] + run
    np1[1], np2[1] = pt1[1] + rise, pt2[1] + rise
    return np1, np2


def mainProcessUTM(lst, shl_coords, surface_relative):
    data_lst = [[i * 0.3048 for i in j] for j in lst]
    surface_relative[0], surface_relative[1] = surface_relative[0] * 0.3048, surface_relative[1] * 0.3048
    lat, lon = float(shl_coords[0]), float(shl_coords[1])  # transform to float
    easting, northing, zone, t_dir = utm.from_latlon(lat, lon)
    easting_diff = easting - surface_relative[0]
    northing_diff = northing - surface_relative[1]
    offset_lst = [[easting_diff + j[0], northing_diff + j[1]] for j in data_lst]
    offset_lst = [utm.to_latlon(offset_lst[i][0], offset_lst[i][1], 12, 'T') for i in range(len(offset_lst))]
    return offset_lst


def lineSegmentCalculator(xy1, xy2, direct, cardinal_dir):
    x1, y1, x2, y2 = xy1[0], xy1[1], xy2[0], xy2[1]
    r = math.sqrt(((x2 - x1) ** 2) + ((y2 - y1) ** 2))
    m, b = ma.slopeFinder(xy1, xy2)
    data_out = []
    if r != 0:
        delta_x = (direct / r) * (xy1[1] - xy2[1])
        delta_y = (direct / r) * (xy2[0] - xy1[0])
        x3, y3 = xy1[0] - delta_x, xy1[1] - delta_y
        x4, y4 = xy2[0] - delta_x, xy2[1] - delta_y
        data_out = [[x3, y3], [x4, y4]]
    if r == 0:
        if cardinal_dir == 'ns':
            y1 = y1 + direct
            y2 = y2 + direct
        else:
            x1 = x1 + direct
            x2 = x2 + direct
        data_out = [[x1, y1], [x2, y2]]
    return data_out


def detectIntersectionParseProcess(ns, ew):
    for i in range(len(ns)):
        for j in range(len(ew)):
            line_ns = LineString([Point(ns[i][0]), Point(ns[i][1])])
            line_ew = LineString([Point(ew[j][0]), Point(ew[j][1])])
            outcome = line_ns.intersection(line_ew)
            try:
                intersection = [outcome.x, outcome.y]
                return intersection, ns[i], ew[j], i, j
            except AttributeError:
                pass


def distance_point_to_segment(point, segment_start, segment_end):
    # Check if the segment has length zero
    if segment_start == segment_end:
        return math.dist(point, segment_start)

    # Calculate the vector representing the line segment
    segment_vector = tuple(map(lambda x, y: x - y, segment_end, segment_start))

    # Calculate the vector representing the point relative to the start of the line segment
    point_vector = tuple(map(lambda x, y: x - y, point, segment_start))

    # Calculate the dot product of the point vector and the line segment vector
    dot_product = sum(map(lambda x, y: x * y, point_vector, segment_vector))

    # Calculate the length squared of the line segment
    segment_length_squared = sum(map(lambda x: x ** 2, segment_vector))

    # Check if the projection of the point onto the line segment falls within the bounds of the line segment
    if dot_product <= 0 or dot_product >= segment_length_squared:
        return False

    # Calculate the projection of the point onto the line segment
    t = dot_product / segment_length_squared
    closest_point = tuple(map(lambda x, y: x + t * y, segment_start, segment_vector))

    # Check if the closest point is the same as the given point, indicating that the point is perpendicular to the line segment
    if closest_point == point:
        distance = 0
    else:
        distance = math.dist(point, closest_point)

    return distance
