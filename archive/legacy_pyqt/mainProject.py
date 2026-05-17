from PyQt5.QtWebChannel import QWebChannel
import itertools
import os
import sqlite3
from datetime import datetime
from typing import Callable, Dict, List, Literal, NoReturn, Optional, Set, Tuple, Union
from functools import partial
# Third-party imports - Core Data/Scientific
import numpy as np
from numpy import array, std
import pandas as pd
from pandas import DataFrame, concat, options, read_sql, set_option, to_datetime, to_numeric
import geopandas as gpd
import utm
from sqlalchemy import create_engine
from PyQt5.QtGui import QPainter, QMouseEvent, QGuiApplication, QStandardItemModel, QStandardItem, QFont, QBrush, \
    QPalette, QColor, QDesktopServices
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
# Third-party imports - PyQt5
import PyQt5
from PyQt5.QtCore import QAbstractItemModel, QModelIndex, Qt
from PyQt5.QtGui import QColor, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QGraphicsDropShadowEffect, QHeaderView,
    QHBoxLayout, QLabel, QLayout, QMainWindow, QScrollArea,
    QStyledItemDelegate, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget
)

import tempfile
import matplotlib.pyplot as plt
import urllib
from sqlalchemy import create_engine
from pyproj import Proj, Geod
import time
import copy
from collections import defaultdict
import sqlite3
import os
import numpy as np
import pandas as pd
import pandas.errors
import pyodbc
import ModuleAgnostic as ma
import utm
import warnings
from pyproj import Geod, Proj, CRS
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LTPage, LTChar, LTAnno, LAParams, LTTextBox, LTTextLine
from pdfminer.pdfpage import PDFPage
import plotly.graph_objects as go
import os
import ModuleAgnostic as ma
import pandas as pd
import copy
import pyodbc
import numpy as np
import welleng as we
import sqlalchemy
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLineEdit, QSpinBox,
                             QCheckBox,
                             QDialog, QTabWidget, QTextBrowser, QTableWidget, QLabel, QTableView, QRadioButton,
                             QGraphicsView,
                             QComboBox, QMessageBox, QFileDialog, QButtonGroup)
from matplotlib.collections import PatchCollection
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, QObject, QItemSelectionRange, pyqtSlot
from matplotlib.textpath import TextPath
from matplotlib.patches import PathPatch
from PyQt5.QtGui import QPainter, QMouseEvent, QGuiApplication, QStandardItemModel, QStandardItem, QFont, \
    QDesktopServices, QTextCursor
from matplotlib.ticker import ScalarFormatter, FuncFormatter
from mpl_toolkits.mplot3d.art3d import Line3DCollection
from PyQt5.QtWidgets import QMainWindow, QApplication, QStyledItemDelegate, QHeaderView, QAbstractItemView, QWidget, \
    QApplication, QMainWindow, QVBoxLayout, QWidget, QSizePolicy
# from EngineeringTools3 import Ui_Dialog.
from EToolsLimited import Ui_Dialog
# from GUIWellPlatCompare import WellVisualizer
# from GUIWellPlatAddNew import AddNewPlatToVisualizer
# from GUISurveyTab import SurveyTab
# from GUICasingTab import CasingTab
# from SQLQueries import SQLQueriesClass, DatabaseManager
# from GUIWCRProcess import WCR_Main
# from ExportDataProcess import ExportData
# from GUIClearData import GUIClear
# # from CasingCalculations import Casing
# from WellEngVisualization import WellengVisualizationMain
# import CasingCalculations as cc
# import ScrapeForSurveyData
from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, select, and_, text
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from PyQt5.QtCore import QModelIndex
import time
import keyboard
from welleng.survey import SurveyHeader
import math
import json
from contextlib import contextmanager
from sqlalchemy import create_engine
from urllib.parse import quote_plus
from functools import lru_cache
import logging
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from main_project_survey_process import SurveyProcessBase
from main_project_locations import TownShipAndRangeProcess
from main_project_clearance import ClearanceProcess
from main_project_writer import DataWriter
from main_project_drawer import DataDrawer
from main_project_wcr import WCR_Main
from main_project_import_surveys import SurveyImporter
from PyQt5.QtCore import QAbstractTableModel, Qt

from shapely.geometry import Point, LineString, MultiPoint, Polygon


class DatabaseManager:
    def __init__(self):
        # Initialize the connection
        self.connector = SQLConnector()
        self.engine = self.connector.get_engine()

        # Create a session factory
        self.Session = sessionmaker(bind=self.engine)

    @contextmanager
    def get_session(self):
        """Context manager for database sessions"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    # Example 1: Raw SQL query
    def execute_raw_query(self, query, params=None):
        with self.engine.connect() as connection:
            result = connection.execute(query, params or {})
            return result.fetchall()

    # Example 2: Query using pandas
    def query_to_dataframe(self, query):
        return pd.read_sql_query(query, self.engine)

    # Example 3: Execute with parameters
    def get_well_data(self, well_id):
        query = """
        SELECT *
        FROM Wells
        WHERE WellID = :well_id
        """
        return self.execute_raw_query(query, {'well_id': well_id})


class SQLConnector:
    def __init__(self, login_file="logininfo.txt"):
        self.login_file = login_file
        self.logger = logging.getLogger(__name__)
        self.engine = self._create_sql_connection()

    def _parse_credentials(self, content):
        """Parse username and password from file content."""
        try:
            lines = content.strip().split('\n')
            return {
                'user': lines[0].split('=')[1].strip(),
                'password': lines[1].split('=')[1].strip()
            }
        except (IndexError, KeyError) as e:
            self.logger.error(f"Error parsing credentials: {e}")
            return None

    def _get_credentials(self):
        """Read credentials from file."""
        try:
            file_path = os.path.join(os.getcwd(), self.login_file)
            with open(file_path, 'r') as file:
                content = file.read()
            return self._parse_credentials(content)
        except FileNotFoundError:
            self.logger.warning(f"Credentials file not found: {self.login_file}")
            return None

    @lru_cache(maxsize=1)
    def _create_connection_string(self):
        """Create connection string with caching."""
        # credentials = self._get_credentials()
        credentials = {}
        if credentials:
            # Production connection
            params = {
                'driver': '{SQL Server}',
                'server': 'oilgas-sql-prod.ogm.utah.gov',
                'database': 'UTRBDMSNET',
                'uid': credentials['user'],
                'pwd': credentials['password']
            }

            conn_str = (
                "DRIVER={driver};"
                "SERVER={server};"
                "DATABASE={database};"
                "UID={uid};"
                "PWD={pwd}"
            ).format(**params)
        else:
            # Fallback to local connection
            conn_str = (
                "Driver={SQL Server};"
                r"Server=CGDESKTOP\SQLEXPRESS;"
                "Database=UTRBDMSNET;"
                "Trusted_Connection=yes;"
            )
        return quote_plus(conn_str)

    def _create_sql_connection(self):
        """Create SQLAlchemy engine."""
        try:
            connection_string = self._create_connection_string()
            return create_engine(
                f"mssql+pyodbc:///?odbc_connect={connection_string}",
                pool_pre_ping=True,
                pool_recycle=3600
            )
        except Exception as e:
            self.logger.error(f"Failed to create SQL connection: {e}")
            raise

    def get_engine(self):
        """Return SQLAlchemy engine instance."""
        return self.engine


def _get_convergence(lat: float, lon: float, from_crs: str = 'EPSG:32043') -> float:
    """Calculate the meridian convergence angle for a given latitude/longitude coordinate.

    This function computes the meridian convergence (the angular difference between
    grid north and true north) at a specified location using the State Plane
    Coordinate System.

    Args:
        lat: Latitude coordinate in decimal degrees.
        lon: Longitude coordinate in decimal degrees.
        from_crs: EPSG code for the coordinate reference system. Defaults to
            'EPSG:32043' (Utah Central Zone State Plane).

    Returns:
        float: Meridian convergence angle in degrees.
            Positive values indicate convergence east of true north.
            Negative values indicate convergence west of true north.

    Examples:
        >>> _get_convergence(40.7608, -111.8910)  # Salt Lake City coordinates
        -0.324  # Example return value

    Notes:
        - The function uses the Utah Central Zone State Plane by default, which is
          appropriate for central Utah locations.
        - For locations outside Utah Central Zone, specify the appropriate EPSG code.
    """
    # Initialize the Coordinate Reference System using the specified EPSG code
    crs_spcs = CRS(from_crs)

    # Create a projection object for coordinate transformation and calculations
    p = Proj(crs_spcs)

    # Calculate meridian convergence using projection factors
    # Parameters: (longitude, latitude, radians=False, return_convergence=True)
    declination = p.get_factors(lon, lat, False, True).meridian_convergence
    return declination


def calculate_convergence_angle(latitude, longitude):
    """
    Calculate the convergence angle between grid north and true north for a given latitude and longitude.

    Parameters:
    - latitude (float): Latitude in decimal degrees.
    - longitude (float): Longitude in decimal degrees.

    Returns:
    - convergence_angle_deg (float): Convergence angle in degrees.
    """
    # Determine the UTM zone based on longitude
    utm_zone_number = int((longitude + 180) / 6) + 1

    # Determine if the location is in the northern or southern hemisphere
    hemisphere = 'north' if latitude >= 0 else 'south'

    # Create a CRS object for the appropriate UTM zone
    utm_crs = CRS.from_proj4(
        f"+proj=utm +zone={utm_zone_number} +{hemisphere} +ellps=WGS84 +datum=WGS84 +units=m +no_defs")

    # Retrieve the central meridian of the UTM zone
    # The central meridian for UTM zone N is (6 * N - 183) degrees
    central_meridian_deg = 6 * utm_zone_number - 183

    # Convert degrees to radians
    phi = math.radians(latitude)
    lambda_ = math.radians(longitude)
    lambda0 = math.radians(central_meridian_deg)

    # Calculate the convergence angle in radians
    convergence_rad = (lambda_ - lambda0) * math.sin(phi)

    # Convert radians to degrees
    convergence_deg = math.degrees(convergence_rad)

    return convergence_deg


# noinspection PyTestUnpassedFixture
class ETools(QMainWindow):
    def __init__(self, flag=True):
        super().__init__()
        self.writer = None
        self.survey_importer = None
        self.wcr_process = None
        self.drawer = None
        pd.set_option('display.max_columns', None)
        pd.options.mode.chained_assignment = None
        self.api_val = None
        self.apd_num = None
        self.well_name = None
        self.lateral = None
        self.file_path_planned = None
        self.file_path_drilled = None
        self.file_path_dict = {'planned': self.file_path_planned, 'drilled': self.file_path_drilled}
        self.well = None
        self.survey_type_lst = []
        self.db = DatabaseManager()

        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

        self.points_checker = PointChecker(ui=self.ui)
        # State 36 Rose, Dobby, Elkhorn
        # 4303950011
        # 4301354306
        # 4301950099
        #4304756908
        self.ui.well_api_val.setText('4301354722')
        self.button_group = QButtonGroup(self.ui.survey_type_widget)
        self.button_group.setExclusive(True)
        self.ui.well_api_val.returnPressed.connect(self.run_api_when_entered)
        self.ui.lateral_name_line_edit.returnPressed.connect(self.run_api_when_entered)
        self.ui.add_dx_data_pushbutton.pressed.connect(self.recalculate_data_with_new_md_input)
        self.ui.plat_searcher_combo_box.activated.connect(self.plat_searcher_combo_process)
        self.ui.locate_more_wells_push_button.pressed.connect(self.find_more_sections_and_report)
        self.ui.data_return_box.anchorClicked.connect(QDesktopServices.openUrl)
        self.ui.data_return_box.setOpenLinks(False)
        self.run_api_when_entered()


    def clear_checkboxes(self):
        """
        Clears all checkboxes from the layout.
        """
        while self.ui.surveys_draw_layout.count():
            item = self.ui.surveys_draw_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def clear_radio_buttons(self):
        """
        Clears all radio buttons from the layout and resets the button group.
        """
        while self.ui.surveys_layout.count():
            item = self.ui.surveys_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()  # Properly delete widget to free memory

        # Reset the button group to remove all previous references
        self.button_group = QButtonGroup(self.ui.survey_type_widget)
        self.button_group.setExclusive(True)

    #
    # def clear_radio_buttons(self):
    #     """
    #     Clears all radio buttons from the layout and the button group.
    #     """
    #     while self.ui.surveys_layout.count():
    #         item = self.ui.surveys_layout.takeAt(0)
    #         widget = item.widget()
    #         if widget is not None:
    #             widget.setParent(None)
    #     self.button_group = QButtonGroup(self.ui.survey_type_widget)
    #     self.button_group.setExclusive(True)

    def write_radio_buttons(self, df, surveys):
        def checkbox_creator():
            checkbox = QCheckBox(dict_translator[survey_label])
            checkbox.setObjectName(f"checkbox_survey_{survey_label}")
            self.ui.surveys_draw_layout.addWidget(checkbox)
            checkbox.setProperty('survey_name', survey_label)
            # survey_used = df[survey_label].clearance_data

            checkbox.stateChanged.connect(
                lambda state, lbl=survey_label: self.drawer.check_box_activate_path(state=state, lbl=lbl))

        """
        Creates and adds radio buttons to the surveys_layout based on the
        variables returned by get_survey_types().
        """
        # Clear existing buttons if any
        self.clear_radio_buttons()
        self.clear_checkboxes()
        dict_translator = {
            'drl_df_true_dx': "AsDrilled - True",
            'drl_df_grid_dx': "AsDrilled - Grid",
            'pln_df_true_dx': "Planned - True",
            'pln_df_grid_dx': "Planned - Grid"}
        # Retrieve variables (survey types)
        variables = [i for i, _ in df.items()]
        # Iterate and create radio buttons
        for idx, survey_label in enumerate(variables):
            checkbox_creator()
            radio_button = QRadioButton(dict_translator[survey_label])
            radio_button.setObjectName(f"radio_survey_{idx}")
            self.ui.surveys_layout.addWidget(radio_button)
            self.button_group.addButton(radio_button, id=idx)

            # Use partial to ensure survey_label is captured correctly
            radio_button.clicked.connect(partial(self.writer.survey_writer, self.ui, survey_label))

        # Optionally, select the first radio button by default
        if variables:
            self.button_group.button(0).setChecked(True)

    def bad_api_popup(self):
        choice = QMessageBox.warning(self, "Attention", "Invalid API Detected! Fix it! (Possibly a string?)",
                                     QMessageBox.Ok)

    def no_dx_popup(self):
        choice = QMessageBox.warning(self, "Attention", "No directional survey detected in database!",
                                     QMessageBox.Ok)
    def retrieve_well_parameters(self):
        query = f"""SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = '{self.api_val}{self.lateral}'"""
        # output = self.db.f(query)
        self.apd_num = self.db.query_to_dataframe(query)['APDNo'].unique()[0]
        print(self.apd_num)

        self.well_name = self.db.query_to_dataframe(query)['Well_Nm'].unique()[0]

    def sql_query_survey(self, db_process, api, lateral):
        # path = r'C:\Work\Databases'
        # apd_data_dir_loc = os.path.join(path, "location_data.db")
        # conn_db_loc = sqlite3.connect(apd_data_dir_loc)
        # # # apd_data_dir_sec = os.path.join(path, 'Board_DB_Plss_Sections.db')
        # # # conn_db = sqlite3.connect(apd_data_dir_sec)
        # # #
        # # # query = "Select * from BaseData"
        # # # df = pd.read_sql(query, conn_db)
        # # # df.to_sql('section_coords', conn_db_loc, if_exists='append', index=False)
        # # # conn_db_loc.commit()
        # # #
        # csv_path = os.path.join(path, r"PlatGridNumbers.csv")
        # df2 = pd.read_csv(csv_path, encoding="ISO-8859-1")
        # df2['Conc'] = df2['Conc'].apply(lambda row: row[:9])

        # df2.to_sql('section_relative', conn_db_loc, if_exists='append', index=False)
        # #
        # #
        # #
        # # query = f"""SELECT *
        # #         FROM section_coords"""
        # # output = pd.read_sql(query, conn_db_loc)
        # #
        # conn_db_loc.commit()
        # conn_db_loc.close()
        # conn_db.close()
        query = f"""SELECT MeasuredDepth as measured_depth, Inclination as inclination, Azimuth as azimuth, 
        CitingType, dsh.SurveySurfaceElevation, dsh.SurfaceLatitude, dsh.SurfaceLongitude,dsh.NorthReference, dsh.LateralName
                FROM DirectionalSurveyHeader dsh
                JOIN DirectionalSurveyData dsd on dsd.DirectionalSurveyHeaderKey = dsh.Pkey
                WHERE dsh.APINumber = '{api}' and dsh.LateralName = '{lateral}' order by MeasuredDepth"""
        survey_dx = db_process.query_to_dataframe(query)
        try:
            well_elevation = survey_dx['SurveySurfaceElevation'].iloc[0]
            north_ref = survey_dx['NorthReference'].iloc[0][0].lower()
            survey_dx = survey_dx.drop(['SurveySurfaceElevation', 'NorthReference'], axis=1)
            survey_dx = survey_dx.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
            survey_dx = survey_dx.sort_values(by=['CitingType', 'measured_depth'])
            survey_dx['CitingType'] = survey_dx['CitingType'].str.lower().replace(
                {'asdrilled': 'AsDrilled', 'planned': 'Planned'})
            return survey_dx, well_elevation, north_ref
        except IndexError:
            self.no_dx_popup()
            sys.exit(app.exec_())



    def run_api_when_entered(self):
        print('run api')
        self.file_path_planned = None
        self.file_path_drilled = None
        self.file_path_dict = {'planned': self.file_path_planned, 'drilled': self.file_path_drilled}

        api_val = self.ui.well_api_val.text()
        lateral_name = self.ui.lateral_name_line_edit.text()
        if lateral_name == '':
            lateral_name = '0000'
            self.ui.lateral_name_line_edit.setText('0000')
        if len(api_val) > 10:
            self.bad_api_popup()
            return
        try:
            int(float(api_val))
        except ValueError:
            self.bad_api_popup()
            return
        # try:

        self.api_val = api_val
        self.lateral = lateral_name
        print('api', api_val, lateral_name)

        self.retrieve_well_parameters()
        survey_dx, well_elevation, north_ref = self.sql_query_survey(self.db, self.api_val, self.lateral)
        self.well = EToolsWell(db=self.db, api=self.api_val, apd_num=self.apd_num, well_name=self.well_name,
                               lateral=self.lateral, survey_dx=survey_dx, well_elevation=well_elevation,
                               north_ref=north_ref, ui=self.ui)
        self.find_more_sections_combo_box()
        self.main_processes_program(north_ref)
        self.writer = DataWriter(ui=self.ui,
                                 surveys=self.well.cl_dx_dict,
                                 spec_surveys=self.well.spec_surveys_dict,
                                 parameters=self.well.survey_parameters,
                                 plat_df=self.well.plat_df)
        self.write_radio_buttons(self.well.cl_dx_dict, self.well.spec_surveys_dict)
        self.ui.load_as_drilled_survey_box.clicked.connect(lambda: self.press_new_survey_button('drilled'))
        self.ui.load_planned_survey_box.clicked.connect(lambda: self.press_new_survey_button('planned'))
        self.ui.calc_new_dx_with_new_shl_pushbutton.clicked.connect(self.process_with_new_shl)

        # self.clear_survey_page()

    def clear_survey_page(self):
        # self.dx_survey_model.setRowCount(0)  # Clear existing rows efficiently
        self.ui.dx_survey_table_mod.setModel(self.dx_survey_model)
        self.ui.dx_survey_table_mod.setUpdatesEnabled(False)
        self.ui.dx_survey_location_tableview.setUpdatesEnabled(False)
        # self.dx_survey_model_footages.setRowCount(0)  # Clear existing rows efficiently
        self.ui.dx_survey_location_tableview.setModel(self.dx_survey_model_footages)

    def main_processes_program(self, north_ref):
        self.ui.well_name.setText(self.well.well_name)
        self.survey_importer = SurveyImporter(self.well.well_name)
        self.drawer = DataDrawer(ui=self.ui, df_survey=self.well.cl_dx_dict)
        self.drawer.draw_2d_data(df_plat=self.well.plat_df, df_survey=self.well.cl_dx_dict)
        self.drawer.draw_3d_process(df=self.well.cl_dx_dict)
        self.wcr_process = WCR_Main(df=self.well.cl_dx_dict, ui=self.ui, db=self.db, loc_df=self.well.loc_df,
                                    spec_surveys=self.well.spec_surveys_dict, north_ref=north_ref)
        self.wcr_process.process_wcr()
        self.ui.add_pt_viz_button.pressed.connect(self.drawer.insert_user_generated_point)

        self.ui.border_100.stateChanged.connect(lambda state: self.drawer.change_visibility_100(state=state))
        self.ui.border_330.stateChanged.connect(lambda state: self.drawer.change_visibility_330(state=state))

    def determine_coord_system(self, x, y):
        # Check if the point falls within typical lat/lon ranges.
        if -180 <= y <= 180 and -90 <= x <= 90:
            return [x, y]

        # Check if the point falls within typical UTM ranges.
        if 166000 <= x <= 834000 and 0 <= y <= 10000000:
            return utm.to_latlon(x, y, 12, 'T')

    # def alter_shl_data(self):
    #     new_shl = [float(self.ui.shl_lat_easting.text()), float(self.ui.shl_lon_northing.text())]
    #     pass
    def recalculate_data_with_new_md_input(self):
        def return_well_survey():
            dict_return = {'AsDrilled - True': self.well.cl_dx_dict['drl_df_true_dx'].clearance_data,
                           'AsDrilled - Grid': self.well.cl_dx_dict['drl_df_grid_dx'].clearance_data,
                           'Planned - True': self.well.cl_dx_dict['pln_df_true_dx'].clearance_data,
                           'Planned - Grid': self.well.cl_dx_dict['pln_df_grid_dx'].clearance_data}
            checked_button = self.button_group.checkedButton()
            checked_button_text = checked_button.text()
            for k, v in dict_return.items():
                if k.lower() in checked_button_text.lower():
                    return dict_return[k]



        def filter_by_citing_type():
            lst_data = [survey]
            for citing, group in survey.groupby('CitingType'):
                lower_row = group[group['measured_depth'].astype(float) < md].iloc[-1]
                upper_row = group[group['measured_depth'].astype(float) > md].iloc[0]
                new_row = {'measured_depth': md}
                new_row['inclination'] = np.interp(md,
                                                   [float(lower_row['measured_depth']),
                                                    float(upper_row['measured_depth'])],
                                                   [float(lower_row['inclination']), float(upper_row['inclination'])])
                new_row['azimuth'] = np.interp(md,
                                               [float(lower_row['measured_depth']), float(upper_row['measured_depth'])],
                                               [float(lower_row['azimuth']), float(upper_row['azimuth'])])
                new_row['CitingType'] = lower_row['CitingType']
                new_row['SurfaceLatitude'] = lower_row['SurfaceLatitude']
                new_row['SurfaceLongitude'] = lower_row['SurfaceLongitude']
                new_row['LateralName'] = lower_row['LateralName']
                lst_data.append(pd.DataFrame([new_row]))
            return lst_data

        md = float(self.ui.new_md_survey_box.text())

        # survey = get_citing_type()
        # row = interpolate_row(df=survey, new_md=md)
        survey = self.well.get_survey()
        output = filter_by_citing_type()
        survey = pd.concat(output, ignore_index=True)
        survey = survey.sort_values(by=['CitingType', 'measured_depth'])
        self.well.set_survey(survey)
        self.well.reprocess_with_current_plat()
        self.main_processes_program(self.ui.dx_survey_north_ref_line.text())
        self.writer.set_clear_survey(self.well.cl_dx_dict)
        self.writer.set_spec_surveys(self.well.spec_surveys_dict)

        self.writer.write_new_survey_line_to_display(return_well_survey(), md)
        first_button = self.button_group.button(self.button_group.checkedId())
        first_button.setChecked(True)
        first_button.clicked.emit()

    def process_with_new_shl(self):
        print('new shl')
        x, y = float(self.ui.shl_lat_easting.text()), float(self.ui.shl_lon_northing.text())
        pt = self.determine_coord_system(float(self.ui.shl_lat_easting.text()), float(self.ui.shl_lon_northing.text()))
        self.well.set_starting_point(pt)
        self.well.etools_process()
        self.main_processes_program(self.ui.dx_survey_north_ref_line.text())
        self.writer.set_clear_survey(self.well.cl_dx_dict)
        self.writer.set_spec_surveys(self.well.spec_surveys_dict)

        # self.writer.write_new_survey_line_to_display(return_well_survey(), md)
    def press_new_survey_button(self, label):
        self.ui.load_as_drilled_survey_box.blockSignals(True)
        self.ui.load_planned_survey_box.blockSignals(True)

        def loader():
            filter = "pdf(*.pdf)"
            current_dir = os.getcwd()
            file_path = QFileDialog.getOpenFileName(None, 'Open file', current_dir, filter)
            print('Loading: ', file_path)
            while '.pdf' not in file_path[0] and file_path != ('', ''):
                file_path = QFileDialog.getOpenFileName(None, 'Open file', current_dir, filter)
            self.file_path_dict[label] = file_path[0]

        def filter_out_same_citing():
            new_label = 'Planned' if label == 'planned' else 'AsDrilled'
            current_df = self.well.survey_dx
            current_df = current_df[current_df['CitingType'] != new_label]
            current_df = current_df.sort_values(by=['measured_depth'])

            new_df = pd.concat([current_df, df]).reset_index(drop=True)
            return new_df

        loader()
        df, north_ref, extra_plats = self.survey_importer.load_and_process_data(label, self.db, self.api_val,
                                                                                self.file_path_dict)
        well_elevation = df['SurveySurfaceElevation'].iloc[0]
        df = df.sort_values(by=['measured_depth'])
        df = df.drop(['SurveySurfaceElevation'], axis=1)
        df['LateralName'] = self.lateral
        output_new_df = filter_out_same_citing()
        test_combo = pd.concat([self.well.plat_df, extra_plats]).drop_duplicates()
        self.well.set_survey(output_new_df)
        self.well.set_north_ref(north_ref)
        self.well.set_well_elevation(well_elevation)
        self.well.set_plat_data(test_combo)
        # self.well.reprocess_with_current_plat()
        self.well.etools_process(preserve_plat=True)
        self.writer.set_clear_survey(self.well.cl_dx_dict)
        self.writer.set_spec_surveys(self.well.spec_surveys_dict)
        self.main_processes_program(north_ref)
        self.write_radio_buttons(self.well.cl_dx_dict, self.well.spec_surveys_dict)
        self.ui.load_as_drilled_survey_box.blockSignals(False)
        self.ui.load_planned_survey_box.blockSignals(False)
        print('ended')

    def find_more_sections_and_report(self):
        def sql_find_section_data():
            query = f"""select a.APDNo, a.API_WellNo
                    from [dbo].[tblAPDLoc] loc
                    inner join [dbo].[tblAPD] a on a.APDNo = loc.APDNO
                    where Wh_Sec = '{section}' and Wh_Twpn = '{ts}' and Wh_Twpd = '{ts_dir}' 
                    and Wh_RngN =' {rng}' and Wh_RngD = '{rng_dir}' and Wh_Pm = '{baseline}'"""
            output = self.db.query_to_dataframe(query)

            return output.drop_duplicates(keep="first")

        section, ts, ts_dir, rng, rng_dir, baseline = self.ui.searcher_section.text(), self.ui.searcher_township.text(), self.ui.searcher_township_dir.text(), self.ui.searcher_range.text(), self.ui.searcher_range_dir.text(), self.ui.searcher_baseline.text()

        township_rng_section = f"""{section} {ts}{ts_dir} {rng}{rng_dir} {baseline}"""

        line = sql_find_section_data()

        self.ui.data_return_box.append("_______________________________________________________")
        self.ui.data_return_box.append(f"<b><u>{township_rng_section}<u><b>")
        for idx, row in line.iterrows():
            permit_number = row['APDNo']
            well_name = row['API_WellNo']
            full_url = f"https://oilgasweb.ogm.utah.gov/apd/attachments/{permit_number}/{permit_number}_wellplat.pdf"
            # Create HTML content with proper formatting
            html_content = f"""
                <div style="margin-bottom: 10px;">
                    {well_name}<br>
                    <a href="{full_url}">{full_url}</a>
                </div>
            """
            # Use insertHtml instead of append
            self.ui.data_return_box.insertHtml(html_content)
        self.ui.data_return_box.append("_______________________________________________________")

    def find_more_sections_combo_box(self):
        self.ui.plat_searcher_combo_box.clear()
        for idx, row in self.well.plat_df.iterrows():
            self.ui.plat_searcher_combo_box.addItem(row['label'])

    def plat_searcher_combo_process(self):
        current_label = self.ui.plat_searcher_combo_box.currentText()
        conc = self.well.plat_df[self.well.plat_df['label'] == current_label]['Conc'].iloc[0]
        self.ui.searcher_section.setText(str(int(float(conc[:2].strip()))))
        self.ui.searcher_township.setText(str(int(float(conc[2:4].strip()))))
        self.ui.searcher_township_dir.setText(conc[4].strip())
        self.ui.searcher_range.setText(str(int(float(conc[5:7].strip()))))
        self.ui.searcher_range_dir.setText(conc[7].strip())
        self.ui.searcher_baseline.setText(conc[-1].strip())


class EToolsWell:
    def __init__(self, db, api, apd_num, well_name, lateral, survey_dx, well_elevation, north_ref, ui):
        super().__init__()
        self.db = db
        self.ui = ui
        self.api = api
        self.apd_num = apd_num
        self.well_name = well_name
        self.lateral = lateral
        self.survey_dx = survey_dx
        first_pt = survey_dx.head(1)
        self.starting_point = [first_pt['SurfaceLatitude'].iloc[0], first_pt['SurfaceLongitude'].iloc[0]]
        self.well_elevation = well_elevation
        self.north_ref = north_ref
        self.surveys_dict, self.spec_surveys_dict, self.survey_parameters = None, None, None
        self.plat_df, self.loc_df, self.cl_dx_dict = None, None, None
        self.set_plat_data(None)
        self.etools_process()
        # self.ui.shl_lat_easting.setText()
        # self.ui.shl_lon_northing.setText()

    def set_plat_data(self, plat_data):
        self.plat_df = plat_data

    def get_plat_data(self):
        return self.plat_df

    def set_survey(self, survey):
        self.survey_dx = survey

    def get_survey(self):
        return self.survey_dx

    def set_north_ref(self, north_ref):
        self.north_ref = north_ref

    def set_well_elevation(self, well_elevation):
        self.well_elevation = well_elevation

    def set_starting_point(self, starting_point):
        self.survey_dx['SurfaceLatitude'] = starting_point[0]
        self.survey_dx['SurfaceLongitude'] = starting_point[1]

        # self.starting_point = starting_point

    # def etools_process(self):
    # self.survey_dx['measured_depth'] = self.survey_dx['measured_depth'].astype(float)
    # self.survey_dx['inclination'] = self.survey_dx['inclination'].astype(float)
    # self.survey_dx['azimuth'] = self.survey_dx['azimuth'].astype(float)
    # self.survey_dx['SurfaceLatitude'] = self.survey_dx['SurfaceLatitude'].astype(float)
    # self.survey_dx['SurfaceLongitude'] = self.survey_dx['SurfaceLongitude'].astype(float)
    # self.sqlRetrieveWellInfo()
    # self.surveys_dict, self.spec_surveys_dict, self.survey_parameters = self.retrieve_survey_data(self.survey_dx, self.well_elevation, self.north_ref)
    # self.plat_df, self.loc_df = self.retrieve_location_data(self.surveys_dict)
    # self.cl_dx_dict = self.retrieve_clearance_data(self.surveys_dict, self.plat_df)

    def etools_process(self, preserve_plat=False):
        self.survey_dx['measured_depth'] = self.survey_dx['measured_depth'].astype(float)
        self.survey_dx['inclination'] = self.survey_dx['inclination'].astype(float)
        self.survey_dx['azimuth'] = self.survey_dx['azimuth'].astype(float)
        self.survey_dx['SurfaceLatitude'] = self.survey_dx['SurfaceLatitude'].astype(float)
        self.survey_dx['SurfaceLongitude'] = self.survey_dx['SurfaceLongitude'].astype(float)
        # self.survey_dx['SurfaceLatitude'] = 39.909024
        # self.survey_dx['SurfaceLongitude'] = -109.204048
        # self.sqlRetrieveWellInfo()

        self.surveys_dict, self.spec_surveys_dict, self.survey_parameters = self.retrieve_survey_data(self.survey_dx,
                                                                                                      self.well_elevation,
                                                                                                      self.north_ref)
        if not preserve_plat:
            plat_df_new, loc_df_new = self.retrieve_location_data(self.surveys_dict)
            self.plat_df = pd.concat([self.plat_df, plat_df_new]).drop_duplicates()
            self.loc_df = pd.concat([self.loc_df, loc_df_new]).drop_duplicates()
        self.cl_dx_dict = self.retrieve_clearance_data(self.surveys_dict, self.plat_df)

    def reprocess_with_current_plat(self):
        self.etools_process(preserve_plat=True)

    def retrieve_survey_data(self, survey_dx, well_elevation, north_ref):
        surveys_dict = SurveyProcessBase(self.api, self.lateral, self.db, survey_dx, well_elevation, north_ref)
        return surveys_dict.dx_dict, surveys_dict.dx_dict_spec_depths, surveys_dict.survey_parameters

    def retrieve_location_data(self, survey_dict):
        plat_output = TownShipAndRangeProcess(self.api, self.lateral, self.db, survey_dict)
        return plat_output.plat_df, plat_output.loc_df

    def retrieve_clearance_data(self, survey_dict, plat_df):
        try:
            test = survey_dict['drl_df'].true_dx.values.tolist()
        except KeyError:
            pass
        clearance_dx_df_dict = {}
        for i, v in survey_dict.items():
            for j in ['true_dx', 'grid_dx']:
                ref_label = f"{i}_{j}"
                clearance_dx_df_dict[ref_label] = self.clearance_process(getattr(survey_dict[i], j), plat_df)
        return clearance_dx_df_dict

    def clearance_process(self, df, plat_df):
        return ClearanceProcess(df, plat_df)

    # def sqlRetrieveWellInfo(self):
    #     def update_xy(row):
    #         if row['LocType'] == 'SURF':
    #             return pd.Series({'X': output['Wh_X'].iloc[0], 'Y': output['Wh_Y'].iloc[0]})
    #         elif row['LocType'] == 'BH':
    #             return pd.Series({'X': output['Bh_X'].iloc[0], 'Y': output['Bh_Y'].iloc[0]})
    #         else:
    #             return pd.Series({'X': row['X'], 'Y': row['Y']})
    #
    #     def is_valid_number(x):
    #         return pd.notnull(x) and np.isreal(x) and x > 400000
    #
    #     def findBHLSHLIfErrored():
    #         query = f"""select Wh_X, Wh_Y, Bh_X, Bh_Y
    #             from [dbo].[tblAPDLoc]
    #             where APDNO = {self.apdNo} and Zone_Name = 'Proposed Depth'"""
    #         output = pd.read_sql_query(query, self.engine)
    #         return output
    #
    #     query = f"""
    #       SELECT
    #           County, l.X, l.Y, NorthReference, CitingType, LocType,
    #           Sec, Township, TownshipDir, Range, RangeDir, PM, OperatorName
    #       FROM Well w
    #       LEFT JOIN Construct c ON c.WellKey = w.PKey
    #       LEFT JOIN loc l ON l.ConstructKey = c.pkey
    #       LEFT JOIN LocExt le ON le.lockey = l.Pkey
    #       LEFT JOIN DirectionalSurveyHeader dsh ON dsh.APINumber = w.WellID
    #       WHERE WellID = {self.api}
    #       AND LocType IN ('BH', 'SURF')
    #       AND CitingType IN ('Planned', 'planned', 'PLANNED')
    #       ORDER BY CitingType
    #       """
    #
    #     def strip_if_string(value):
    #         return value.strip() if isinstance(value, str) else value
    #
    #     # output = self.db.query_to_dataframe(query).applymap(strip_if_string)
    #     output = self.db.query_to_dataframe(query).map(strip_if_string)
    #     invalid_x = output[~output['X'].apply(is_valid_number)]
    #     invalid_y = output[~output['Y'].apply(is_valid_number)]
    #     invalid_rows = pd.concat([invalid_x, invalid_y]).drop_duplicates()
    #     if not invalid_rows.empty:
    #         output = findBHLSHLIfErrored()
    #         output[['X', 'Y']] = output.apply(update_xy, axis=1)
    #         output = output[output['X'].apply(is_valid_number) & output['Y'].apply(is_valid_number)]
    #
    #     output['Lat'], output['Lon'] = zip(
    #         *output.apply(lambda row: utm.to_latlon(row['X'], row['Y'], 12, 'T'), axis=1))
    #     output['CitingType'] = output['CitingType'].apply(lambda x: x.lower())
    #     output['CitingType'] = output['CitingType'].replace('asdrilled', 'AsDrilled')
    #     output['CitingType'] = output['CitingType'].replace('planned', 'Planned')
    #     county = output['County'].unique()[0].tolist()
    #     sp_zone = ma.findSPZone(ma.countyDict(county))
    #     lat, lon = output['Lat'].iloc[0], output['Lon'].iloc[0]


# noinspection PyTestUnpassedFixture
class PointChecker:
    def __init__(self, ui):
        self.ui = ui

        self.ui.a_check_pt_e.setText('558421.8536512152')
        self.ui.a_check_pt_n.setText('4442048.529338275')
        self.ui.b_check_pt_e.setText('558448.0426760855')
        self.ui.b_check_pt_n.setText('4441231.027283544')
        self.ui.check_pt_e.setText('558473')
        self.ui.check_pt_n.setText('4441472')

        self.ui.lat_deg_a.editingFinished.connect(self.collect_data)
        self.ui.lat_min_a.editingFinished.connect(self.collect_data)
        self.ui.lat_sec_a.editingFinished.connect(self.collect_data)
        self.ui.lon_deg_a.editingFinished.connect(self.collect_data)
        self.ui.lon_min_a.editingFinished.connect(self.collect_data)
        self.ui.lon_sec_a.editingFinished.connect(self.collect_data)
        self.ui.lat_deg_b.editingFinished.connect(self.collect_data)
        self.ui.lat_min_b.editingFinished.connect(self.collect_data)
        self.ui.lat_sec_b.editingFinished.connect(self.collect_data)
        self.ui.lon_deg_b.editingFinished.connect(self.collect_data)
        self.ui.lon_min_b.editingFinished.connect(self.collect_data)
        self.ui.lon_sec_b.editingFinished.connect(self.collect_data)
        self.ui.a_check_pt_e.editingFinished.connect(self.collect_data)
        self.ui.a_check_pt_n.editingFinished.connect(self.collect_data)
        self.ui.b_check_pt_e.editingFinished.connect(self.collect_data)
        self.ui.b_check_pt_n.editingFinished.connect(self.collect_data)

        self.figure_check, self.ax_check = plt.subplots()
        self.canvas_check = FigureCanvas(self.figure_check)  # Create Qt-compatible canvas
        self.ui.check_pt_graphic_display.addWidget(self.canvas_check)
        self.check_pts = self.ax_check.scatter([], [],
                                                 marker='o',
                                                 color='black',  # filled black circle
                                                 s=25,
                                                 zorder=1000)
        self.check_seg_plot, = self.ax_check.plot(
            [], [], color='red', linewidth=1, zorder=5)
        self.segment = None
        self.check_pt = None
        

        pass
    def set_segment(self, segment):
        self.segment = segment

    def set_check_pt(self, check_pt):
        self.check_pt = check_pt
    # def gather_deg_pts(self):
    #     def converter(label, id):
    #         deg = abs(float(getattr(self.ui, f"{label}_deg_{id}").text()))
    #         min = float(getattr(self.ui, f"{label}_min_{id}").text())
    #         sec = float(getattr(self.ui, f"{label}_sec_{id}").text())
    #         dec_val_base = deg + min / 60 + sec / 3600
    #         return dec_val_base
    #
    #     lat_dec_a = converter('lat', 'a')
    #     lon_dec_a = abs(converter('lon', 'a')) * -1
    #
    #     lat_dec_b = converter('lat', 'b')
    #     lon_dec_b = abs(converter('lon', 'b')) * -1
    #
    #     output_a = utm.from_latlon(lat_dec_a, lon_dec_a)[:2]
    #     output_b = utm.from_latlon(lat_dec_b, lon_dec_b)[:2]
    #
    #     return output_a, output_b

    def gather_deg_pts(self):
        def converter(label, id):
            deg_text = getattr(self.ui, f"{label}_deg_{id}").text().strip()
            min_text = getattr(self.ui, f"{label}_min_{id}").text().strip()
            sec_text = getattr(self.ui, f"{label}_sec_{id}").text().strip()

            # If any field is empty, raise an error
            if not (deg_text and min_text and sec_text):
                raise ValueError(f"Empty field in {label}_{id} inputs")

            deg = abs(float(deg_text))
            minutes = float(min_text)
            sec = float(sec_text)
            return deg + minutes / 60 + sec / 3600

        lat_dec_a = converter('lat', 'a')
        lon_dec_a = -abs(converter('lon', 'a'))
        lat_dec_b = converter('lat', 'b')
        lon_dec_b = -abs(converter('lon', 'b'))

        output_a = utm.from_latlon(lat_dec_a, lon_dec_a)[:2]
        output_b = utm.from_latlon(lat_dec_b, lon_dec_b)[:2]

        return output_a, output_b

    def gather_pts(self):
        fields = [
            self.ui.a_check_pt_e.text(),
            self.ui.a_check_pt_n.text(),
            self.ui.b_check_pt_e.text(),
            self.ui.b_check_pt_n.text()
        ]

        # If any field is empty, use gather_deg_pts()
        if any(not field.strip() for field in fields):
            try:
                return self.gather_deg_pts()
            except ValueError:
                pass

        # Otherwise, proceed with conversion and UTM/latlon check
        try:
            e_dec_1 = float(self.ui.a_check_pt_e.text())
            n_dec_1 = float(self.ui.a_check_pt_n.text())
            e_dec_2 = float(self.ui.b_check_pt_e.text())
            n_dec_2 = float(self.ui.b_check_pt_n.text())
            output_a = self.check_if_utm_or_latlon(e_dec_1, n_dec_1)
            output_b = self.check_if_utm_or_latlon(e_dec_2, n_dec_2)
            return output_a, output_b
        except ValueError:
            # Handle unexpected conversion errors if needed
            try:
                return self.gather_deg_pts()
            except ValueError:
                pass



        #
        # try:
        #     e_dec_1, n_dec_1 = [float(self.ui.a_check_pt_e.text()), float(self.ui.a_check_pt_n.text())]
        #     e_dec_2, n_dec_2 = [float(self.ui.b_check_pt_e.text()), float(self.ui.b_check_pt_n.text())]
        #     output_a = self.check_if_utm_or_latlon(e_dec_1, n_dec_1)
        #     output_b = self.check_if_utm_or_latlon(e_dec_2, n_dec_2)
        #     return output_a, output_b
        #
        # except ValueError:
        #     try:
        #         output_a, output_b = self.gather_deg_pts()
        #         return output_a, output_b
        #     except ValueError:
        #         pass
        #     pass


    def check_if_utm_or_latlon(self, x_coord, y_coord):
        try:
            x = float(x_coord)
            y = float(y_coord)
            if (-180 <= x <= 180) and (-90 <= y <= 90):
                if (-114 <= x <= -109) and (37 <= y <= 42):
                    y = abs(y) * -1
                    return utm.from_latlon(x, y)[:2]
            if (140000 <= x <= 800000) and (3800000 <= y <= 4800000):
                return (x, y)

            return 'invalid'

        except ValueError:
            return 'invalid'

    def collect_data(self):
        try:
            pt_a, pt_b = self.gather_pts()
        except TypeError:
            pass
        try:

            pt_used = (float(self.ui.check_pt_e.text()), float(self.ui.check_pt_n.text()))
            line = LineString([pt_a, pt_b])
            point = Point(pt_used)

            # Compute the distance in meters
            distance = point.distance(line)
            self.ui.check_pt_result_box.setText(f"{round(distance / 0.3048, 3)} ft")
            self.draw_graphic_for_checked_pts([pt_a, pt_b], pt_used)
        except ValueError:
            pass

    def draw_graphic_for_checked_pts(self, segment_pts, check_pt):
        all_pts = segment_pts + [check_pt]
        x, y = LineString(segment_pts).xy

        self.check_seg_plot.set_data(x, y)
        self.check_pts.set_offsets(all_pts)
        self.ax_check.relim()
        self.ax_check.axis('equal')
        self.ax_check.autoscale_view()

        self.canvas_check.draw()


class ZoomPan:
    def __init__(self):
        self.press = None
        self.cur_xlim = None
        self.cur_ylim = None
        self.x0 = None
        self.y0 = None
        self.x1 = None
        self.y1 = None
        self.xpress = None
        self.ypress = None
        self.text_objects = []  # Store text annotations

    def zoom_factory(self, ax, base_scale):
        def zoom(event):
            if event.inaxes != ax: return
            cur_xlim = ax.get_xlim()
            cur_ylim = ax.get_ylim()

            xdata = event.xdata  # get event x location
            ydata = event.ydata  # get event y location

            if event.button == 'down':
                # deal with zoom in
                scale_factor = 1 / base_scale
            elif event.button == 'up':
                # deal with zoom out
                scale_factor = base_scale
            else:
                # deal with something that should never happen
                scale_factor = 1

            new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
            new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor

            relx = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
            rely = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])

            ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * (relx)])
            ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * (rely)])

            # Update the font size of text annotations based on the new zoom level
            scale_factor = ax.get_xlim()[1] - ax.get_xlim()[0]
            for text in self.text_objects:
                new_fontsize = 12 / scale_factor * 2500  # Adjust the 10 as needed for desired scale
                text.set_fontsize(new_fontsize)
            ax.figure.canvas.draw()

        fig = ax.get_figure()  # get the figure of interest
        fig.canvas.mpl_connect('scroll_event', zoom)
        return zoom

    def add_text(self, ax, x, y, text_str):
        scale_factor = ax.get_xlim()[1] - ax.get_xlim()[0]
        text = ax.text(x, y, text_str, ha='center', va='center', fontsize=12 / scale_factor * 2500,
                       transform=ax.transData)
        self.text_objects.append(text)

    def pan_factory(self, ax):
        def onPress(event):
            if event.inaxes != ax: return
            self.cur_xlim = ax.get_xlim()
            self.cur_ylim = ax.get_ylim()
            self.press = self.x0, self.y0, event.xdata, event.ydata
            self.x0, self.y0, self.xpress, self.ypress = self.press

        def onRelease(event):
            self.press = None
            ax.figure.canvas.draw()

        def onMotion(event):
            if self.press is None: return
            if event.inaxes != ax: return
            dx = event.xdata - self.xpress
            dy = event.ydata - self.ypress
            self.cur_xlim -= dx
            self.cur_ylim -= dy
            ax.set_xlim(self.cur_xlim)
            ax.set_ylim(self.cur_ylim)

            ax.figure.canvas.draw()

        fig = ax.get_figure()  # get the figure of interest

        # attach the call back
        fig.canvas.mpl_connect('button_press_event', onPress)
        fig.canvas.mpl_connect('button_release_event', onRelease)
        fig.canvas.mpl_connect('motion_notify_event', onMotion)

        # return the function
        return onMotion


def except_hook(cls, exception, traceback):
    sys.__excepthook__(cls, exception, traceback)


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    # w = EngineeringTools()
    w = ETools()
    w.show()
    sys.excepthook = except_hook
    sys.exit(app.exec_())
