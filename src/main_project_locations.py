"""Module for processing and retrieving township, range, and plat location data for oil and gas wells.

This module provides functionality to integrate well survey data with Public Land Survey System (PLSS)
plat information, handling spatial queries and geographic data processing for regulatory compliance
and engineering analysis in the oil and gas industry.
"""

import sqlite3
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
from typing import Tuple, Dict, Any, Union
import sys
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QDialogButtonBox, QLabel, QMessageBox, QTabWidget, QWidget,
    QGroupBox
)
from PyQt5.QtGui import QIntValidator, QDoubleValidator

def retrieve_sql_location_data(
        api: str,
        lateral: str,
        db: 'DatabaseManager'
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Retrieve well location data from APD database using API number and lateral designation.

    Implements a two-stage query strategy for robust data retrieval:
    1. Primary: Direct API pattern matching with lateral extension
    2. Fallback: APD number resolution through master table lookup

    The function returns complete PLSS (Public Land Survey System) location data
    including surface hole location (SHL) and bottom hole location (BHL) coordinates
    in state plane coordinate system.

    Args:
        api: API well number identifier following standard format (e.g., "05-123-45678")
        lateral: Lateral designation for multi-lateral wells (e.g., "H", "A", "B")
        db: Database connection manager instance with query_to_dataframe method

    Returns:
        Tuple containing:
            - loc_df: Complete location dataset with PLSS footages and state plane coordinates
            - shl: Surface location records filtered by zone_name = 'Surface Location'
            - bhl: Bottom hole location records filtered by zone_name = 'Proposed Depth'

    Note:
        API numbers follow Colorado Oil and Gas Conservation Commission (COGCC) format.
        Coordinate system is typically Colorado State Plane NAD83.
    """
    # Primary query using API pattern matching for direct lookup
    query = f"""select [Wh_Sec] as section, [Wh_Twpn] as township, [Wh_Twpd] as township_dir, [Wh_RngN] as rng, [Wh_RngD] as rng_dir,
     [Wh_Pm] as baseline, [Wh_FtNS] as fnsl, [Wh_Ns] as fnsl_dir, [Wh_FtEW] as fewl, [Wh_EW] as fewl_dir,
      [Zone_Name] as zone_name,[Wh_Qtr] as qtr_qtr,[Wh_X] as shl_x,[Wh_Y] as shl_y, [Bh_X] as bhl_x, [Bh_Y] as bhl_y
     from [dbo].[tblAPDLoc] where API LIKE '%{api}%' and API_EXT = '{lateral}'"""
    loc_df = db.query_to_dataframe(query)
    # Fallback strategy if primary query returns no results
    if loc_df.empty:
        # Resolve APD permit number from master table
        query = f"""SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = '{api}{lateral}'"""
        output = db.query_to_dataframe(query)['APDNo'].unique()[0]

        # Query location table using resolved APD number
        query = f"""select [Wh_Sec] as section, [Wh_Twpn] as township, [Wh_Twpd] as township_dir, [Wh_RngN] as rng, [Wh_RngD] as rng_dir,
         [Wh_Pm] as baseline, [Wh_FtNS] as fnsl, [Wh_Ns] as fnsl_dir, [Wh_FtEW] as fewl, [Wh_EW] as fewl_dir,
          [Zone_Name] as zone_name,[Wh_Qtr] as qtr_qtr,[Wh_X] as shl_x,[Wh_Y] as shl_y, [Bh_X] as bhl_x, [Bh_Y] as bhl_y
         from [dbo].[tblAPDLoc] where APDNO = {output}"""
        loc_df = db.query_to_dataframe(query)

    # Clean string data by removing leading/trailing whitespace
    loc_df = loc_df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

    # Filter by zone type for specialized location datasets
    shl = loc_df[loc_df['zone_name'] == 'Surface Location']  # Surface hole location
    bhl = loc_df[loc_df['zone_name'] == 'Proposed Depth']  # Bottom hole location at total depth

    return loc_df, shl, bhl


def find_plats_data(
        data: Union[Dict[str, Any], pd.DataFrame],
        conn_db: sqlite3.Connection
) -> pd.DataFrame:
    """Find PLSS plat boundaries intersecting with well survey trajectories.

    Implements efficient spatial analysis pipeline:
    1. Extract survey trajectory points from input data
    2. Calculate bounding box for spatial query optimization
    3. Query plat database using spatial filters
    4. Perform spatial joins to identify containing plats
    5. Transform results into polygon geometries with labels

    This function handles large plat databases efficiently through:
    - Bounding box pre-filtering to reduce query size
    - Two-stage filtering (bbox then concentration values)
    - Optimized spatial joins using GeoDataFrame operations

    Args:
        data: Survey trajectory data as either:
            - Dict containing survey objects with true_dx and grid_dx attributes
            - DataFrame with pre-processed trajectory points
        conn_db: SQLite connection to plat boundary database

    Returns:
        DataFrame containing plat polygons with:
            - geometry: Polygon objects representing plat boundaries
            - label: Human-readable township/range/section identifiers
            - centroid: Center points for label placement
            - Conc: Concentration codes for database joins

    Note:
        Plat data follows PLSS (Public Land Survey System) conventions.
        Concentration codes encode Township, Range, Section, and Principal Meridian.
    """

    def _process_input_data(data: Union[Dict[str, Any], pd.DataFrame]) -> pd.DataFrame:
        """Convert survey data to standardized DataFrame format.

        Internal function handling multiple input formats for flexibility.
        """
        if isinstance(data, dict):
            # Extract and combine trajectory data from survey objects
            combined = []
            for obj in data.values():
                combined.append(obj.true_dx)  # True vertical section data
                combined.append(obj.grid_dx)  # Grid-corrected coordinates
            # Deduplicate to optimize processing
            return pd.concat(combined, ignore_index=True).drop_duplicates(keep="first")
        elif isinstance(data, pd.DataFrame):
            return data
        return pd.DataFrame()

    def _read_base_data_by_bbox(
            conn: sqlite3.Connection,
            bbox: Tuple[float, float, float, float],
            buffer_dist: int = 1000
    ) -> pd.DataFrame:
        """Query plat data within buffered bounding box.

        Internal function for spatial pre-filtering to optimize database queries.
        Buffer ensures edge cases are captured.
        """
        query = f"""
            SELECT *
            FROM BaseData
            WHERE Easting >= {bbox[0] - buffer_dist}
              AND Easting <= {bbox[2] + buffer_dist}
              AND Northing >= {bbox[1] - buffer_dist}
              AND Northing <= {bbox[3] + buffer_dist}
        """
        return pd.read_sql(query, conn)

    def _read_base_data_by_conc(conn: sqlite3.Connection, conc_values: list) -> pd.DataFrame:
        """Query plat data by concentration values.

        Internal function for targeted data retrieval after initial filtering.
        """
        conc_str = ', '.join(f"'{c}'" for c in conc_values)
        query = f"SELECT * FROM BaseData WHERE Conc IN ({conc_str})"
        return pd.read_sql(query, conn)

    def _get_points_bbox(points_series: pd.Series) -> Tuple[float, float, float, float]:
        """Calculate bounding box from Shapely Point objects.

        Internal function extracting spatial extent for query optimization.
        """
        coords = [(pt.x, pt.y) for pt in points_series]
        x_coords, y_coords = zip(*coords)
        return min(x_coords), min(y_coords), max(x_coords), max(y_coords)

    def _geo_transform(df: pd.DataFrame) -> pd.DataFrame:
        """Transform coordinate points into labeled polygon geometries.

        Internal function handling:
        - Polygon creation from grouped coordinates
        - Human-readable label generation from concentration codes
        - Centroid calculation for label placement
        """
        # Create polygons from coordinate groups
        polygons = (df.groupby('Conc')
                    .apply(lambda x: Polygon(zip(x['Easting'], x['Northing'])))
                    .reset_index()
                    .rename(columns={0: 'geometry'}))

        # Generate township/range/section labels (e.g., "12 3N 68W 6")
        polygons['label'] = (polygons['Conc'].str[:2].astype(int).astype(str) + ' ' +
                             polygons['Conc'].str[2:4].astype(int).astype(str) + polygons['Conc'].str[4] + ' ' +
                             polygons['Conc'].str[5:7].astype(int).astype(str) + polygons['Conc'].str[7] + ' ' +
                             polygons['Conc'].str[-1])

        # Calculate centroids for label positioning
        polygons['centroid'] = polygons['geometry'].apply(lambda x: x.centroid)
        return polygons

    # Main processing pipeline
    # Process input survey data
    point_df = _process_input_data(data)

    # Calculate spatial extent and perform initial bbox query
    bbox = _get_points_bbox(point_df['shp_pt'])
    filtered_data = _read_base_data_by_bbox(conn_db, bbox)

    # Refine query using concentration values from initial results
    conc_vals = filtered_data['Conc'].unique()
    filtered_data = _read_base_data_by_conc(conn_db, conc_vals)
    # Transform to polygon geometries
    test_plat = _geo_transform(filtered_data)
    if not isinstance(test_plat, gpd.GeoDataFrame):
        test_plat_gdf = gpd.GeoDataFrame(test_plat, geometry='geometry')
    else:
        test_plat_gdf = test_plat

    # Create GeoDataFrame from survey points
    plat_gdf = gpd.GeoDataFrame(
        point_df,
        geometry=point_df['shp_pt'],
        crs=test_plat_gdf.crs
    )

    # Standardize CRS for spatial operations
    plat_gdf.crs = "EPSG:4326"  # WGS84 for compatibility
    test_plat_gdf.crs = "EPSG:4326"

    # Spatial join to find containing plats for each survey point
    joined = gpd.sjoin(
        plat_gdf,
        test_plat_gdf[['Conc', 'label', 'geometry']],
        how='inner',
        predicate='within'
    )

    # Final refinement using updated concentration list
    conc_vals = joined['Conc'].unique()
    filtered_data2 = _read_base_data_by_conc(conn_db, conc_vals)
    test_plat = _geo_transform(filtered_data2)

    return test_plat


def find_relative_data(
        conn_db: sqlite3.Connection,
        plat_df: pd.DataFrame
) -> pd.core.groupby.DataFrameGroupBy:
    """Retrieve coordinate transformation data for PLSS sections.

    Queries the section_relative table to obtain coordinate system transformation
    parameters for converting between different survey versions and datums.
    This is critical for accurate spatial analysis when combining historical
    and modern survey data.

    Args:
        conn_db: SQLite database connection containing section_relative table
        plat_df: DataFrame with plat data containing 'Conc' column

    Returns:
        DataFrameGroupBy object grouped by:
            - Conc: Concentration code (Township-Range-Section identifier)
            - Version: Survey version/datum identifier

    Note:
        Multiple versions may exist for the same section due to:
        - Historical resurveys
        - Datum shifts (NAD27 to NAD83)
        - Correction of surveying errors
    """
    # Extract unique concentration codes from plat data
    used_concs = tuple(plat_df['Conc'].unique().tolist())

    # Query all relative coordinate transformation data
    query = f"select * from section_relative"
    output = pd.read_sql(query, conn_db).drop_duplicates(keep="first")

    # Standardize concentration format (9-character PLSS identifier)
    output['Conc'] = output['Conc'].apply(lambda row: row[:9])

    # Filter to only sections present in plat data
    output = output[output['Conc'].isin(used_concs)]

    # Group by concentration and version for systematic processing
    grouped = output.groupby(['Conc', 'Version'])
    return grouped
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QDialogButtonBox, QLabel, QMessageBox
)
from PyQt5.QtGui import QIntValidator, QDoubleValidator

class ManualFootageInputDialog(QDialog):
    """
    Dialog for manual input of well footage data, returning the result
    as a pandas DataFrame. Includes an optional autofill for testing.
    """

    def __init__(self, parent=None, testing_enabled=False):
        super().__init__(parent)
        self.setWindowTitle("Manual Footage Data Entry")
        self.setModal(True)
        self.setFixedSize(450, 620)
        self.testing_enabled = testing_enabled

        # Sample data for the autofill feature
        self.sample_data = [
            {'section': 4, 'township': 3.0, 'township_dir': 'S', 'rng': 1.0, 'rng_dir': 'W', 'baseline': 'U', 'fnsl': 1054, 'fnsl_dir': 'FNL', 'fewl': 2304, 'fewl_dir': 'FEL', 'zone_name': 'Surface Location', 'qtr_qtr': 'LOT2', 'shl_x': 585048, 'shl_y': 4456625, 'bhl_x': 584548, 'bhl_y': 4460124},
            {'section': 33, 'township': 2.0, 'township_dir': 'S', 'rng': 1.0, 'rng_dir': 'W', 'baseline': 'U', 'fnsl': 100, 'fnsl_dir': 'FSL', 'fewl': 1490, 'fewl_dir': 'FWL', 'zone_name': 'Uppermost Producing', 'qtr_qtr': 'SESW', 'shl_x': 585048, 'shl_y': 4456625, 'bhl_x': 584548, 'bhl_y': 4460124},
            {'section': 28, 'township': 2.0, 'township_dir': 'S', 'rng': 1.0, 'rng_dir': 'W', 'baseline': 'U', 'fnsl': 100, 'fnsl_dir': 'FNL', 'fewl': 1490, 'fewl_dir': 'FWL', 'zone_name': 'Proposed Depth', 'qtr_qtr': 'NENW', 'shl_x': 585048, 'shl_y': 4456625, 'bhl_x': 584548, 'bhl_y': 4460124},
            {'section': 4, 'township': 3.0, 'township_dir': 'S', 'rng': 1.0, 'rng_dir': 'W', 'baseline': 'U', 'fnsl': 453, 'fnsl_dir': 'FNL', 'fewl': 1627, 'fewl_dir': 'FWL', 'zone_name': 'Kickoff Point', 'qtr_qtr': 'LOT3', 'shl_x': 585048, 'shl_y': 4456625, 'bhl_x': 584548, 'bhl_y': 4460124}
        ]

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        info_label = QLabel("Enter data in the tabs below. Common fields are at the bottom.")
        main_layout.addWidget(info_label)

        # Tab widget for row-specific data
        self.tab_widget = QTabWidget()
        self.tabs = []
        for i in range(4):
            tab = QWidget()
            form_layout = self._create_row_specific_layout(tab)
            tab.setLayout(form_layout)
            self.tab_widget.addTab(tab, f"Row {i + 1}")
            self.tabs.append(tab)
        main_layout.addWidget(self.tab_widget)

        # Common SHL/BHL coordinates
        common_group_box = QGroupBox("Common Surface and Bottom-Hole Locations")
        common_layout = QFormLayout()
        self.shl_x_edit = QLineEdit()
        self.shl_y_edit = QLineEdit()
        self.bhl_x_edit = QLineEdit()
        self.bhl_y_edit = QLineEdit()
        self.shl_x_edit.setValidator(QIntValidator())
        self.shl_y_edit.setValidator(QIntValidator())
        self.bhl_x_edit.setValidator(QIntValidator())
        self.bhl_y_edit.setValidator(QIntValidator())
        common_layout.addRow("SHL X:", self.shl_x_edit)
        common_layout.addRow("SHL Y:", self.shl_y_edit)
        common_layout.addRow("BHL X:", self.bhl_x_edit)
        common_layout.addRow("BHL Y:", self.bhl_y_edit)
        common_group_box.setLayout(common_layout)
        main_layout.addWidget(common_group_box)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)

        if self.testing_enabled:
            autofill_button = button_box.addButton("Test Autofill", QDialogButtonBox.ActionRole)
            autofill_button.clicked.connect(self._autofill_data)

        main_layout.addWidget(button_box)

    def _create_row_specific_layout(self, parent):
        form_layout = QFormLayout(parent)
        widgets = {}
        fields = {
            "section": {"widget": QLineEdit, "validator": QIntValidator(1, 36)},
            "township": {"widget": QLineEdit, "validator": QDoubleValidator(0.0, 100.0, 2)},
            "township_dir": {"widget": QComboBox, "items": ['N', 'S']},
            "rng": {"widget": QLineEdit, "validator": QDoubleValidator(0.0, 100.0, 2)},
            "rng_dir": {"widget": QComboBox, "items": ['E', 'W']},
            "baseline": {"widget": QLineEdit},
            "fnsl": {"widget": QLineEdit, "validator": QIntValidator(0, 9999)},
            "fnsl_dir": {"widget": QComboBox, "items": ['FNL', 'FSL']},
            "fewl": {"widget": QLineEdit, "validator": QIntValidator(0, 9999)},
            "fewl_dir": {"widget": QComboBox, "items": ['FEL', 'FWL']},
            "zone_name": {"widget": QLineEdit},
            "qtr_qtr": {"widget": QLineEdit},
        }
        for name, props in fields.items():
            widget_instance = props["widget"]()
            if "items" in props:
                widget_instance.addItems(props["items"])
            if "validator" in props:
                widget_instance.setValidator(props["validator"])
            form_layout.addRow(f"{name.replace('_', ' ').title()}:", widget_instance)
            widgets[name] = widget_instance
        parent.widgets = widgets
        return form_layout

    def _autofill_data(self):
        """Populates the form with sample data for testing."""
        first_row = self.sample_data[0]
        self.shl_x_edit.setText(str(first_row['shl_x']))
        self.shl_y_edit.setText(str(first_row['shl_y']))
        self.bhl_x_edit.setText(str(first_row['bhl_x']))
        self.bhl_y_edit.setText(str(first_row['bhl_y']))

        for i, tab in enumerate(self.tabs):
            if i < len(self.sample_data):
                data_row = self.sample_data[i]
                widgets = tab.widgets
                for key, value in data_row.items():
                    if key in widgets:
                        widget = widgets[key]
                        if isinstance(widget, QLineEdit):
                            widget.setText(str(value))
                        elif isinstance(widget, QComboBox):
                            index = widget.findText(str(value))
                            if index >= 0:
                                widget.setCurrentIndex(index)

    def _validate_and_accept(self):
        """Validate all fields and accept the dialog."""
        all_data = []
        common_fields = {
            "SHL X": self.shl_x_edit, "SHL Y": self.shl_y_edit,
            "BHL X": self.bhl_x_edit, "BHL Y": self.bhl_y_edit
        }
        for name, field in common_fields.items():
            if not field.text().strip():
                QMessageBox.warning(self, "Validation Error", f"Common field '{name}' is required.")
                field.setFocus()
                return

        for i, tab in enumerate(self.tabs):
            widgets = tab.widgets
            if not widgets["section"].text().strip():
                continue
            required_fields = {
                "Section": widgets["section"], "Township": widgets["township"],
                "Range": widgets["rng"], "FNSL": widgets["fnsl"],
                "FEWL": widgets["fewl"]
            }
            for name, field in required_fields.items():
                if not field.text().strip():
                    self.tab_widget.setCurrentIndex(i)
                    QMessageBox.warning(self, "Validation Error", f"'{name}' is required in Row {i + 1}.")
                    field.setFocus()
                    return
            all_data.append(self._get_tab_values(tab))

        if not all_data:
            QMessageBox.warning(self, "Validation Error", "At least one row must be filled out.")
            return

        self.final_data = all_data
        self.accept()

    def _get_tab_values(self, tab):
        """Extracts values and combines them with common coordinates."""
        widgets = tab.widgets
        row_data = {
            "section": int(widgets["section"].text()),
            "township": float(widgets["township"].text()),
            "township_dir": widgets["township_dir"].currentText(),
            "rng": float(widgets["rng"].text()),
            "rng_dir": widgets["rng_dir"].currentText(),
            "baseline": widgets["baseline"].text(),
            "fnsl": int(widgets["fnsl"].text()),
            "fnsl_dir": widgets["fnsl_dir"].currentText(),
            "fewl": int(widgets["fewl"].text()),
            "fewl_dir": widgets["fewl_dir"].currentText(),
            "zone_name": widgets["zone_name"].text(),
            "qtr_qtr": widgets["qtr_qtr"].text(),
        }
        row_data["shl_x"] = int(self.shl_x_edit.text())
        row_data["shl_y"] = int(self.shl_y_edit.text())
        row_data["bhl_x"] = int(self.bhl_x_edit.text())
        row_data["bhl_y"] = int(self.bhl_y_edit.text())
        return row_data

    def get_values(self):
        """
        Return the validated input values as a pandas DataFrame.
        """
        if hasattr(self, 'final_data') and self.final_data:
            return pd.DataFrame(self.final_data)
        return pd.DataFrame() # Return an empty DataFrame if no data

class TownShipAndRangeProcess:
    """Process and integrate township, range, and plat data for oil and gas well locations.

    This class serves as the primary interface for combining:
    - Well survey trajectory data (directional drilling paths)
    - Regulatory location data (APD permits and surface/bottom hole locations)
    - PLSS plat boundaries (legal land descriptions)

    The integration supports:
    - Regulatory compliance verification
    - Spatial analysis for drilling operations
    - Visualization of well paths relative to legal boundaries
    - Anti-collision analysis with offset wells

    Attributes:
        plat_df: Processed plat boundary data with geometries and labels
        loc_df: Complete location dataset from regulatory database
    """

    def __init__(
            self,
            api: str,
            lateral: str,
            db_process: 'DatabaseManager',
            survey_dict: Dict[str, Any],
            location_db: sqlite3.Connection
    ) -> None:
        """Initialize township and range processor for a specific well.

        Coordinates data retrieval from multiple sources:
        1. Regulatory database (APD permits, well locations)
        2. Survey trajectory data (actual/planned well paths)
        3. PLSS plat database (legal land boundaries)

        Args:
            api: API well number following COGCC format
            lateral: Lateral designation for multi-lateral wells
            db_process: Database manager for regulatory data access
            survey_dict: Dictionary containing processed survey objects with
                true_dx and grid_dx trajectory data
            location_db: SQLite connection to PLSS plat boundary database

        Note:
            The class assumes Colorado State Plane coordinate system
            for consistency with COGCC regulatory requirements.
        """
        # Retrieve regulatory location data from APD database
        try:
            loc_df, shl, bhl = retrieve_sql_location_data(api, lateral, db_process)

        except Exception as e:
            loc_df = self.run_dialog_example()
            shl = loc_df[['shl_x', 'shl_y']].iloc[0].tolist()
            bhl = loc_df[['bhl_x', 'bhl_y']].iloc[0].tolist()

        # Find plat boundaries intersecting with survey trajectory
        plat_df = find_plats_data(data=survey_dict, conn_db=location_db)

        # Store processed data for access by visualization and analysis methods
        self.plat_df = plat_df
        self.loc_df = loc_df

    def run_dialog_example(self):
        """
        Function to demonstrate how to create and use the
        ManualFootageInputDialog.
        """
        # In a real application, the parent would be your main window
        dialog = ManualFootageInputDialog(testing_enabled=True)

        if dialog.exec_() == QDialog.Accepted:
            footage_df = dialog.get_values()
            print("\n✅ Manual input received. Data returned as a pandas DataFrame:\n")
            return footage_df
        else:
            print("\n❌ Operation Cancelled: Manual data entry was cancelled.")