import sqlite3

import PyQt5
import pandas as pd
import geopandas as gpd
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

class PlatCoordEditor:
    def __init__(self, section_df, ui):
        self.section_df = section_df
        self.ui = ui
        self.db = self.setup_sqlite_db()
        self.dict_utm = dict.fromkeys(range(1, 9))
        self.dict_latlon = dict.fromkeys(range(1, 9))
        self.button_groups = {}
        self.dict_plats = {}
        self.dict_figures = {}
        self.dict_canvas = {}
        self.dict_ax = {}
        self.zp = ZoomPan()
        self._program_changes = True  # Flag for programmatic changes
        # self._initializing = True  # Flag to track initialization state
        # self.added_viz_pts_model = QStandardItemModel()
        # self.ui.insert_pts_lst.setModel(self.added_viz_pts_model)
        # self.added_viz_pts_model.dataChanged.connect(self.update_model_table_when_user_modifies_values)
        # self.ui.insert_pts_lst.setEditTriggers(QAbstractItemView.AllEditTriggers)

        for i in range(8):
            setattr(self, f"plat_table_model_coords_{i + 1}", QStandardItemModel())
            model = getattr(self, f"plat_table_model_coords_{i + 1}")
            ui_element = getattr(self.ui, f"table_coords_{i + 1}")
            ui_viz = getattr(self.ui, f"well_graphic_coords_{i + 1}")
            ui_element.blockSignals(True)
            ui_element.setModel(model)
            self.setup_radio_buttons(i)
            grp = getattr(self.ui, f'bg_coords_{i + 1}')
            grp.buttonClicked[int].connect(partial(self.toggle_radio_button, group_index=i + 1))

            # Add selection mode and ability to edit
            ui_element.setSelectionMode(QAbstractItemView.ExtendedSelection)
            ui_element.setSelectionBehavior(QAbstractItemView.SelectRows)
            ui_element.setEditTriggers(QAbstractItemView.AllEditTriggers)

            # Connect data change signal
            model.dataChanged.connect(partial(self.alter_coords_tables, i + 1))

            # Setup delete key event
            # ui_element.keyPressEvent = partial(self.handle_key_press, table_index=i + 1)

            self.dict_figures[i + 1] = plt.figure()
            self.dict_canvas[i + 1] = FigureCanvas(self.dict_figures[i + 1])
            self.dict_ax[i + 1] = self.dict_figures[i + 1].subplots()
            ui_viz.addWidget(self.dict_canvas[i + 1])
            line_collection_template, = self.dict_ax[i + 1].plot([], [], color='black', linewidth=1, zorder=5)
            self.dict_plats[i + 1] = line_collection_template
            self.dict_ax[i + 1].axis('equal')
            self.zoom_fac = self.zp.zoom_factory(self.dict_ax[i + 1], 1.1)
            figPan = self.zp.pan_factory(self.dict_ax[i + 1])
            table_wid = getattr(self.ui, f"plat_table_coords_{i + 1}")

            table_wid.cellChanged.connect(partial(self.find_new_data, i + 1))
            table_wid.setMouseTracking(True)
            table_wid.blockSignals(True)
        #
        # for i in range(8):
        #     setattr(self, f"plat_table_model_coords_{i + 1}", QStandardItemModel())
        #     model = getattr(self, f"plat_table_model_coords_{i + 1}")
        #     ui_element = getattr(self.ui, f"table_coords_{i + 1}")
        #     ui_viz = getattr(self.ui, f"well_graphic_coords_{i + 1}")
        #     ui_element.setModel(model)
        #     model.dataChanged.connect(partial(self.alter_coords_tables, i+1))
        #     ui_element.setEditTriggers(QAbstractItemView.AllEditTriggers)
        #     self.setup_radio_buttons(i)
        #     grp = getattr(self.ui, f'bg_coords_{i + 1}')
        #     grp.buttonClicked[int].connect(partial(self.toggle_radio_button, group_index=i + 1))
        #     self.dict_figures[i + 1] = plt.figure()
        #     self.dict_canvas[i + 1] = FigureCanvas(self.dict_figures[i + 1])
        #     self.dict_ax[i + 1] = self.dict_figures[i + 1].subplots()
        #     ui_viz.addWidget(self.dict_canvas[i + 1])
        #     line_collection_template, = self.dict_ax[i + 1].plot([], [], color='black', linewidth=1, zorder=5)
        #     self.dict_plats[i + 1] = line_collection_template
        #     self.dict_ax[i + 1].axis('equal')
        #     self.zoom_fac = self.zp.zoom_factory(self.dict_ax[i + 1], 1.1)
        #     figPan = self.zp.pan_factory(self.dict_ax[i + 1])
        #     table_wid = getattr(self.ui, f"plat_table_coords_{i+1}")
        #
        #     table_wid.cellChanged.connect(partial(self.find_new_data, i+1))
        #     table_wid.setMouseTracking(True)
        #     table_wid.blockSignals(True)

        for grp in self.button_groups.values():
            # this signature delivers the button itself
            grp.buttonClicked[QObject].connect(self.toggle_radio_button)
        self.write_all_data()
        self.retrieve_all_data()
        self._program_changes = False
        for i in range(8):

            table_wid = getattr(self.ui, f"plat_table_coords_{i + 1}")
            table_wid.blockSignals(False)
        # for i in range(8):
        #     table_wid = getattr(self.ui, f"plat_table_coords_{i + 1}")
        #     table_wid.blockSignals(False)
        #     ui_element = getattr(self.ui, f"table_coords_{i + 1}")
        #     ui_element.blockSignals(False)
        # self._initializing = False  # Initialization complete

    # def handle_key_press(self, event, table_index):
    #     """Handle key press events for the tables"""
    #     table = getattr(self.ui, f"table_coords_{table_index}")
    #     # Handle original event first
    #     QTableView.keyPressEvent(table, event)
    #
    #     # Check if Delete key was pressed
    #     if event.key() == Qt.Key_Delete or event.key():
    #         self.delete_selected_rows(table_index)

    def delete_selected_rows(self, table_index):
        """Delete selected rows from the specified table"""
        self._program_changes = True  # Set flag for programmatic changes

        table = getattr(self.ui, f"table_coords_{table_index}")
        model = getattr(self, f"plat_table_model_coords_{table_index}")

        points = []
        for row in range(model.rowCount()):
            try:
                x = float(model.data(model.index(row, 0)))
                y = float(model.data(model.index(row, 1)))
                points.append([x, y])
            except (ValueError, TypeError):
                continue
        # Get selection model
        selection = table.selectionModel()
        if not selection.hasSelection():
            self._program_changes = False
            return
        # Get unique rows in descending order
        selected_rows = sorted(set(index.row() for index in selection.selectedIndexes()), reverse=True)
        selected_data = []
        # for rows in range(8):

        for row in selected_rows:
            # For a QStandardItemModel
            row_data = []
            for col in range(model.columnCount()):
                item = model.item(row, col)
                if item:
                    row_data.append(item.data(Qt.DisplayRole))
            if all(x == '' for x in row_data):
                print('remove row')
                model.removeRow(row)
            else:
                print("keep row")
                print(row_data)

            # selected_data.append(row_data)

        # Remove rows
        # for row in selected_rows:
        #     model.removeRow(row)
        # Update visualization
        self._program_changes = False  # Reset flag
        # self.update_from_model_change(table_index)

    def alter_coords_tables(self, table_index, topLeft, bottomRight, roles):
        """Handle data changes in the table models"""
        # Update the visualization based on the model changes
        # if self._initializing:
        #     return  # Skip during initialization
        if self._program_changes:
            return  # Skip if changes are programmatic

        self.delete_selected_rows(table_index)
        self.update_from_model_change(table_index)

    def update_from_model_change(self, table_index):
        def convert_to_shapely_polygon(coords_list):
            # Filter out sublists with empty strings
            filtered_coords = [sublist for sublist in coords_list if all(element != '' for element in sublist)]

            # Convert all string values to floats
            float_coords = [[float(x), float(y)] for x, y in filtered_coords]

            # Create a Shapely Polygon (if we have at least 3 points)
            if len(float_coords) >= 3:
                # Ensure the polygon is closed (first and last points match)
                if float_coords[0] != float_coords[-1]:
                    float_coords.append(float_coords[0])

                return Polygon(float_coords)
            else:
                return None
        """Update visualizations after model changes"""
        model = getattr(self, f"plat_table_model_coords_{table_index}")
        # Extract points from model
        points = []
        selected_data = []
        for row in range(model.rowCount()):
            # For a QStandardItemModel
            row_data = []
            for col in range(model.columnCount()):
                item = model.item(row, col)
                if item:
                    row_data.append(item.data(Qt.DisplayRole))
            selected_data.append(row_data)


        # Check if we have enough points for a valid polygon

        if len(selected_data) >= 3:
            # Create polygon and update display
            # poly = Polygon(points)
            poly = convert_to_shapely_polygon(points)
            # Update the polygon in dict_plats
            x, y = poly.exterior.xy
            self.dict_plats[table_index].set_data(x, y)
            # Store UTM and LatLon versions
            self.dict_utm[table_index] = poly
            # Convert to latlon for display if needed
            latlon_poly = self.convert_utm_to_latlon_poly(poly)
            self.dict_latlon[table_index] = latlon_poly
            # Redraw the canvas
            self.dict_ax[table_index].relim()
            self.dict_ax[table_index].autoscale_view()
            self.dict_canvas[table_index].draw()

        # Update overall section_df when needed
        self.update_model_table(table_index)
        self.retrieve_all_data()

    def update_model_table(self, table_index):
        def extract_pt_data():
            points = []
            for row in range(model.rowCount()):
                try:
                    x = float(model.data(model.index(row, 0)))
                    y = float(model.data(model.index(row, 1)))
                    points.append([x, y])
                except (ValueError, TypeError):
                    continue
            return points
        model = getattr(self, f"plat_table_model_coords_{table_index}")
        ui_data = getattr(self.ui, f"table_coords_{table_index}")
        used_table = getattr(self.ui, f"plat_table_coords_{table_index}")
        data_frame = self.section_df.iloc[table_index-1]
        points_geo = Polygon(extract_pt_data())
        tsr_data = self.validate_coords_table(used_table)
        conc_code = self.label_to_conc_code(tsr_data)
        all_conc_codes = self.section_df['Conc'].unique()
        self.section_df.at[table_index-1, 'geometry'] = points_geo
        self.section_df.at[table_index-1, 'centroid'] = points_geo.centroid

        # # if conc_code in all_conc_codes:
        # #     pass
        # #

        #
        # model.removeRows(0, model.rowCount())
        # for _, data in self.df_custom_viz_pts.iterrows():
        #     row = [data['Easting'], data['Northing']]
        #     items = [QStandardItem(str(item)) for item in row]
        #     for k in range(2):
        #         items[k].setData(row[k])
        #     model.appendRow(items)
        #     ui_data.verticalHeader().setVisible(False)
        #     ui_data.horizontalHeader().setVisible(False)
        #     ui_data.setShowGrid(True)
        #     ui_data.show()

    def convert_utm_to_latlon_poly(self, poly):
        """Convert UTM polygon to LatLon polygon"""
        latlon_coords = []
        for x, y in poly.exterior.coords:
            lat, lon = utm.to_latlon(x, y, 12, 'T')
            latlon_coords.append((lon, lat))  # Note the order swap for lat/lon

        return Polygon(latlon_coords)

    def validate_coords_table(self, used_table):
        tsr_data = []
        for row in range(used_table.rowCount()):
            tsr_row_data = []
            for col in range(used_table.columnCount()):
                tsr_item = used_table.item(row, col)  # QTableWidgetItem or None
                tsr_text = tsr_item.text() if tsr_item else ""
                if tsr_item != "":
                    tsr_row_data.append(tsr_text)
            tsr_data.append(tsr_row_data[0])
        return tsr_data

    def find_new_data(self, i):


        def validate_list(
                values: list[str],
                table: QTableWidget
        ) -> list[str]:
            """
            values: list of exactly 6 strings, in order.
            table: the QTableWidget holding those 6 rows (1 column).

            Returns the same list if all pass validation.
            On failure:
              • highlights invalid rows red,
              • sets a tooltip explaining *that* row’s error,
              • raises ValueError.

            No UI changes occur for valid rows.
            """
            if len(values) != 6:
                raise ValueError("Expected exactly 6 values, got %d." % len(values))

            # ensure the table will show tooltips on hover
            table.setMouseTracking(True)

            # brushes
            error_brush = QBrush(QColor("red"))
            normal_brush = QBrush(QColor("white"))

            bad = False
            # store cleaned results (strip whitespace)
            cleaned = [v.strip() for v in values]

            for row, text in enumerate(cleaned):
                # ensure there's an item to color/tooltip
                item = table.item(row, 0)
                if not item:
                    item = QTableWidgetItem(text)
                    table.setItem(row, 0, item)
                else:
                    item.setText(text)

                # default: valid
                valid = True
                tip = ""

                # 1) empty?
                if not text:
                    valid = False
                    tip = "This field cannot be empty."

                # 2) rows 2,4,5 must be a single letter
                elif row in (0, 1, 3):
                    if not text.isdigit():
                        valid = False
                        tip = "Must be an integer."

                # row 3: N or S
                elif row == 2:
                    if text.upper() not in ("N", "S"):
                        valid = False
                        tip = "Must be 'N' or 'S'."

                # row 5: E or W
                elif row == 4:
                    if text.upper() not in ("E", "W"):
                        valid = False
                        tip = "Must be 'E' or 'W'."

                # row 6: U or S
                elif row == 5:
                    if text.upper() not in ("U", "S"):
                        valid = False
                        tip = "Must be 'U' or 'S'."

                # apply UI feedback only on error
                if valid:
                    # clear any old error styling/tooltip
                    item.setBackground(normal_brush)
                    item.setToolTip("")
                else:
                    item.setBackground(error_brush)
                    item.setToolTip(tip)
                    bad = True

            if bad:
                return False
            return True

        def search_db_for_conc():
            query = f"SELECT * FROM BaseData WHERE Conc = '{conc_code}'"
            return pd.read_sql(query, self.db)

        used_table = getattr(self.ui, f"plat_table_coords_{i}")
        tsr_data = self.validate_coords_table(used_table)
        try:
            output = validate_list(tsr_data, used_table)
        except ValueError:
            return
        if output:
            conc_code = self.label_to_conc_code(tsr_data)
            data = search_db_for_conc()

    def label_to_conc_code(self, label):
        """
        label: either
          - a string like "6 3S 1W U"
          - a list like ['6','3','s','1','w','u']
        returns: e.g. "0603S01WU"
        """
        # 1) Build a flat list of exactly 6 elements:
        if isinstance(label, str):
            tokens = label.split()  # ["6","3S","1W","U"]
            flat = []
            for tok in tokens:
                # split any digit+letter combo
                if tok[:-1].isdigit() and tok[-1].isalpha():
                    flat.append(tok[:-1])
                    flat.append(tok[-1])
                else:
                    flat.append(tok)
        else:
            # assume it’s already a list of 6 strings or ints
            flat = [str(x) for x in label]
        if len(flat) != 6:
            raise ValueError(f"Expected 6 parts after splitting, got {len(flat)}: {flat!r}")

        # 2) Zero-pad and uppercase as needed:
        section = flat[0].zfill(2)
        township = flat[1].zfill(2)
        rng = flat[3].zfill(2)

        code = (
                section
                + township
                + flat[2].upper()
                + rng
                + flat[4].upper()
                + flat[5].upper()
        )
        return code
    def label_to_conc_code2(self, label):
        if isinstance(label, str):
            label = label.split()
            out = []
            for v in label:
                m = re.fullmatch(r'(\d+)([A-Za-z])', v)
                if m:
                    # split into the digit part and the letter
                    out.extend(m.groups())
                else:
                    out.append(v)
            label = out
        section = label[0].zfill(2)
        township = label[1].zfill(2)
        rng = label[3].zfill(2)
        full = [section, township, label[2].upper(), rng, label[4].upper(), label[-1].upper()]
        return "".join(full)


    def retrieve_all_data(self):
        def retrieve_label():
            used_table = getattr(self.ui, f"plat_table_coords_{i}")
            tsr_data = []
            for row in range(used_table.rowCount()):
                tsr_row_data = []
                for col in range(used_table.columnCount()):
                    tsr_item = used_table.item(row, col)  # QTableWidgetItem or None
                    tsr_text = tsr_item.text() if tsr_item else ""
                    tsr_row_data.append(tsr_text)
                tsr_data.append(tsr_row_data[0])
            label = f"{tsr_data[0]} {tsr_data[1]}{tsr_data[2]} {tsr_data[3]}{tsr_data[4]} {tsr_data[5]}"
            return label

        def retrieve_coords_data():
            selected_model = getattr(self, f"plat_table_model_coords_{i}")
            table_data = [[selected_model.data(selected_model.index(row, column)) for column in
                           range(selected_model.columnCount())] for row in
                          range(selected_model.rowCount())]
            table_data = [r for r in table_data if r and None not in r and '' not in r]
            table_data = [[float(r[0]), float(r[1])] for r in table_data]
            poly_out = Polygon(table_data)
            return poly_out, poly_out.centroid
        full_data = []
        for i in range(1,9):
            try:
                label = retrieve_label()
                conc_code = self.label_to_conc_code(label)
                poly, cent = retrieve_coords_data()
                full_data.append([conc_code, poly, label, cent])
            except (IndexError, ValueError) as e:
                pass
        columns = ['Conc', 'geometry', 'label', 'centroid']
        self.section_df = pd.DataFrame(columns=columns, data=full_data)

    def setup_radio_buttons(self, i):
        button_group = getattr(self.ui, f"bg_coords_{i + 1}")
        button = getattr(self.ui, f"utm_radio_coords_{i + 1}")
        button_group.blockSignals(True)
        button.blockSignals(True)
        button.setChecked(True)
        button_group.blockSignals(False)
        button.blockSignals(True)

    def setup_sqlite_db(self):
        path_used_db = r'C:\Work\Databases'
        apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
        return sqlite3.connect(apd_data_dir)

    def toggle_radio_button(self, button_id: int, group_index: int):
        try:
            if button_id == -3:
                data_used = self.dict_latlon[group_index]
                self.write_coordinates(list(data_used.exterior.coords), group_index)
                self.draw_well_data(group_index, "latlon")
            elif button_id == -2:
                data_used = self.dict_utm[group_index]
                self.write_coordinates(list(data_used.exterior.coords), group_index)
                self.draw_well_data(group_index, "utm")
        except AttributeError:
            pass

    def draw_well_data(self, group_id, coord_type_label):
        dict_used = getattr(self, f"dict_{coord_type_label}")[group_id]
        canvas_used = getattr(self, f"dict_canvas")[group_id]
        ax_used = getattr(self, f"dict_ax")[group_id]
        line_collection_used = self.dict_plats[group_id]
        x, y = np.array(dict_used.exterior.coords).T
        line_collection_used.set_data(x, y)
        ax_used.relim()
        ax_used.autoscale_view()
        canvas_used.blit(ax_used.bbox)
        canvas_used.draw()

    def write_coordinates(self, points, i):
        self._program_changes = True
        main_table = getattr(self.ui, f"table_coords_{i}")
        model = getattr(self, f"plat_table_model_coords_{i}")
        model.setRowCount(0)  # Clear existing rows efficiently
        main_table.setModel(model)
        main_table.setUpdatesEnabled(False)
        main_table.verticalHeader().setVisible(False)
        main_table.setShowGrid(True)
        model.setHorizontalHeaderLabels(['X', 'Y'])
        for val, (x, y) in enumerate(points):
            model.setItem(val, 0, QStandardItem(f"{x:.3f}"))
            model.setItem(val, 1, QStandardItem(f"{y:.3f}"))
        main_table.setUpdatesEnabled(True)
        main_table.show()

        self._program_changes = False
    # def write_coordinates(self, points, i):
    #     main_table = getattr(self.ui, f"table_coords_{i}")
    #     model = getattr(self, f"plat_table_model_coords_{i}")
    #
    #     # Tell the view a reset is starting
    #     model.beginResetModel()
    #
    #     # Clear existing data
    #     model.setRowCount(0)
    #     model.setColumnCount(2)
    #     model.setHorizontalHeaderLabels(['X', 'Y'])
    #
    #     # Add data
    #     for val, (x, y) in enumerate(points):
    #         row_items = [QStandardItem(f"{x:.3f}"), QStandardItem(f"{y:.3f}")]
    #         model.appendRow(row_items)
    #
    #     # Signal the view that reset is complete
    #     model.endResetModel()
    #
    #     # Configure view
    #     main_table.verticalHeader().setVisible(False)
    #     main_table.setShowGrid(True)
    #     main_table.resizeColumnsToContents()
    #     main_table.viewport().update()
    #
    #     # Force the view to appear
    #     main_table.update()
    #     main_table.repaint()


    def write_all_data(self):
        def write_tsr():
            tsr_info = getattr(self.ui, f"plat_table_coords_{i + 1}")
            parameters = row['label'].split(" ")
            section = int(float(parameters[0]))
            township = int(float(parameters[1][:-1]))
            township_dir = parameters[1][-1:]
            rng = int(float(parameters[2][:-1]))
            rng_dir = parameters[2][-1:]
            meridian = parameters[3]
            data = [section, township, township_dir, rng, rng_dir, meridian]
            tsr_info.clearContents()  # optional: clear old items
            tsr_info.setRowCount(len(data))
            tsr_info.setColumnCount(1)
            tsr_info.setHorizontalHeaderLabels(['Value'])  # adjust header text as needed
            for row2, val in enumerate(data):
                tsr_info.setItem(row2, 0, QTableWidgetItem(str(val)))
        def convert_utm_to_latlon():
            utm_poly = row['geometry']
            transformer = Transformer.from_crs("EPSG:32612", "EPSG:4326", always_xy=True)
            lonlat = [transformer.transform(x, y) for x, y in utm_poly.exterior.coords]
            self.dict_latlon[index_val] = Polygon(lonlat)
        for i, row in self.section_df.iterrows():
            index_val = i + 1
            self.write_coordinates(list(row['geometry'].exterior.coords), index_val)
            write_tsr()
            convert_utm_to_latlon()
            self.dict_utm[index_val] = row['geometry']
            self.draw_well_data(index_val, 'utm')
