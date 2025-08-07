"""
Plat Coordinate Editor Module

This module provides functionality for editing and visualizing oil and gas plat coordinates
in both UTM and Lat/Lon coordinate systems. It handles the conversion between coordinate
systems, database interactions for PLSS (Public Land Survey System) sections, and provides
a Qt-based interface for coordinate manipulation and visualization.

The module integrates with the broader well survey system to manage land plat boundaries
and their associated coordinate data.
"""

import sqlite3
from typing import List, Tuple, Dict, Optional, Union, Any

import pandas as pd
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, Point
import os
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QBrush, QColor
from PyQt5.QtWidgets import (QTableWidgetItem, QWidget, QRadioButton, QButtonGroup,
                             QAbstractItemView, QSizePolicy, QHeaderView, QTableWidget,
                             QMessageBox)
from PyQt5.QtCore import QObject, Qt
import utm
from pyproj import Transformer
from functools import partial
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import numpy as np

# import ModuleAgnostic as ma
from main_project_drawer import ZoomPan


def label_to_conc_code(label: Union[str, List[str]]) -> str:
    """
    Convert a PLSS (Public Land Survey System) label to a concatenated code format.

    This function transforms township-range-section labels into a standardized 9-character
    code used for database queries and unique identification of land parcels.

    Args:
        label: Either a string like "6 3S 1W U" or a list like ['6','3','s','1','w','u']
               Format: [section, township+direction, range+direction, meridian]

    Returns:
        str: Concatenated code in format "0603S01WU" (zero-padded)

    Raises:
        ValueError: If the label doesn't contain exactly 6 parts after parsing

    Example:
        >>> label_to_conc_code("6 3S 1W U")
        '0603S01WU'
        >>> label_to_conc_code(['6', '3', 's', '1', 'w', 'u'])
        '0603S01WU'
    """
    # Build a flat list of exactly 6 elements
    if isinstance(label, str):
        tokens = label.split()  # ["6","3S","1W","U"]
        flat = []
        for tok in tokens:
            # Split any digit+letter combo (e.g., "3S" -> ["3", "S"])
            if tok[:-1].isdigit() and tok[-1].isalpha():
                flat.append(tok[:-1])
                flat.append(tok[-1])
            else:
                flat.append(tok)
    else:
        # Assume it's already a list of 6 strings or ints
        flat = [str(x) for x in label]

    if len(flat) != 6:
        raise ValueError(f"Expected 6 parts after splitting, got {len(flat)}: {flat!r}")

    # Zero-pad numeric values and uppercase directional indicators
    section = flat[0].zfill(2)  # Section number (01-36)
    township = flat[1].zfill(2)  # Township number
    rng = flat[3].zfill(2)  # Range number

    # Concatenate all parts into standardized code
    code = (section + township + flat[2].upper() + rng + flat[4].upper() + flat[5].upper())
    return code


# def setup_sqlite_db() -> sqlite3.Connection:
#     """
#     Establish connection to the PLSS sections SQLite database.
#
#     This database contains the base coordinate data for all Public Land Survey System
#     sections, which serve as the foundation for plat boundary definitions.
#
#     Returns:
#         sqlite3.Connection: Active database connection
#
#     Note:
#         The database path is hardcoded to 'C:\\Work\\Databases\\Board_DB_Plss_Sections.db'
#         which should be made configurable in production environments.
#     """
#     path_used_db = r'C:\Work\Databases'
#     apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
#     return sqlite3.connect(apd_data_dir)


def validate_coords_table(used_table: QTableWidget) -> List[str]:
    """
    Extract and validate coordinate data from a QTableWidget.

    This function reads all non-empty cells from the first column of the table,
    typically used for extracting township-range-section identifiers.

    Args:
        used_table: QTableWidget containing coordinate or identifier data

    Returns:
        List[str]: List of non-empty text values from the table's first column
    """
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


def convert_utm_to_latlon_poly(poly: Polygon) -> Polygon:
    """
    Convert a polygon from UTM Zone 12N coordinates to WGS84 latitude/longitude.

    This function handles the coordinate system transformation required for displaying
    plat boundaries in geographic coordinates, which is essential for integration
    with mapping systems and GPS data.

    Args:
        poly: Shapely Polygon with coordinates in UTM Zone 12N (meters)

    Returns:
        Polygon: New polygon with coordinates in WGS84 lat/lon (degrees)

    Note:
        - UTM Zone 12N is hardcoded (covers much of western US oil fields)
        - Coordinate order is swapped: UTM (x,y) becomes LatLon (lon,lat)
    """
    latlon_coords = []
    for x, y in poly.exterior.coords:
        lat, lon = utm.to_latlon(x, y, 12, 'T')
        latlon_coords.append((lon, lat))  # Note the order swap for lat/lon
    return Polygon(latlon_coords)


def bad_utm() -> None:
    """
    Display a warning dialog for invalid UTM coordinate entries.

    This provides user feedback when entered coordinates fall outside the valid
    UTM Zone 12N range, preventing data corruption and calculation errors.
    """
    choice = QMessageBox.warning(None, "Attention", "Invalid UTM Entry", QMessageBox.Ok)


class PlatCoordEditor:
    """
    Main editor class for managing plat coordinate data and visualization.

    This class provides a comprehensive interface for editing land plat boundaries,
    handling coordinate system conversions, and managing the associated database
    operations. It supports up to 8 simultaneous plat sections with independent
    coordinate editing and visualization capabilities.

    The editor integrates with Qt widgets for user interaction and matplotlib for
    visualization, providing zoom/pan functionality and real-time coordinate conversion
    between UTM and geographic coordinate systems.

    Attributes:
        section_df (pd.DataFrame): DataFrame containing section geometry and metadata
        conn (sqlite3.Connection): Database connection for PLSS data queries
        ui: Qt UI object containing widget references
        dict_utm (Dict[int, Polygon]): UTM polygons indexed by plat number (1-8)
        dict_latlon (Dict[int, Polygon]): Lat/Lon polygons indexed by plat number
        button_groups (Dict): Radio button groups for coordinate system selection
        dict_plats (Dict[int, Line2D]): Matplotlib line objects for each plat
        dict_figures (Dict[int, Figure]): Matplotlib figures for each plat
        dict_canvas (Dict[int, FigureCanvas]): Qt canvas widgets for each plat
        dict_ax (Dict[int, Axes]): Matplotlib axes for each plat visualization
        zp (ZoomPan): Zoom and pan handler for interactive visualization
        _program_changes (bool): Flag to distinguish programmatic vs user changes
        _all_points_for_plats (pd.DataFrame): Current plat polygon data
        _all_original_points_for_plats (pd.DataFrame): Original plat data for reset
    """

    def __init__(self, section_df: pd.DataFrame, ui: Any, conn: sqlite3.Connection) -> None:
        """
        Initialize the plat coordinate editor with data and UI connections.

        Sets up 8 independent plat editing interfaces with coordinate tables,
        visualization canvases, and coordinate system toggle controls. Each plat
        can be edited independently with full undo/reset capabilities.

        Args:
            section_df: Initial DataFrame containing plat section data
            ui: Qt UI object with widget references (expects specific naming convention)
            conn: Active database connection for PLSS data queries
        """
        self.section_df = section_df
        self.conn = conn
        self.ui = ui
        self.dict_utm = dict.fromkeys(range(1, 9))
        self.dict_latlon = dict.fromkeys(range(1, 9))
        self.button_groups = {}
        self.dict_plats = {}
        self.dict_figures = {}
        self.dict_canvas = {}
        self.dict_ax = {}
        self.zp = ZoomPan()
        self._program_changes = True  # Flag for programmatic changes
        self._all_points_for_plats = pd.DataFrame(columns=['index', 'geometry'])
        self._all_original_points_for_plats = pd.DataFrame(columns=['index', 'geometry'])

        # Initialize 8 plat editing interfaces
        for i in range(8):
            # Create model and connect to UI elements
            setattr(self, f"plat_table_model_coords_{i + 1}", QStandardItemModel())
            model = getattr(self, f"plat_table_model_coords_{i + 1}")
            ui_element = getattr(self.ui, f"table_coords_{i + 1}")
            ui_viz = getattr(self.ui, f"well_graphic_coords_{i + 1}")
            reset_button = getattr(self.ui, f"refresh_data_button_coords_{i + 1}")

            # Configure table for coordinate editing
            ui_element.blockSignals(True)
            ui_element.setModel(model)
            self._setup_radio_buttons(i)

            # Connect radio button signals for coordinate system switching
            grp = getattr(self.ui, f'bg_coords_{i + 1}')
            grp.buttonClicked[int].connect(partial(self._toggle_radio_button, group_index=i + 1))

            # Configure table selection and editing behavior
            ui_element.setSelectionMode(QAbstractItemView.ExtendedSelection)
            ui_element.setSelectionBehavior(QAbstractItemView.SelectRows)
            ui_element.setEditTriggers(QAbstractItemView.AllEditTriggers)

            # Connect data change signal for real-time updates
            model.dataChanged.connect(partial(self._alter_coords_tables, i + 1))

            # Setup matplotlib visualization components
            self.dict_figures[i + 1] = plt.figure()
            self.dict_canvas[i + 1] = FigureCanvas(self.dict_figures[i + 1])
            self.dict_ax[i + 1] = self.dict_figures[i + 1].subplots()
            ui_viz.addWidget(self.dict_canvas[i + 1])

            # Create line object for plat boundary visualization
            line_collection_template, = self.dict_ax[i + 1].plot([], [], color='black', linewidth=1, zorder=5)
            self.dict_plats[i + 1] = line_collection_template
            self.dict_ax[i + 1].axis('equal')

            # Enable zoom and pan functionality
            self.zoom_fac = self.zp.zoom_factory(self.dict_ax[i + 1], 1.1)
            figPan = self.zp.pan_factory(self.dict_ax[i + 1])

            # Connect table editing signals
            table_wid = getattr(self.ui, f"plat_table_coords_{i + 1}")
            table_wid.cellChanged.connect(partial(self._find_new_data, i + 1))
            table_wid.setMouseTracking(True)
            table_wid.blockSignals(True)

        # Connect radio button groups for coordinate system selection
        for grp in self.button_groups.values():
            grp.buttonClicked[QObject].connect(self._toggle_radio_button)

        # Load initial data and enable user interaction
        self._write_all_data()
        self.retrieve_all_data()
        self._program_changes = False

        # Re-enable signals for user interaction
        for i in range(8):
            table_wid = getattr(self.ui, f"plat_table_coords_{i + 1}")
            table_wid.blockSignals(False)

    def _delete_selected_rows(self, table_index: int) -> None:
        """
        Delete selected rows from the specified coordinate table.

        This method handles row deletion while maintaining polygon integrity,
        ensuring that enough points remain to form a valid polygon (minimum 3).
        Empty rows are automatically removed without affecting valid data.

        Args:
            table_index: Index of the plat table (1-8) to delete rows from
        """
        self._program_changes = True  # Prevent cascading updates during deletion

        table = getattr(self.ui, f"table_coords_{table_index}")
        model = getattr(self, f"plat_table_model_coords_{table_index}")

        # Extract current points for validation
        points = []
        for row in range(model.rowCount()):
            try:
                x = float(model.data(model.index(row, 0)))
                y = float(model.data(model.index(row, 1)))
                points.append([x, y])
            except (ValueError, TypeError):
                continue

        # Check for selected rows
        selection = table.selectionModel()
        if not selection.hasSelection():
            self._program_changes = False
            return

        # Get unique rows in descending order to avoid index shifting
        selected_rows = sorted(set(index.row() for index in selection.selectedIndexes()), reverse=True)

        for row in selected_rows:
            # Check if row contains only empty data
            row_data = []
            for col in range(model.columnCount()):
                item = model.item(row, col)
                if item:
                    row_data.append(item.data(Qt.DisplayRole))
            if all(x == '' for x in row_data):
                model.removeRow(row)

        self._program_changes = False

    def _alter_coords_tables(self, table_index: int, topLeft: Any, bottomRight: Any, roles: Any) -> None:
        """
        Handle data changes in coordinate table models.

        This method responds to user edits in the coordinate tables, triggering
        validation, visualization updates, and data synchronization. It filters
        out programmatic changes to prevent infinite update loops.

        Args:
            table_index: Index of the modified table (1-8)
            topLeft: Top-left cell of the changed region (Qt model index)
            bottomRight: Bottom-right cell of the changed region (Qt model index)
            roles: Qt data roles that were modified
        """
        if self._program_changes:
            return  # Skip if changes are programmatic

        self._delete_selected_rows(table_index)
        self._update_from_model_change(table_index)

    def _update_from_model_change(self, table_index: int) -> None:
        """
        Update visualizations and data structures after coordinate table changes.

        This method validates the modified coordinates, creates new polygon geometries,
        performs coordinate system conversions, and updates all related visualizations.
        It includes UTM range validation to prevent invalid coordinate entries.

        Args:
            table_index: Index of the table that was modified (1-8)
        """
        if self._program_changes:
            return

        def convert_to_shapely_polygon(coords_list: List[List[str]]) -> Optional[Polygon]:
            """
            Convert coordinate list to Shapely Polygon with validation.

            Filters out empty values, converts strings to floats, and ensures
            the polygon is properly closed for valid geometry creation.
            """
            # Filter out sublists with empty strings
            filtered_coords = [sublist for sublist in coords_list if all(element != '' for element in sublist)]
            # Convert all string values to floats
            float_coords = [[float(x), float(y)] for x, y in filtered_coords]

            # Create a Shapely Polygon (requires at least 3 points)
            if len(float_coords) >= 3:
                # Ensure the polygon is closed
                if float_coords[0] != float_coords[-1]:
                    float_coords.append(float_coords[0])
                return Polygon(float_coords)
            else:
                return None

        def is_valid_utm(x: Union[str, float], y: Union[str, float]) -> bool:
            """
            Validate UTM coordinates for Zone 12N range.

            UTM Zone 12N covers longitudes 114°W to 108°W, which translates
            to specific easting and northing ranges in meters.
            """
            try:
                x, y = float(x), float(y)
                # Valid UTM Zone 12N ranges
                return (160000 <= x <= 840000) and (0 <= y <= 10000000)
            except (ValueError, TypeError):
                return False

        model = getattr(self, f"plat_table_model_coords_{table_index}")

        # Extract coordinate data from model
        points = []
        selected_data = []
        for row in range(model.rowCount()):
            row_data = []
            for col in range(model.columnCount()):
                item = model.item(row, col)
                if item:
                    row_data.append(item.data(Qt.DisplayRole))
            selected_data.append(row_data)

        # Validate all coordinates before processing
        for row_data in selected_data:
            if len(row_data) >= 2 and row_data[0] != '' and row_data[1] != '':
                if not is_valid_utm(row_data[0], row_data[1]):
                    bad_utm()
                    self._reset_table(table_index)
                    return

        # Create polygon if we have enough valid points
        if len(selected_data) >= 3:
            poly = convert_to_shapely_polygon(selected_data)

            # Update visualization
            x, y = poly.exterior.xy
            self.dict_plats[table_index].set_data(x, y)

            # Store UTM version
            self.dict_utm[table_index] = poly

            # Convert to lat/lon and update display
            try:
                latlon_poly = convert_utm_to_latlon_poly(poly)
                self.dict_latlon[table_index] = latlon_poly

                # Redraw the canvas with new data
                self.dict_ax[table_index].relim()
                self.dict_ax[table_index].autoscale_view()
                self.dict_canvas[table_index].draw()

                # Update stored polygon data
                self._all_points_for_plats.loc[table_index - 1, 'polygon'] = poly
            except utm.error.OutOfRangeError as e:
                bad_utm()
                self._reset_table(table_index)
                return

        self.retrieve_all_data()

    def _reset_table(self, table_index: int) -> None:
        """
        Reset coordinate table to original values.

        This method provides undo functionality by reverting the specified plat's
        coordinates to their original state from when the editor was initialized.

        Args:
            table_index: Index of the table to reset (1-8)
        """
        self._program_changes = True  # Prevent validation during reset

        # Find original data for this plat
        original_row = self._all_original_points_for_plats[
            self._all_original_points_for_plats['index'] == table_index
            ]

        if not original_row.empty:
            original_polygon = original_row['geometry'].iloc[0]
            original_coords = list(original_polygon.exterior.coords[:-1])
            self._write_coordinates(original_coords, table_index)

        self._program_changes = False

    def _rewrite_utms(self, points: List[Tuple[float, float]], i: int) -> None:
        """
        Rewrite UTM coordinates to the specified table.

        This internal method updates a coordinate table with new UTM points,
        handling the UI updates and data storage in a single operation.

        Args:
            points: List of (x, y) coordinate tuples in UTM
            i: Table index (1-8) to update
        """
        self._program_changes = True

        main_table = getattr(self.ui, f"table_coords_{i}")
        model = getattr(self, f"plat_table_model_coords_{i}")

        # Clear and reconfigure table
        model.setRowCount(0)
        main_table.setModel(model)
        main_table.setUpdatesEnabled(False)
        main_table.verticalHeader().setVisible(False)
        main_table.setShowGrid(True)
        model.setHorizontalHeaderLabels(['X', 'Y'])

        # Store polygon data
        data_for_df = [i, Polygon(points)]
        self._all_points_for_plats.loc[len(self._all_points_for_plats)] = data_for_df

        # Populate table with formatted coordinates
        for val, (x, y) in enumerate(points):
            model.setItem(val, 0, QStandardItem(f"{x:.3f}"))
            model.setItem(val, 1, QStandardItem(f"{y:.3f}"))

        main_table.setUpdatesEnabled(True)
        main_table.show()
        self._program_changes = False

    def _find_new_data(self, i: int) -> None:
        """
        Search for new plat data based on township-range-section input.

        This method validates user-entered TSR data, converts it to a concatenated
        code, and queries the database for corresponding plat geometry. It provides
        detailed validation feedback for each field.

        Args:
            i: Index of the plat being searched (1-8)
        """

        def validate_list(values: List[str], table: QTableWidget) -> bool:
            """
            Validate township-range-section input with visual feedback.

            Validates each component of the TSR identifier and provides
            specific error messages and visual highlighting for invalid entries.

            Expected format:
            - Row 0: Section number (1-36)
            - Row 1: Township number
            - Row 2: Township direction (N/S)
            - Row 3: Range number
            - Row 4: Range direction (E/W)
            - Row 5: Meridian identifier (U/S)
            """
            if len(values) != 6:
                raise ValueError("Expected exactly 6 values, got %d." % len(values))

            # Enable tooltips for error messages
            table.setMouseTracking(True)

            # Define brushes for visual feedback
            error_brush = QBrush(QColor("red"))
            normal_brush = QBrush(QColor("white"))

            bad = False
            cleaned = [v.strip() for v in values]

            for row, text in enumerate(cleaned):
                # Ensure table item exists
                item = table.item(row, 0)
                if not item:
                    item = QTableWidgetItem(text)
                    table.setItem(row, 0, item)
                else:
                    item.setText(text)

                valid = True
                tip = ""

                # Validate based on row position
                if not text:
                    valid = False
                    tip = "This field cannot be empty."
                elif row in (0, 1, 3):  # Numeric fields
                    if not text.isdigit():
                        valid = False
                        tip = "Must be an integer."
                elif row == 2:  # Township direction
                    if text.upper() not in ("N", "S"):
                        valid = False
                        tip = "Must be 'N' or 'S'."
                elif row == 4:  # Range direction
                    if text.upper() not in ("E", "W"):
                        valid = False
                        tip = "Must be 'E' or 'W'."
                elif row == 5:  # Meridian
                    if text.upper() not in ("U", "S"):
                        valid = False
                        tip = "Must be 'U' or 'S'."

                # Apply visual feedback
                if valid:
                    item.setBackground(normal_brush)
                    item.setToolTip("")
                else:
                    item.setBackground(error_brush)
                    item.setToolTip(tip)
                    bad = True

            return not bad

        def search_db_for_conc() -> pd.DataFrame:
            """Query database for plat geometry using concatenated code."""
            query = f"SELECT * FROM BaseData WHERE Conc = '{conc_code}'"
            return pd.read_sql(query, self.conn)

        used_table = getattr(self.ui, f"plat_table_coords_{i}")
        tsr_data = validate_coords_table(used_table)

        try:
            output = validate_list(tsr_data, used_table)
        except ValueError:
            return

        if output:
            conc_code = label_to_conc_code(tsr_data)
            data = search_db_for_conc()
            # Further processing would occur here based on database results

    def retrieve_all_data(self) -> None:
        """
        Consolidate all plat data from UI tables into the section DataFrame.

        This method collects data from all 8 plat editors, validates the coordinates,
        creates polygon geometries, and updates the main section_df with the current
        state of all plats. This is typically called after any modification to ensure
        data consistency across the application.
        """

        def retrieve_label() -> str:
            """Extract TSR label from table widgets."""
            used_table = getattr(self.ui, f"plat_table_coords_{i}")
            tsr_data = []
            for row in range(used_table.rowCount()):
                tsr_row_data = []
                for col in range(used_table.columnCount()):
                    tsr_item = used_table.item(row, col)
                    tsr_text = tsr_item.text() if tsr_item else ""
                    tsr_row_data.append(tsr_text)
                tsr_data.append(tsr_row_data[0])
            # Format as standard TSR label
            label = f"{tsr_data[0]} {tsr_data[1]}{tsr_data[2]} {tsr_data[3]}{tsr_data[4]} {tsr_data[5]}"
            return label

        def retrieve_coords_data() -> Tuple[Polygon, Point]:
            """Extract coordinate data and create polygon geometry."""
            selected_model = getattr(self, f"plat_table_model_coords_{i}")
            table_data = [[selected_model.data(selected_model.index(row, column)) for column in
                           range(selected_model.columnCount())] for row in
                          range(selected_model.rowCount())]
            # Filter out empty rows
            table_data = [r for r in table_data if r and None not in r and '' not in r]
            # Convert to float coordinates
            table_data = [[float(r[0]), float(r[1])] for r in table_data]
            poly_out = Polygon(table_data)
            return poly_out, poly_out.centroid

        full_data = []
        for i in range(1, 9):
            try:
                label = retrieve_label()
                conc_code = label_to_conc_code(label)
                poly, cent = retrieve_coords_data()
                full_data.append([conc_code, poly, label, cent])
            except (IndexError, ValueError) as e:
                # Skip invalid or incomplete plats
                pass

        # Update main DataFrame with collected data
        columns = ['Conc', 'geometry', 'label', 'centroid']
        self.section_df = pd.DataFrame(columns=columns, data=full_data)

    def _setup_radio_buttons(self, i: int) -> None:
        """
        Configure radio buttons for coordinate system selection.

        Sets up the UTM/LatLon toggle buttons for each plat editor,
        defaulting to UTM display mode.

        Args:
            i: Zero-based index for the plat editor (0-7)
        """
        button_group = getattr(self.ui, f"bg_coords_{i + 1}")
        button = getattr(self.ui, f"utm_radio_coords_{i + 1}")

        # Temporarily block signals during setup
        button_group.blockSignals(True)
        button.blockSignals(True)
        button.setChecked(True)  # Default to UTM
        button_group.blockSignals(False)
        button.blockSignals(False)

    def _toggle_radio_button(self, button_id: int, group_index: int) -> None:
        """
        Handle coordinate system toggle between UTM and Lat/Lon display.

        This method switches the coordinate display and updates both the table
        and visualization when the user toggles between coordinate systems.

        Args:
            button_id: Qt button ID (-3 for LatLon, -2 for UTM)
            group_index: Plat index (1-8) being toggled
        """
        try:
            if button_id == -3:  # Lat/Lon selected
                data_used = self.dict_latlon[group_index]
                self._write_coordinates(list(data_used.exterior.coords), group_index)
                self._draw_well_data(group_index, "latlon")
            elif button_id == -2:  # UTM selected
                data_used = self.dict_utm[group_index]
                self._write_coordinates(list(data_used.exterior.coords), group_index)
                self._draw_well_data(group_index, "utm")
        except AttributeError:
            # Handle case where data hasn't been loaded yet
            pass

    def _draw_well_data(self, group_id: int, coord_type_label: str) -> None:
        """
        Update the matplotlib visualization for a specific plat.

        This method refreshes the visual display of plat boundaries after
        coordinate changes or system toggles, ensuring the plot accurately
        reflects the current data state.

        Args:
            group_id: Plat index (1-8) to update
            coord_type_label: Either "utm" or "latlon" to specify coordinate system
        """
        # Get appropriate coordinate data
        dict_used = getattr(self, f"dict_{coord_type_label}")[group_id]
        canvas_used = self.dict_canvas[group_id]
        ax_used = self.dict_ax[group_id]
        line_collection_used = self.dict_plats[group_id]

        # Update line data with polygon coordinates
        x, y = np.array(dict_used.exterior.coords).T
        line_collection_used.set_data(x, y)

        # Refresh plot limits and redraw
        ax_used.relim()
        ax_used.autoscale_view()
        canvas_used.blit(ax_used.bbox)
        canvas_used.draw()

    def _write_coordinates(self, points: List[Tuple[float, float]], i: int) -> None:
        """
        Write coordinate data to the specified table widget.

        This method populates a coordinate table with the provided points,
        formatting them for display and storing the original data for reset
        functionality. It handles both initial loading and updates.

        Args:
            points: List of (x, y) coordinate tuples
            i: Table index (1-8) to populate
        """
        # Store original data on first write
        if i not in self._all_original_points_for_plats:
            self._all_original_points_for_plats.loc[len(self._all_original_points_for_plats)] = [i, Polygon(points)]

        self._program_changes = True

        try:
            main_table = getattr(self.ui, f"table_coords_{i}")
        except AttributeError:
            return

        model = getattr(self, f"plat_table_model_coords_{i}")

        # Clear and configure table
        model.setRowCount(0)
        model.setHorizontalHeaderLabels(['X', 'Y'])
        main_table.setModel(model)
        main_table.setUpdatesEnabled(False)

        # Store current polygon data
        self._all_points_for_plats.loc[len(self._all_points_for_plats)] = [i, Polygon(points)]

        # Populate table with formatted coordinates
        for val, (x, y) in enumerate(points):
            model.setItem(val, 0, QStandardItem(f"{x:.3f}"))
            model.setItem(val, 1, QStandardItem(f"{y:.3f}"))

        main_table.setUpdatesEnabled(True)
        main_table.show()
        self._program_changes = False

    def _write_all_data(self) -> None:
        """
        Initialize all plat editors with data from the section DataFrame.

        This method populates all 8 plat editors with existing data from
        section_df, setting up the TSR identifiers, coordinate tables,
        and visualizations. It performs the initial coordinate system
        conversions and establishes the baseline for editing operations.
        """

        def write_tsr() -> None:
            """Write township-range-section data to the UI table."""
            tsr_info = getattr(self.ui, f"plat_table_coords_{i + 1}")
            parameters = row['label'].split(" ")

            # Parse TSR components
            section = int(float(parameters[0]))
            township = int(float(parameters[1][:-1]))
            township_dir = parameters[1][-1:]
            rng = int(float(parameters[2][:-1]))
            rng_dir = parameters[2][-1:]
            meridian = parameters[3]

            data = [section, township, township_dir, rng, rng_dir, meridian]

            # Configure and populate TSR table
            tsr_info.clearContents()
            tsr_info.setRowCount(len(data))
            tsr_info.setColumnCount(1)
            tsr_info.setHorizontalHeaderLabels(['Value'])

            for row2, val in enumerate(data):
                tsr_info.setItem(row2, 0, QTableWidgetItem(str(val)))

        def convert_utm_to_latlon() -> None:
            """Convert UTM polygon to lat/lon using pyproj."""
            utm_poly = row['geometry']
            transformer = Transformer.from_crs("EPSG:32612", "EPSG:4326", always_xy=True)
            lonlat = [transformer.transform(x, y) for x, y in utm_poly.exterior.coords]
            self.dict_latlon[index_val] = Polygon(lonlat)

        # Process each row in section_df
        for i, row in self.section_df.iterrows():
            index_val = i + 1
            # Write coordinates and TSR data
            self._write_coordinates(list(row['geometry'].exterior.coords), index_val)
            write_tsr()
            convert_utm_to_latlon()
            # Store UTM polygon and update visualization
            self.dict_utm[index_val] = row['geometry']
            self._draw_well_data(index_val, 'utm')