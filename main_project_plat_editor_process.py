import copy
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


class PlatEditorProcess:
    def __init__(self, conn, plat_df, shl, well_df):
        # self.load_surveys()
        self.well_object = well_df
        self.location_db = conn
        self.used_data_df = plat_df
        self.grouped_df = self.find_relevant_datasets()
        self.shl = shl
        # print()
        # print(well_df.columns)
        # for i, j in self.grouped_df:
        #     print(j.columns)
        # query = f"SELECT * FROM section_plat_data"
        # print(pd.read_sql(query, self.location_db))

    def find_relevant_datasets(self):
        used_concs = self.used_data_df['Conc'].unique()
        query = f"select * from section_plat_data"
        output = pd.read_sql(query, self.location_db).drop_duplicates(keep="first")
        output['new_code'] = output['new_code'].apply(lambda row: row[:9])
        output = output[output['new_code'].isin(used_concs)]
        grouped = output.groupby(['new_code', 'Version'])
        return grouped

    def run_finder_process(self):
        


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
            valsAddLst.append(valsLst2[countLst][0] + valsLst2[countLst + 1][0] + valsLst2[countLst + 2][0] + valsLst2[countLst + 3][0])
            valsAddLst2.append(valsLstTot[-1][countLst][0] + valsLstTot[-1][countLst + 1][0] + valsLstTot[-1][countLst + 2][0] + valsLstTot[-1][countLst + 3][0])
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
    valsLst, platWS = ExcelDataValues.getDataVals(path, section, newPlat[1], newPlat[2], newPlat[3], newPlat[4], newPlat[5])
    return valsLst


def getNewCoords(newPlat, section, direction, path, coordLst, valsLstTot):
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
