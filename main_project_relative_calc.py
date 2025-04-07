collections.Iterable = collections.abc.Iterable
collections.Mapping = collections.abc.Mapping
collections.MutableSet = collections.abc.MutableSet
collections.MutableMapping = collections.abc.MutableMapping
import collections.abc
from WCR import *
from PyQt5.QtWidgets import QApplication, QMainWindow, QTableWidgetItem, QApplication, QWidget, QVBoxLayout, \
    QPushButton, QRadioButton, QButtonGroup, QMessageBox, QLabel, QVBoxLayout, QScrollArea
import ModuleAgnostic as ma
import os
from openpyxl import load_workbook
import pyodbc
import wellpathpy as wp
import math
from pyproj import Proj, Geod, Transformer, transform
from PyQt5.QtWidgets import QMainWindow, QApplication, QStyledItemDelegate, QHeaderView, QAbstractItemView, QWidget, QApplication, QMainWindow, QVBoxLayout, QWidget, QSizePolicy
from PyQt5.QtGui import QColor, QStandardItem, QStandardItemModel


class WCR_Main:
    def __init__(self, ui):
        self.ui = ui
        pass

    def load_plat_data(self):
        pass
    def main(self):
        pass