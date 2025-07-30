import pandas as pd
import numpy as np
import math
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
import warnings
import pyproj

import time

from scipy.spatial import ConvexHull
import math
from itertools import chain

import pandas as pd

from shapely.geometry import Point, LineString, Polygon



plat_coords_df = pd.read_csv(r'C:\Work\Databases\current_plat_coords_modified.csv')
well_df = pd.read_csv(r'C:\Work\Databases\well_path.csv')
intersection_segment = LineString(list(zip(well_df['n_offset'], well_df['e_offset'])))
polygon_plat = Polygon(plat_coords_df)

for i, row in well_df.iterrows():
    delta_x, delta_y = float(row['delta_x']) * 0.3048, float(row['delta_y']) * 0.3048
    used_pt = [used_pt[0] + delta_x, used_pt[1] + delta_y]
    dir_val, index = get_direction(used_pt, xMin, xMax, yMin, yMax)
    if polygon_plat.contains(Point(used_pt)):
        well_path.at[x, 'rel_plat_conc'] = current_plat_conc
    else:
        try:
            intersection_pt = intersection_segment.intersection(polygon_plat)
# for j in range(len(segment_lst)):
#     for k in range(len(segment_lst[j])):
#         pt1 = LineString([Point(offset_pts_lst[i - 1]), Point(offset_pts_lst[i])])
#         pt2 = LineString([Point(segment_lst[j][k][0]), Point(segment_lst[j][k][1])])
#         outcome = pt1.intersection(pt2)
#         try:
#             intersection = [outcome.x, outcome.y]
#
#             if intersection != [0, 0]:
#                 return intersection, direction[j], i, output, offset_pts_lst
#         except:
#             pass