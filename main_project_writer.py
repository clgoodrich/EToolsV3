import decimal
import pandas as pd
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QHeaderView, QAbstractItemView
import math
import numpy as np
from typing import Dict, Any, Optional, Union
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QDialog,
                             QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
                             QDialogButtonBox, QLabel)





def _isolate_footage_depths(survey: pd.DataFrame, spec_data: pd.DataFrame) -> pd.DataFrame:
    """Extract specific depth points and their associated clearance footage data.

    Identifies key trajectory points (KOP, Landing Point, BHL) from survey data and
    extracts their corresponding clearance footage measurements for regulatory reporting
    and engineering analysis. Creates a focused dataset for critical depth analysis.

    Args:
        survey (pd.DataFrame): Complete survey trajectory data with measured depth and clearance calculations
        spec_data (pd.DataFrame): Special depth points data containing KOP and Landing Point information

    Returns:
        pd.DataFrame: Filtered dataset containing only key depth points with labels, clearance
            footages (FNL, FSL, FEL, FWL), measured depth, and azimuth data
    """
    # Step 1: Define key depth points mapping from special data and survey extremes
    depths_lst = {'kop': spec_data['measured_depth'].iloc[0],  # Kick-off point depth
                  'prod': spec_data['measured_depth'].iloc[1],  # Production/landing point depth
                  'bhl': survey['measured_depth'].iloc[-1]}  # Bottom hole location depth

    # Step 2: Create reverse mapping for depth-to-label assignment
    reverse_map = {v: k for k, v in depths_lst.items()}

    # Step 3: Filter survey data to only include the key depth points
    dx_lst = survey[survey['measured_depth'].isin(depths_lst.values())]

    # Step 4: Add descriptive labels for each depth point
    dx_lst['lbl'] = dx_lst['measured_depth'].map(reverse_map)

    # Step 5: Select essential columns for footage analysis and reporting
    df = dx_lst[['lbl', 'FNL', 'FSL', 'FEL', 'FWL', 'measured_depth', 'azimuth']]

    return df


class DataWriter:
    """User interface data writer for displaying survey results and clearance calculations.

    This class manages the presentation of processed survey data in PyQt5 GUI components,
    handling multiple table views, line edits, and data formatting for engineering analysis
    and regulatory reporting. Provides real-time updates and numerical precision control
    for professional oil and gas software applications.
    """

    def __init__(self, ui: Any, surveys: Dict[str, Any], spec_surveys: Dict[str, Any],
                 parameters: Dict[str, Any], plat_df: pd.DataFrame) -> None:
        """Initialize data writer with survey results and UI component setup.

        Sets up multiple data models for different table views, configures UI components
        for read-only display, and initializes text fields for survey parameters. Creates
        the foundation for dynamic data presentation and user interaction.

        Args:
            ui (Any): PyQt5 user interface object containing table views and line edits
            surveys (Dict[str, Any]): Dictionary of processed survey objects with clearance data
            spec_surveys (Dict[str, Any]): Dictionary of special depth points for each survey type
            parameters (Dict[str, Any]): Survey processing parameters including convergence and north reference
            plat_df (pd.DataFrame): Plat boundary data for spatial reference
        """
        # Step 1: Store survey data and processing parameters
        self.surveys = surveys
        self.spec_surveys = spec_surveys
        self.survey_parameters = parameters
        self.ui = ui

        # Step 2: Initialize main survey data table model
        self.dx_survey_model = QStandardItemModel()
        self.ui.dx_survey_table_mod.setModel(self.dx_survey_model)
        self.ui.dx_survey_table_mod.setEditTriggers(QAbstractItemView.NoEditTriggers)  # Read-only display

        # Step 3: Initialize clearance footages table model
        self.dx_survey_model_footages = QStandardItemModel()
        self.ui.dx_survey_location_tableview.setModel(self.dx_survey_model_footages)
        self.ui.dx_survey_location_tableview.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Step 4: Initialize new survey line display model for interpolated points
        self.dx_survey_model_new_line = QStandardItemModel()
        self.ui.dx_survey_table_mod_new_md.setModel(self.dx_survey_model_new_line)
        self.ui.dx_survey_table_mod_new_md.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Step 5: Clear and initialize all survey parameter display fields
        self.ui.dx_survey_kop_line.setText("")  # Kick-off point depth
        self.ui.dx_survey_prod_line.setText("")  # Production zone depth
        self.ui.dx_survey_bhl_line.setText("")  # Bottom hole location depth
        self.ui.dx_survey_north_ref_line.setText("")  # North reference system
        self.ui.dx_survey_mag_dec_line.setText("")  # Magnetic declination
        self.ui.dx_survey_conv_angle_line.setText("")  # Convergence angle
        self.ui.dx_survey_pro_azi_line.setText("")  # Proposed azimuth
        # Make sure row selection is enabled
        # self.ui.dx_survey_table_mod.setSelectionBehavior(QTableView.SelectRows)
        # self.ui.dx_survey_table_mod.setSelectionMode(QTableView.SingleSelection)

        # Install event filter
        # self.ui.dx_survey_table_mod.installEventFilter(self)



    def set_clear_survey(self, data: Dict[str, Any]) -> None:
        """Update stored survey data with new clearance calculations.

        Allows dynamic updating of survey data without reinitializing the entire
        writer object. Used when survey processing parameters change or new
        data becomes available during real-time analysis.

        Args:
            data (Dict[str, Any]): Updated dictionary of survey objects with clearance data
        """
        self.surveys = data

    def set_spec_surveys(self, data: Dict[str, Any]) -> None:
        """Update stored special depth points data with new calculations.

        Updates the special depth points (KOP, Landing Point, BHL) when survey
        processing parameters change or trajectory calculations are reprocessed.
        Maintains synchronization between main survey data and critical points.

        Args:
            data (Dict[str, Any]): Updated dictionary of special depth points for each survey type
        """
        self.spec_surveys = data

    def survey_writer(self, ui: Any, survey_label: str) -> None:
        """Orchestrate complete survey data display for specified survey type.

        Coordinates the display of survey trajectory data, clearance footages, and
        significant depth information for a specific survey type (planned/as-drilled).
        Manages the complete workflow from data extraction to UI presentation.

        Args:
            ui (Any): PyQt5 user interface object for display components
            survey_label (str): Survey type identifier (e.g., "pln_df_true_dx", "drl_df_grid_dx")
        """
        # Step 1: Extract clearance data for the specified survey type
        survey = self.surveys[survey_label].clearance_data

        # Step 2: Identify corresponding special depth points data
        spec_id = survey_label[:6]  # Extract survey type prefix (e.g., "pln_df")
        spec_survey_found = self.spec_surveys[spec_id]
        spec_data = spec_survey_found[spec_survey_found['type'] == survey_label]

        # Step 3: Display complete survey trajectory in main table
        self.write_survey_to_table(survey, ui)

        # Step 4: Extract and process footage data for key depth points
        footage_lst = _isolate_footage_depths(survey, spec_data)

        # Step 5: Update UI line edits with significant depth values
        self.write_significant_depths_to_line_edits(ui, self.survey_parameters, footage_lst)

        # Step 6: Display clearance footages in dedicated table
        self.write_clearance_footages(footage_lst, ui)

    def write_survey_to_table(self, survey: pd.DataFrame, ui: Any) -> None:
        """Display complete survey trajectory data in main table view with formatting.

        Populates the main survey data table with trajectory points, clearance calculations,
        and coordinate information. Handles numerical formatting, precision control, and
        table appearance configuration for professional presentation.

        Args:
            survey (pd.DataFrame): Complete survey data with trajectory and clearance information
            ui (Any): PyQt5 user interface object containing the target table view
        """
        # Step 1: Clear coordinate display fields for fresh data presentation
        self.ui.shl_lat_easting.setText("")
        self.ui.shl_lon_northing.setText("")

        # Step 2: Reset table model and prepare for new data
        self.dx_survey_model.setRowCount(0)
        self.ui.dx_survey_table_mod.setModel(self.dx_survey_model)
        self.ui.dx_survey_table_mod.setUpdatesEnabled(False)  # Batch update for performance

        # Step 3: Clean survey data by removing internal tracking columns
        survey = survey.drop(columns=['point_index', 'feature'])

        # survey['ID'] = survey.index + 1  # +1 if you want to start from 1 instead of 0
        survey.insert(0, 'row', survey.index + 1)
        # Step 4: Convert angular measurements from radians to degrees for display
        for col in ['azimuth', 'inclination']:
            survey[col] = np.degrees(survey[col])

        # Step 5: Convert DataFrame to list format for table population
        data = survey.values.tolist()
        self.dx_survey_model.setRowCount(len(data))

        # Step 6: Populate table with formatted numerical data
        for row_idx, row in enumerate(data):
            for col_idx, value in enumerate(row):
                try:
                    # Step 6a: Analyze numerical precision for optimal display formatting
                    num_places_decimal = abs(decimal.Decimal(str(value)).as_tuple().exponent)
                    num_places_whole = len(str(int(value)))

                    # Step 6b: Apply precision control to prevent display overflow
                    if num_places_whole + num_places_decimal > 10:
                        if num_places_whole > 2:
                            value = round(value, 4)  # Round large numbers to 4 decimal places
                        else:
                            value = f'{value:.8g}'  # Use scientific notation for small numbers
                except (TypeError, decimal.InvalidOperation):
                    # Step 6c: Handle non-numeric values without modification
                    pass

                # Step 6d: Create table item and insert into model
                item = QStandardItem(str(value))
                self.dx_survey_model.setItem(row_idx, col_idx, item)

        # Step 7: Configure table headers and appearance
        columns = survey.columns.values
        self.dx_survey_model.setHorizontalHeaderLabels(columns)

        # Step 8: Set table view properties for professional appearance
        self.ui.dx_survey_table_mod.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_survey_table_mod.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_survey_table_mod.verticalHeader().setVisible(False)  # Hide row numbers
        self.ui.dx_survey_table_mod.setShowGrid(True)

        # Step 9: Enable table updates and refresh display
        self.ui.dx_survey_table_mod.setUpdatesEnabled(True)
        self.ui.dx_survey_table_mod.show()

        # Step 10: Display surface location coordinates in dedicated fields
        first_pt = survey.head(1)
        self.ui.shl_lat_easting.setText(str(first_pt['easting'].iloc[0]))
        self.ui.shl_lon_northing.setText(str(first_pt['northing'].iloc[0]))
        self.ui.dx_survey_table_mod.viewport().update()

    def write_new_survey_line_to_display(self, survey: pd.DataFrame, md: float,
                                         row_position: Optional[int] = None) -> None:
        """Display single interpolated survey point for new measured depth analysis.

        Shows calculated trajectory data for a user-specified measured depth point,
        useful for analyzing intermediate positions between actual survey stations.
        Provides detailed view of interpolated trajectory parameters.

        Args:
            survey (pd.DataFrame): Complete survey data for interpolation reference
            md (float): Target measured depth for interpolated point display
            row_position (Optional[int]): Optional table row position for insertion
        """
        # Step 1: Reset single-line display table
        self.dx_survey_model_new_line.setRowCount(0)
        self.ui.dx_survey_table_mod_new_md.setModel(self.dx_survey_model_new_line)
        self.ui.dx_survey_table_mod_new_md.setUpdatesEnabled(False)

        # Step 2: Extract data for the specified measured depth
        used_data = survey[survey['measured_depth'] == md]
        used_data = used_data.drop(columns=['point_index', 'feature'])

        # Step 3: Create table items with precision formatting
        items = [QStandardItem(str(item)) for item in used_data.iloc[0].tolist()]

        # Step 4: Apply numerical formatting to each data value
        for k, value in enumerate(used_data.iloc[0]):
            try:
                # Step 4a: Calculate precision requirements for display formatting
                num_places_decimal = abs(decimal.Decimal(str(value)).as_tuple().exponent)
                num_places_whole = len(str(int(value)))

                # Step 4b: Apply appropriate precision control
                if num_places_whole + num_places_decimal > 10:
                    if num_places_whole > 2:
                        value = round(value, 4)
                    else:
                        value = f'{value:.8g}'
            except (TypeError, decimal.InvalidOperation):
                # Step 4c: Handle non-numeric values without modification
                pass

            # Step 4d: Update item with formatted value
            items[k].setData(str(value))

        # Step 5: Add formatted row to display model
        self.dx_survey_model_new_line.appendRow(items)

        # Step 6: Configure headers and table appearance
        columns = used_data.columns.values
        self.dx_survey_model_new_line.setHorizontalHeaderLabels(columns)
        self.ui.dx_survey_table_mod_new_md.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_survey_table_mod_new_md.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_survey_table_mod_new_md.verticalHeader().setVisible(False)
        self.ui.dx_survey_table_mod_new_md.setShowGrid(True)

        # Step 7: Enable updates and display results
        self.ui.dx_survey_table_mod_new_md.setUpdatesEnabled(True)
        self.ui.dx_survey_table_mod_new_md.show()

    def write_significant_depths_to_line_edits(self, ui: Any, param: Dict[str, Any],
                                               footage_lst: pd.DataFrame) -> None:
        """Update UI line edits with critical depth points and survey parameters.

        Populates text fields with key trajectory information including KOP, production
        zone, BHL depths, and survey processing parameters. Provides quick reference
        display for engineering analysis and regulatory reporting.

        Args:
            ui (Any): PyQt5 user interface object containing line edit components
            param (Dict[str, Any]): Survey processing parameters including north reference and convergence
            footage_lst (pd.DataFrame): Footage data containing labeled depth points
        """
        # Step 1: Clear all parameter display fields for fresh data
        self.ui.dx_survey_kop_line.setText("")
        self.ui.dx_survey_prod_line.setText("")
        self.ui.dx_survey_bhl_line.setText("")
        self.ui.dx_survey_north_ref_line.setText("")
        self.ui.dx_survey_mag_dec_line.setText("")
        self.ui.dx_survey_conv_angle_line.setText("")
        self.ui.dx_survey_pro_azi_line.setText("")

        # Step 2: Setup ordered categories for depth point processing
        depths_str_lst = ['kop', 'prod', 'bhl']
        footage_lst['lbl'] = pd.Categorical(footage_lst['lbl'], categories=depths_str_lst, ordered=True)
        columns = footage_lst['lbl'].unique()

        # Step 3: Populate depth-specific line edits with measured depth values
        for i in columns:
            # Step 3a: Get corresponding UI line edit component
            used_line_edit = getattr(self.ui, f"dx_survey_{i}_line")

            # Step 3b: Extract measured depth value for the specific depth point
            md_val = footage_lst[footage_lst['lbl'] == i]['measured_depth'].iloc[0]
            used_line_edit.setText(str(md_val))

        # Step 4: Display survey processing parameters
        self.ui.dx_survey_north_ref_line.setText(param['north_ref'])  # North reference system
        self.ui.dx_survey_conv_angle_line.setText(str(round(param['conv_angle'], 4)))  # Convergence angle
        self.ui.dx_survey_pro_azi_line.setText(str(round(math.degrees(footage_lst['azimuth'].iloc[-1]), 3)))  # Final azimuth

    def write_clearance_footages(self, footage_lst: pd.DataFrame, ui: Any) -> None:
        """Display clearance footage measurements in dedicated table view.

        Presents clearance distances (FNL, FSL, FEL, FWL) for critical depth points
        in a formatted table for regulatory compliance and engineering analysis.
        Provides clear visualization of well positioning relative to plat boundaries.

        Args:
            footage_lst (pd.DataFrame): Footage data with clearance measurements for key depths
            ui (Any): PyQt5 user interface object containing footages table view
        """
        # Step 1: Remove non-footage columns for focused display
        footage_lst = footage_lst.drop(columns=['measured_depth', 'azimuth'])

        # Step 2: Setup table for batch data loading
        self.ui.dx_survey_location_tableview.setUpdatesEnabled(False)
        self.dx_survey_model_footages.setRowCount(0)
        self.ui.dx_survey_location_tableview.setModel(self.dx_survey_model_footages)

        # Step 3: Convert DataFrame to list format for table population
        data = footage_lst.values.tolist()
        self.dx_survey_model_footages.setRowCount(len(data))

        # Step 4: Populate table with formatted footage data
        for row_idx, row in enumerate(data):
            for col_idx, value in enumerate(row):
                if col_idx != 0:  # Skip label column for numerical formatting
                    # Step 4a: Round numerical values to 2 decimal places for footage display
                    item = QStandardItem(str(round(float(value), 2)))
                else:
                    # Step 4b: Display label column as-is
                    item = QStandardItem(str(value))
                self.dx_survey_model_footages.setItem(row_idx, col_idx, item)

        # Step 5: Configure table headers and appearance
        columns = footage_lst.columns.values
        self.dx_survey_model_footages.setHorizontalHeaderLabels(columns)
        self.ui.dx_survey_location_tableview.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_survey_location_tableview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_survey_location_tableview.verticalHeader().setVisible(False)
        self.ui.dx_survey_location_tableview.setShowGrid(True)

        # Step 6: Enable updates and display final results
        self.ui.dx_survey_location_tableview.setUpdatesEnabled(True)
        self.ui.dx_survey_location_tableview.show()
