"""Oil and gas engineering tools for directional survey processing and wellbore clearance analysis.

This module provides a comprehensive GUI application for managing directional survey data,
calculating wellbore clearances, and visualizing well paths in both 2D and 3D. It integrates
with Utah's oil and gas database to retrieve well information and process survey data.

Key Features:
    - Directional survey import and processing (planned and as-drilled)
    - Wellbore clearance calculations against plat boundaries
    - Township and range section coordinate processing
    - 2D and 3D visualization of well paths
    - Database integration for well data retrieval
    - Survey interpolation and manipulation tools
"""

import traceback
from functools import partial
import sqlite3
from typing import Tuple, Any

import utm
from pyproj import Geod, Proj, CRS
import os
import pandas as pd
import numpy as np
import copy
from PyQt5.QtCore import QTimer, QSignalBlocker
import time
import sys
import weakref
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLineEdit, QSpinBox,
                             QCheckBox, QDialog, QTabWidget, QTextBrowser, QTableWidget, QLabel, QTableView,
                             QRadioButton, QGraphicsView, QComboBox, QMessageBox, QFileDialog, QButtonGroup,
                             QTextEdit, QPlainTextEdit, QDoubleSpinBox, QListWidget, QDateEdit, QTimeEdit,
                             QDateTimeEdit, QTreeWidget, QFormLayout, QHBoxLayout, QDialogButtonBox)
from PyQt5.QtCore import QRegExp, QObject, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QDoubleValidator, QRegExpValidator, QStandardItemModel, QStandardItem
from src.EToolsLimited import Ui_Dialog
import matplotlib.pyplot as plt
import math
import sqlalchemy
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
from main_project_plat_coord_editor import PlatCoordEditor
from main_project_plat_editor_process import SetupRelativeCoordsPage
from shapely.geometry import Point, LineString, MultiPoint, Polygon
from main_project_plat_editor_process import convert_to_pts
import main_project_drawer
import sys
import io
from PyQt5 import QtCore, QtWidgets, QtGui
from file_helper import get_plss_sections_path
import datetime


# sys.path.append(os.path.dirname(__file__))

def _get_data_from_qtableview(table_view: QTableView) -> list[list[str]] | None:
    """Extract data from a QTableView using the data() method for improved performance.

    This function retrieves all cell data from a QTableView by directly accessing
    the model's data() method, which is slightly faster than using item().text()
    for large tables.

    Args:
        table_view: The QTableView widget containing the data to extract.

    Returns:
        A 2D list where each inner list represents a row of cell values as strings.
        Returns None if the table_view doesn't have a QStandardItemModel.

    """
    model = table_view.model()
    if not isinstance(model, QStandardItemModel):
        return None

    rows = model.rowCount()
    columns = model.columnCount()

    return [[model.data(model.index(row, col)) or ""
             for col in range(columns)]
            for row in range(rows)]


def get_resource_path(relative_path):
    """Get the absolute path to a resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # If not running as executable, use the current directory
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class ConsoleRedirector(QtCore.QObject):
    """
    Console output redirector that safely handles encoding issues
    while grouping messages with timestamps at specified intervals.
    """
    # Signal for thread-safe UI updates
    text_signal = QtCore.pyqtSignal(str, str, bool)  # text, stream_type, is_new_group

    def __init__(self, text_browser, original_stream, stream_name, timestamp_interval=2.0):
        super().__init__()

        # Store configuration
        self.text_browser = text_browser
        self.original_stream = original_stream
        self.stream_name = stream_name
        self.timestamp_interval = timestamp_interval

        # Timestamp tracking
        self.last_timestamp = 0
        self.line_buffer = ""

        # Connect signal
        self.text_signal.connect(self.update_text_browser)

    def write(self, text):
        # Write to original stream with encoding error handling
        try:
            self.original_stream.write(text)
        except UnicodeEncodeError:
            # If there's an encoding error, use a replacement character
            # or skip problematic characters
            try:
                # Try writing with 'replace' error handling
                self.original_stream.write(text.encode(self.original_stream.encoding,
                                                       errors='replace').decode(self.original_stream.encoding))
            except (UnicodeError, AttributeError, IOError):
                # If that still doesn't work, try a fallback approach
                try:
                    # Try ASCII with replacement characters
                    self.original_stream.write(text.encode('ascii', errors='replace').decode('ascii'))
                except:
                    # Last resort: just skip writing to the original stream
                    pass

        # Add to buffer and process if we have complete lines
        self.line_buffer += text
        if '\n' in self.line_buffer:
            self._process_buffer()

    def _process_buffer(self):
        """Process all complete lines in the buffer."""
        # Split by newlines, keeping incomplete lines in buffer
        lines = self.line_buffer.split('\n')
        self.line_buffer = lines.pop() if lines[-1] != '' else ""

        # Process each complete line
        for line in lines:
            # Determine if we need a new timestamp group
            current_time = time.time()
            is_new_group = (current_time - self.last_timestamp) >= self.timestamp_interval

            # Update timestamp if starting a new group
            if is_new_group:
                self.last_timestamp = current_time

            # Send to text browser via signal
            self.text_signal.emit(line, self.stream_name, is_new_group)

    def flush(self):
        """Process any remaining text in the buffer and flush the stream."""
        if self.line_buffer:
            # Check if we need a new timestamp
            current_time = time.time()
            is_new_group = (current_time - self.last_timestamp) >= self.timestamp_interval

            if is_new_group:
                self.last_timestamp = current_time

            # Process the remaining text
            self.text_signal.emit(self.line_buffer, self.stream_name, is_new_group)
            self.line_buffer = ""

        # Safe flush
        try:
            self.original_stream.flush()
        except:
            pass

    def update_text_browser(self, text, stream_type, is_new_group):
        """Update the text browser with formatted text."""
        # Set text colors based on stream type
        if stream_type == "stderr":
            color = QtGui.QColor(207, 0, 0)  # Red for errors
            font = self.text_browser.font()
            font.setBold(True)
        else:
            color = QtGui.QColor(0, 0, 0)  # Black for standard output
            font = self.text_browser.font()
            font.setBold(False)

        # Get cursor for editing
        cursor = self.text_browser.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)

        # Insert timestamp if this is a new group
        if is_new_group:
            # Add a little spacing between groups
            cursor.insertBlock()

            # Insert timestamp with gray color
            timestamp_format = QtGui.QTextCharFormat()
            timestamp_format.setForeground(QtGui.QColor(100, 100, 100))
            timestamp_format.setFontWeight(QtGui.QFont.Bold)

            timestamp = datetime.datetime.now().strftime('[%H:%M:%S]')
            cursor.insertText(timestamp, timestamp_format)
            cursor.insertBlock()

        # Insert the actual text with appropriate color
        text_format = QtGui.QTextCharFormat()
        text_format.setForeground(color)
        text_format.setFont(font)

        # Preserve indentation
        if text.startswith(' '):
            leading_spaces = len(text) - len(text.lstrip(' '))
            indent = ' ' * leading_spaces
            text = text[leading_spaces:]
            cursor.insertText(indent, text_format)

        cursor.insertText(text, text_format)
        cursor.insertBlock()  # Add a newline

        # Update the cursor in the text browser
        self.text_browser.setTextCursor(cursor)

        # Ensure visible
        self.text_browser.ensureCursorVisible()


def setup_console_redirection(text_browser, timestamp_interval=2.0):
    """
    Sets up redirection of stdout and stderr to the specified text browser with time-grouped timestamps.

    Args:
        text_browser: The QTextBrowser widget to display console output
        timestamp_interval: Minimum seconds between timestamps (default: 2.0)

    Returns:
        Tuple of (original_stdout, original_stderr) for restoring later
    """
    # Configure text browser for best display
    text_browser.setReadOnly(True)
    text_browser.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)  # Allow horizontal scrolling

    # Set a monospace font for code-like appearance
    font = QtGui.QFont("Consolas, Monaco, 'Courier New', monospace", 9)
    text_browser.setFont(font)

    # Save original streams
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    # Create redirectors
    stdout_redirector = ConsoleRedirector(
        text_browser,
        original_stdout,
        "stdout",
        timestamp_interval
    )

    stderr_redirector = ConsoleRedirector(
        text_browser,
        original_stderr,
        "stderr",
        timestamp_interval
    )

    # Replace standard streams
    sys.stdout = stdout_redirector
    sys.stderr = stderr_redirector

    return original_stdout, original_stderr


def restore_console(original_stdout, original_stderr):
    """Restores the original console streams."""
    # Flush any remaining content
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except:
        pass

    # Restore original streams
    sys.stdout = original_stdout
    sys.stderr = original_stderr


class LateralNameDialog(QDialog):
    """
    A dialog to prompt the user for a valid 4-digit lateral name.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lateral Name Required")
        self.setModal(True)
        self.setFixedSize(350, 150)

        # To store the validated name
        self.lateral_name = None

        self._setup_ui()

    def _setup_ui(self):
        """Initializes the user interface components."""
        main_layout = QVBoxLayout(self)

        info_label = QLabel(
            "A 4-digit numeric lateral name is required.\nPlease enter it below."
        )
        info_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        main_layout.addWidget(info_label)

        form_layout = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., 0000")
        # Set max length for user convenience and input mask for digits
        self.name_edit.setMaxLength(4)
        self.name_edit.setInputMask("9999")  # Restricts input to digits
        self.name_edit.setText('0000')
        form_layout.addRow("Lateral Name:", self.name_edit)
        main_layout.addLayout(form_layout)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _validate_and_accept(self):
        """Validates that the input is a 4-digit string."""
        text = self.name_edit.text().strip()

        if len(text) != 4 or not text.isdigit():
            QMessageBox.warning(
                self, "Validation Error", "Lateral name must be exactly 4 digits."
            )
            self.name_edit.setFocus()
            return

        # If validation passes, store the value and accept the dialog
        self.lateral_name = text
        self.accept()

    def get_value(self):
        """Returns the validated 4-digit lateral name."""
        return self.lateral_name


class ManualDataInputDialog(QDialog):
    """
    Dialog for manual input of well elevation and north reference when database query fails
    or returns empty values.
    """

    def __init__(self, current_elevation=None, current_north_ref=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manual Data Entry Required")
        self.setFixedSize(350, 180)
        self.setModal(True)

        # Store current values for pre-population
        self.current_elevation = str(current_elevation) if current_elevation else ""
        self.current_north_ref = str(current_north_ref) if current_north_ref else ""

        self._setup_ui()
        self._setup_validators()
        self._populate_current_values()

    def _setup_ui(self):
        """Initialize the user interface components"""
        main_layout = QVBoxLayout(self)

        # Add informational label
        info_label = QLabel("Database query returned empty values. Please enter the required data manually:")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #2c3e50; font-weight: bold; margin-bottom: 10px;")
        main_layout.addWidget(info_label)

        # Create form layout
        form_layout = QFormLayout()

        # Well elevation input
        self.elevation_edit = QLineEdit()
        self.elevation_edit.setPlaceholderText("Enter well elevation (feet)")
        form_layout.addRow("Well Elevation:", self.elevation_edit)

        # North reference input (dropdown)
        self.north_ref_combo = QComboBox()
        self.north_ref_combo.addItems(['t', 'g', 'true', 'grid'])
        self.north_ref_combo.setEditable(True)  # Allow custom input
        form_layout.addRow("North Reference:", self.north_ref_combo)

        main_layout.addLayout(form_layout)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _setup_validators(self):
        """Configure input validators for data integrity"""
        # Elevation should be a positive or negative number (altitude can be below sea level)
        elevation_validator = QDoubleValidator(-1000.0, 10000.0, 2)
        self.elevation_edit.setValidator(elevation_validator)

    def _populate_current_values(self):
        """Pre-populate fields with current values if available"""
        if self.current_elevation:
            self.elevation_edit.setText(self.current_elevation)

        if self.current_north_ref:
            # Find matching combo box item or set as custom text
            index = self.north_ref_combo.findText(self.current_north_ref.lower())
            if index >= 0:
                self.north_ref_combo.setCurrentIndex(index)
            else:
                self.north_ref_combo.setEditText(self.current_north_ref)

    def _validate_and_accept(self):
        """Validate inputs before accepting the dialog"""
        elevation_text = self.elevation_edit.text().strip()
        north_ref_text = self.north_ref_combo.currentText().strip()

        # Validation checks
        if not elevation_text:
            QMessageBox.warning(self, "Validation Error",
                                "Well elevation is required and cannot be empty.")
            self.elevation_edit.setFocus()
            return

        if not north_ref_text:
            QMessageBox.warning(self, "Validation Error",
                                "North reference is required and cannot be empty.")
            self.north_ref_combo.setFocus()
            return

        try:
            # Validate elevation is a valid number
            float(elevation_text)
        except ValueError:
            QMessageBox.warning(self, "Validation Error",
                                "Well elevation must be a valid number.")
            self.elevation_edit.setFocus()
            return

        # Validate north reference format
        valid_north_refs = ['t', 'g', 'true', 'grid']
        if north_ref_text.lower() not in valid_north_refs:
            QMessageBox.warning(self, "Validation Error",
                                f"North reference must be one of: {', '.join(valid_north_refs)}")
            self.north_ref_combo.setFocus()
            return

        # All validations passed
        self.accept()

    def get_values(self):
        """Return the validated input values"""
        elevation = float(self.elevation_edit.text().strip())
        north_ref = self.north_ref_combo.currentText().strip().lower()
        return elevation, north_ref


class UltraFastClearer:
    """High-performance widget clearing utility optimized for forms with hundreds of widgets.

    This class provides efficient batch clearing of various Qt widget types to reset
    form data. It pre-categorizes widgets by type for faster clearing operations and
    implements debouncing to prevent rapid consecutive clear operations.

    Attributes:
        dialog: The parent dialog containing widgets to clear.
        trigger_textbox: The QLineEdit that triggers clearing when text changes.
        clear_timer: QTimer for debouncing clear operations.
    """

    def __init__(self, dialog: QDialog, trigger_textbox: QLineEdit) -> None:
        """Initialize the UltraFastClearer with a dialog and trigger textbox.

        Args:
            dialog: Parent dialog containing widgets to clear.
            trigger_textbox: QLineEdit that won't be cleared and serves as trigger.
        """
        self.dialog = dialog
        self.trigger_textbox = trigger_textbox
        self.line_edits = []
        self.combo_boxes = []
        self.check_boxes = []
        self.radio_buttons = []
        self.spin_boxes = []
        self.tables = []
        self.q_table_views = []

        # Pre-sort widgets by type for faster clearing
        self._categorize_widgets()

        # Connect trigger with debouncing
        self.clear_timer = QTimer()
        self.clear_timer.timeout.connect(self.execute_clear)
        self.clear_timer.setSingleShot(True)

    def _categorize_widgets(self) -> None:
        """Pre-sort all child widgets by type for efficient batch operations.

        This method iterates through all widgets in the dialog and categorizes them
        into lists based on their type. This pre-sorting allows for much faster
        batch clearing operations compared to checking widget types during clearing.

        Note:
            The trigger_textbox is explicitly excluded from clearing operations.
        """
        for widget in self.dialog.findChildren(QWidget):
            if widget == self.trigger_textbox:
                continue

            if isinstance(widget, QLineEdit):
                self.line_edits.append(widget)
            elif isinstance(widget, QComboBox):
                self.combo_boxes.append(widget)
            elif isinstance(widget, QCheckBox):
                self.check_boxes.append(widget)
            elif isinstance(widget, QRadioButton):
                self.radio_buttons.append(widget)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                self.spin_boxes.append(widget)
            elif isinstance(widget, QTableWidget):
                self.tables.append(widget)
            elif isinstance(widget, QTableView):
                self.q_table_views.append(widget)

    def _on_text_changed(self, text: str) -> None:
        """Handle text change events with debouncing to avoid rapid clears.

        Args:
            text: The new text value (used to determine if clearing should occur).
        """
        if text:
            self.clear_timer.stop()
            self.clear_timer.start(50)  # 50ms debounce

    def execute_clear(self) -> None:
        """Execute batch clearing operations on all categorized widgets.

        This method performs optimized batch clearing of all widgets based on their
        type. Operations are ordered from fastest (QLineEdits) to slowest (Tables)
        for optimal performance. Special handling ensures that certain tables
        (like label and coordinate tables) are preserved.
        """

        # Batch clear QLineEdits (fastest operation)
        for widget in self.line_edits:
            widget.clear()

        # Batch clear ComboBoxes
        for widget in self.combo_boxes:
            widget.setCurrentIndex(-1)

        # Batch clear CheckBoxes
        for widget in self.check_boxes:
            widget.setChecked(False)

        # Batch clear RadioButtons
        for widget in self.radio_buttons:
            widget.setChecked(False)

        # Batch clear SpinBoxes
        for widget in self.spin_boxes:
            widget.setValue(widget.minimum())

        # Clear tables (more expensive operation)
        for widget in self.tables:
            name = widget.objectName()
            # Preserve special tables that shouldn't be cleared
            if 'labels' not in name and 'plat_table_coords_' not in name:
                widget.clearContents()

        for widget in self.q_table_views:
            model = widget.model()
            if isinstance(model, QStandardItemModel):
                model.clear()


class SingleInputDialog(QDialog):
    """Simple dialog for collecting a single input value from the user.

    This dialog provides a clean interface for requesting one value with
    customizable title, label, and placeholder text. It includes standard
    OK/Cancel buttons and supports input validation.

    """

    def __init__(self, title: str = "Input", label: str = "Value:",
                 placeholder: str = "Enter value", parent: QWidget = None) -> None:
        """Initialize the single input dialog.

        Args:
            title: Window title for the dialog.
            label: Label text displayed next to the input field.
            placeholder: Placeholder text shown in the empty input field.
            parent: Parent widget for the dialog.
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(250, 120)

        # Create form layout for label and line edit
        form_layout = QFormLayout()

        # Create line edit
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText(placeholder)

        # Add field to form layout
        form_layout.addRow(label, self.value_edit)

        # Add standard buttons (OK and Cancel)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # Create main layout and add the form layout and button box
        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(button_box)

    def get_value(self) -> str:
        """Return the value entered by the user.

        Returns:
            The text content of the input field as a string.
        """
        return self.value_edit.text()

    def set_validator(self, validator: QDoubleValidator | QRegExpValidator) -> None:
        """Set a validator for the input field to restrict input.

        Args:
            validator: Qt validator object to apply to the input field.
        """
        self.value_edit.setValidator(validator)


class InputDialog(QDialog):
    """Dialog for collecting directional survey point data (MD, inclination, azimuth).

    This specialized dialog provides validated input fields for adding new survey
    points to a directional survey. Each field has appropriate validators and
    range restrictions based on industry standards.

    Field Ranges:
        - Measured Depth: Positive numbers only
        - Inclination: -180 to +180 degrees
        - Azimuth: 0 to 360 degrees
    """

    def __init__(self, parent: QWidget = None) -> None:
        """Initialize the survey point input dialog with validated fields."""
        super().__init__(parent)
        self.setWindowTitle("Add Survey Point")
        self.resize(300, 200)

        # Create form layout for labels and line edits
        form_layout = QFormLayout()

        # Create line edits with validators
        self.measured_depth_edit = QLineEdit()
        self.inclination_edit = QLineEdit()
        self.azimuth_edit = QLineEdit()

        # Set validators
        # Positive numbers only for measured depth
        positive_validator = QRegExpValidator(QRegExp(r"[0-9]*\.?[0-9]+"))
        self.measured_depth_edit.setValidator(positive_validator)

        # -180 to +180 for inclination
        inclination_validator = QDoubleValidator(-180.0, 180.0, 5)
        self.inclination_edit.setValidator(inclination_validator)

        # 0 to 360 for azimuth
        azimuth_validator = QDoubleValidator(0.0, 360.0, 5)
        self.azimuth_edit.setValidator(azimuth_validator)

        # Add placeholder text
        self.measured_depth_edit.setPlaceholderText("Positive number")
        self.inclination_edit.setPlaceholderText("Range: -180 to 180")
        self.azimuth_edit.setPlaceholderText("Range: 0 to 360")

        # Add fields to form layout
        form_layout.addRow("Measured Depth:", self.measured_depth_edit)
        form_layout.addRow("Inclination:", self.inclination_edit)
        form_layout.addRow("Azimuth:", self.azimuth_edit)

        # Add standard buttons (OK and Cancel)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)

        # Create main layout and add the form layout and button box
        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(button_box)

    def validate_and_accept(self) -> None:
        """Validate all inputs before accepting the dialog.

        This method performs comprehensive validation including:
        - Ensuring all fields have values
        - Checking value ranges against industry standards
        - Converting and validating numeric inputs

        If validation fails, appropriate warning messages are shown to the user.
        """
        try:
            # Check if all fields have values
            if not self.measured_depth_edit.text() or not self.inclination_edit.text() or not self.azimuth_edit.text():
                QMessageBox.warning(self, "Validation Error", "All fields must be filled.")
                return

            # Parse values
            measured_depth = float(self.measured_depth_edit.text())
            inclination = float(self.inclination_edit.text())
            azimuth = float(self.azimuth_edit.text())

            # Additional validation
            if measured_depth <= 0:
                QMessageBox.warning(self, "Validation Error", "Measured Depth must be positive.")
                return

            if inclination < -180 or inclination > 180:
                QMessageBox.warning(self, "Validation Error", "Inclination must be between -180 and 180.")
                return

            if azimuth < 0 or azimuth > 360:
                QMessageBox.warning(self, "Validation Error", "Azimuth must be between 0 and 360.")
                return

            # If all validations pass, accept the dialog
            self.accept()

        except ValueError:
            QMessageBox.warning(self, "Validation Error", "All values must be valid numbers.")

    def get_inputs(self) -> dict[str, float]:
        """Return the validated survey point values entered by the user.

        Returns:
            Dictionary containing:
                - measured_depth: Float value of measured depth
                - inclination: Float value of inclination in degrees
                - azimuth: Float value of azimuth in degrees
        """
        return {
            "measured_depth": float(self.measured_depth_edit.text()),
            "inclination": float(self.inclination_edit.text()),
            "azimuth": float(self.azimuth_edit.text())
        }


class DatabaseManager:
    """Manages database connections and operations for the oil and gas data system.

    This class provides a high-level interface for database operations including
    connection management, session handling, and various query execution methods.
    It uses SQLAlchemy for ORM operations and supports both raw SQL and pandas
    DataFrame integration.

    Attributes:
        connector: SQLConnector instance for database connection management.
        engine: SQLAlchemy engine for database operations.
        Session: Session factory for creating database sessions.
    """

    def __init__(self) -> None:
        """Initialize the database manager with connection and session factory."""
        # Initialize the connection
        file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logininfo.txt")

        self.connector = SQLConnector(login_file=file_path)
        self.engine = self.connector.get_engine()

        # Create a session factory
        self.Session = sessionmaker(bind=self.engine)

    @contextmanager
    def get_session(self):
        """Context manager for database sessions with automatic commit/rollback.

        This ensures proper session cleanup and automatic transaction handling.
        Sessions are automatically committed on success or rolled back on error.

        Yields:
            SQLAlchemy session object for database operations.

        """
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def execute_raw_query(self, query: str, params: dict = None) -> list:
        """Execute a raw SQL query with optional parameters.

        Args:
            query: SQL query string with optional parameter placeholders.
            params: Dictionary of parameter values for the query.

        Returns:
            List of result rows from the query execution.

        """
        with self.engine.connect() as connection:
            result = connection.execute(query, params or {})
            return result.fetchall()

    def query_to_dataframe(self, query: str) -> pd.DataFrame:
        """Execute a SQL query and return results as a pandas DataFrame.

        Args:
            query: SQL query string to execute.

        Returns:
            pandas DataFrame containing the query results.

        """
        return pd.read_sql_query(query, self.engine)

    def get_well_data(self, well_id: str) -> list:
        """Retrieve well data for a specific well ID.

        Args:
            well_id: The unique identifier for the well.

        Returns:
            List of records matching the well ID.
        """
        query = """
        SELECT *
        FROM Wells
        WHERE WellID = :well_id
        """
        return self.execute_raw_query(query, {'well_id': well_id})


class SQLConnector:
    """Handles SQL Server database connections with credential management.

    This class manages database connection strings, credential parsing, and
    SQLAlchemy engine creation. It supports both production connections with
    credentials and local trusted connections as a fallback.

    Attributes:
        login_file: Path to the file containing database credentials.
        logger: Logger instance for error reporting.
        engine: SQLAlchemy engine instance for database operations.
    """

    def __init__(self, login_file: str = "logininfo.txt") -> None:
        """Initialize SQL connector with credential file path.

        Args:
            login_file: Name of the file containing login credentials.
        """
        self.login_file = login_file
        self.logger = logging.getLogger(__name__)
        self.engine = self._create_sql_connection()

    def _parse_credentials(self, content: str) -> dict[str, str] | None:
        """Parse username and password from credential file content.

        Expected file format:
            user=username
            password=password

        Args:
            content: Raw content from the credentials file.

        Returns:
            Dictionary with 'user' and 'password' keys, or None if parsing fails.
        """
        try:
            lines = content.strip().split('\n')
            return {
                'user': lines[0].split('=')[1].strip(),
                'password': lines[1].split('=')[1].strip()
            }
        except (IndexError, KeyError) as e:
            self.logger.error(f"Error parsing credentials: {e}")
            return None

    def _get_credentials(self) -> dict[str, str] | None:
        """Read and parse credentials from the configured file.

        Returns:
            Dictionary containing database credentials, or None if file not found.
        """
        try:
            file_path = os.path.join(os.getcwd(), self.login_file)
            with open(file_path, 'r') as file:
                content = file.read()
            return self._parse_credentials(content)
        except FileNotFoundError:
            self.logger.warning(f"Credentials file not found: {self.login_file}")
            return None

    @lru_cache(maxsize=1)
    def _create_connection_string(self) -> str:
        """Create SQL Server connection string with caching for performance.

        This method attempts to create a production connection string using
        credentials from the login file. If credentials are not available,
        it falls back to a local trusted connection.

        Returns:
            URL-encoded connection string for SQLAlchemy.
        """
        credentials = self._get_credentials()

        if credentials:
            # Production connection to Utah Oil & Gas database
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

    def _create_sql_connection(self) -> sqlalchemy.engine.Engine:
        """Create and configure SQLAlchemy engine for database operations.

        Returns:
            Configured SQLAlchemy engine with connection pooling.

        Raises:
            Exception: If engine creation fails.
        """
        try:
            connection_string = self._create_connection_string()
            return create_engine(
                f"mssql+pyodbc:///?odbc_connect={connection_string}",
                pool_pre_ping=True,  # Verify connections before use
                pool_recycle=3600  # Recycle connections after 1 hour
            )
        except Exception as e:
            self.logger.error(f"Failed to create SQL connection: {e}")
            raise

    def get_engine(self) -> sqlalchemy.engine.Engine:
        """Return the SQLAlchemy engine instance.

        Returns:
            SQLAlchemy engine for database operations.
        """
        return self.engine


def _get_convergence(lat: float, lon: float, from_crs: str = 'EPSG:32043') -> float:
    """Calculate the meridian convergence angle for a given latitude/longitude coordinate.

    This function computes the meridian convergence (the angular difference between
    grid north and true north) at a specified location using the State Plane
    Coordinate System. This is critical for accurate directional survey calculations
    when converting between true north and grid north references.

    Args:
        lat: Latitude coordinate in decimal degrees.
        lon: Longitude coordinate in decimal degrees.
        from_crs: EPSG code for the coordinate reference system. Defaults to
            'EPSG:32043' (Utah Central Zone State Plane).

    Returns:
        float: Meridian convergence angle in degrees.
            Positive values indicate convergence east of true north.
            Negative values indicate convergence west of true north.

    Notes:
        - The function uses the Utah Central Zone State Plane by default, which is
          appropriate for central Utah locations.
        - For locations outside Utah Central Zone, specify the appropriate EPSG code.
        - Convergence angle is essential for converting between magnetic, true, and
          grid north references in directional drilling operations.
    """
    # Initialize the Coordinate Reference System using the specified EPSG code
    crs_spcs = CRS(from_crs)

    # Create a projection object for coordinate transformation and calculations
    p = Proj(crs_spcs)

    # Calculate meridian convergence using projection factors
    # Parameters: (longitude, latitude, radians=False, return_convergence=True)
    declination = p.get_factors(lon, lat, False, True).meridian_convergence
    return declination


def calculate_convergence_angle(latitude: float, longitude: float) -> float:
    """Calculate the convergence angle between grid north and true north using UTM projection.

    This alternative method calculates convergence angle based on UTM zone parameters.
    It's useful when working with UTM coordinates or when State Plane convergence
    is not available.

    Args:
        latitude: Latitude in decimal degrees.
        longitude: Longitude in decimal degrees.

    Returns:
        Convergence angle in degrees between grid north and true north.

    Notes:
        - This method uses a simplified formula based on the sine of latitude
          and the difference from the central meridian.
        - Less accurate than the State Plane method for precise surveys.
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

    # Calculate the convergence angle in radians using simplified formula
    # Convergence = (λ - λ₀) × sin(φ)
    convergence_rad = (lambda_ - lambda0) * math.sin(phi)

    # Convert radians to degrees
    convergence_deg = math.degrees(convergence_rad)

    return convergence_deg


def setup_db() -> sqlite3.Connection:
    """Establish connection to the local SQLite database for PLSS section data.

    This function connects to a local SQLite database containing Public Land
    Survey System (PLSS) section information used for plat coordinate calculations.

    Returns:
        SQLite database connection object.

    Note:
        The database path is currently hardcoded and should be made configurable.
    """
    # path_used_db = r'C:\Work\Databases'
    # apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
    #
    # return sqlite3.connect(apd_data_dir)

    return sqlite3.connect(get_plss_sections_path())


class ETools(QMainWindow):
    """Main application window for oil and gas engineering tools.

    This class provides the primary user interface for directional survey processing,
    wellbore clearance analysis, and visualization. It integrates various subsystems
    including database connectivity, survey processing, and data visualization.

    Key Functionality:
        - API-based well data retrieval
        - Directional survey import and processing
        - Wellbore clearance calculations
        - 2D and 3D visualization
        - Survey point interpolation and editing
        - Plat coordinate management
        - Export capabilities for reports and data

    Attributes:
        ui: The main UI interface from Qt Designer
        db: DatabaseManager instance for data operations
        well: EToolsWell instance representing the current well
        drawer: DataDrawer for visualization operations
        writer: DataWriter for data export and display
        survey_importer: SurveyImporter for loading external survey files
    """

    def __init__(self, flag: bool = True) -> None:
        """Initialize the main application window and connect UI signals.

        Args:
            flag: Unused parameter maintained for backwards compatibility.
        """
        super().__init__()

        # Initialize instance variables for major components
        self._last_processed_api = ""
        self._last_processed_lateral = ""
        self.writer = None
        self.survey_importer = None
        self.wcr_process = None
        self.drawer = None
        self.db = None

        # Configure pandas display options for debugging
        pd.set_option('display.max_columns', None)
        pd.options.mode.chained_assignment = None

        # Well identification attributes
        self.api_val = None
        self.apd_num = None
        self.well_name = None
        self.lateral = None

        # File paths for survey imports
        self.file_path_planned = None
        self.file_path_drilled = None
        self.file_path_dict = {'planned': self.file_path_planned, 'drilled': self.file_path_drilled}

        # Well object and survey type tracking
        self.well = None
        self.survey_type_lst = []

        # # Initialize database connection with error handling
        # try:
        #     self.db = DatabaseManager()
        # except sqlalchemy.exc.OperationalError:
        #     # Continue without database if connection fails
        #     pass

        # Initialize survey importer
        self.survey_importer = SurveyImporter()

        # Set up UI from Qt Designer file
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        self._update_db_button_state(connected=False)

        self.ui.db_connect_pushbutton.pressed.connect(self.connect_to_db)

        # Connect to local SQLite database for PLSS data
        self.conn = setup_db()

        # Initialize helper components
        self.points_checker = PointChecker(ui=self.ui)

        # Create exclusive button group for survey type selection
        self.button_group = QButtonGroup(self.ui.survey_type_widget)
        self.button_group.setExclusive(True)

        # Initialize widget clearer for form reset functionality
        self.clearer = UltraFastClearer(self, self.ui.well_api_val)

        # Connect UI signals to handler methods
        self.ui.well_api_val.editingFinished.connect(self.run_api_when_entered)
        self.ui.lateral_name_line_edit.editingFinished.connect(self.run_api_when_entered)

        # self.ui.well_api_val.returnPressed.connect(self.run_api_when_entered)
        # self.ui.lateral_name_line_edit.returnPressed.connect(self.run_api_when_entered)


        # self.ui.dx_survey_bhl_line.returnPressed.connect()
        # self.ui.dx_survey_kop_line.returnPressed.connect()
        # self.ui.dx_survey_prod_line.returnPressed.connect()
        # self.ui.dx_survey_pro_azi_line.returnPressed.connect()

        # self.ui.add_dx_data_pushbutton.pressed.connect(self.recalculate_data_with_new_md_input)
        self.ui.add_dx_data_pushbutton.pressed.connect(
            lambda: self.recalculate_data_with_new_md_input(float(self.ui.new_md_survey_box.text())))

        # self.ui.runDXSurveyPushbutton.pressed.connect(self.process_when_dx_button_pushed)
        self.ui.runDXSurveyPushbutton.pressed.connect(lambda: self.process_when_dx_button_pushed())

        # self.ui.locate_more_wells_push_button.pressed.connect(self.find_more_sections_and_report)
        self.ui.dx_new_row_pushbutton.clicked.connect(self.open_dialog_new_row)
        self.ui.dx_delete_row_pushbutton.clicked.connect(self.open_dialog_delete)
        # self.ui.plat_searcher_combo_box.activated.connect(self.plat_searcher_combo_process)
        # self.ui.data_return_box.anchorClicked.connect(QDesktopServices.openUrl)
        self.ui.load_as_drilled_survey_box.clicked.connect(lambda: self.press_new_survey_button('drilled'))
        self.ui.load_planned_survey_box.clicked.connect(lambda: self.press_new_survey_button('planned'))
        self.original_streams = setup_console_redirection(
            self.ui.debug_return_box,
            timestamp_interval=2.0  # Only show timestamps every 2 seconds
        )
        # self.original_streams = setup_console_redirection(self.ui.debug_return_box)

        # 4301353727
        # 4301354659
        # self.ui.well_api_val.setText('4301354659')
        # self.connect_to_db()
        #
        # self.run_api_when_entered()
        # self.process_when_dx_button_pushed()

    def handle_api_input(self) -> None:
        """Handle API input changes, only process if values actually changed."""
        current_api = self.ui.well_api_val.text().strip()
        current_lateral = self.ui.lateral_name_line_edit.text().strip()

        # Only process if values actually changed AND we have a valid API
        if (current_api and
                (current_api != self._last_processed_api or
                 current_lateral != self._last_processed_lateral)):

            print(f"API changed from '{self._last_processed_api}' to '{current_api}'")
            print(f"Lateral changed from '{self._last_processed_lateral}' to '{current_lateral}'")

            # Update tracked values
            self._last_processed_api = current_api
            self._last_processed_lateral = current_lateral

            # Process the new API
            self.run_api_when_entered()
        else:
            print("No API change detected, skipping processing")
    def connect_to_db(self):
        print('connection')
        """Connect to database and update button state accordingly."""
        try:
            self.db = DatabaseManager()
            self._update_db_button_state(connected=True)
            self.db_connect_popup()
        except sqlalchemy.exc.OperationalError:
            self.db = None
            self._update_db_button_state(connected=False)
            self.no_db_connect_popup()
        return self.db

    def _update_db_button_state(self, connected: bool):
        """Update button appearance based on connection status.

        Args:
            connected: True if database is connected, False otherwise
        """
        if connected:
            self.ui.db_connect_pushbutton.setText("DB Connected ✓")
            self.ui.db_connect_pushbutton.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }"
            )
            self.ui.db_connect_pushbutton.setEnabled(False)  # Disable when connected
        else:
            self.ui.db_connect_pushbutton.setText("Connect to DB")
            self.ui.db_connect_pushbutton.setStyleSheet(
                "QPushButton { background-color: #f44336; color: white; }"
            )
            self.ui.db_connect_pushbutton.setEnabled(True)

    def disconnect_from_db(self):
        """Disconnect from database and reset button state."""
        if self.db:
            self.db = None
            self._update_db_button_state(connected=False)

    def open_dialog_new_row(self) -> None:
        """Open dialog for adding a new survey point and process the input.

        This method displays a dialog for entering measured depth, inclination,
        and azimuth values for a new survey point. If accepted, it adds the
        point to the current survey and recalculates all dependent data.
        """
        dialog = InputDialog(None)

        if dialog.exec_() == QDialog.Accepted:
            inputs = dialog.get_inputs()
            # Process the inputs
            measured_depth = inputs["measured_depth"]
            inclination = inputs["inclination"]
            azimuth = inputs["azimuth"]
            self.recalculate_with_new_row(measured_depth, inclination, azimuth)

    def open_dialog_delete(self) -> None:
        """Open dialog for deleting a survey row by row number.

        This method displays a simple input dialog for entering a row number
        to delete from the current survey. The row is removed and all
        dependent calculations are updated.
        """
        dialog = SingleInputDialog(
            title="Enter Row",
            label="Value:",
            placeholder="Enter a row"
        )

        if dialog.exec_() == QDialog.Accepted:
            value = dialog.get_value()
            try:
                # Convert to appropriate type if needed
                numeric_value = float(value)
                # Process the value
                self.delete_row_and_recalculate(numeric_value)
            except ValueError:
                QMessageBox.warning(None, "Error", "Please enter a valid number.")

    def clear_checkboxes(self) -> None:
        """Clear all checkboxes from the surveys draw layout.

        This method removes all checkbox widgets from the layout, properly
        handling widget cleanup to prevent memory leaks.
        """
        while self.ui.surveys_draw_layout.count():
            item = self.ui.surveys_draw_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def clear_radio_buttons(self) -> None:
        """Clear all radio buttons and reset the button group.

        This method removes all radio button widgets from the surveys layout
        and creates a fresh button group to prevent reference issues.
        """
        while self.ui.surveys_layout.count():
            item = self.ui.surveys_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()  # Properly delete widget to free memory

        # Reset the button group to remove all previous references
        self.button_group = QButtonGroup(self.ui.survey_type_widget)
        self.button_group.setExclusive(True)

    def write_radio_buttons(self, df: dict, surveys: dict) -> None:
        """Create radio buttons and checkboxes for survey type selection.

        This method dynamically creates UI controls for each available survey type,
        allowing users to select which survey to display and which to include in
        visualizations.

        Args:
            df: Dictionary of clearance data dictionaries keyed by survey type.
            surveys: Dictionary of survey objects for special depth calculations.
        """

        def checkbox_creator():
            """Create a checkbox for the current survey type."""
            checkbox = QCheckBox(dict_translator[survey_label])
            checkbox.setObjectName(f"checkbox_survey_{survey_label}")
            self.ui.surveys_draw_layout.addWidget(checkbox)
            checkbox.setProperty('survey_name', survey_label)
            checkbox.stateChanged.connect(
                lambda state, lbl=survey_label: self.drawer.check_box_activate_path(state=state, lbl=lbl))

        # Clear existing buttons if any
        self.clear_radio_buttons()
        self.clear_checkboxes()

        # Translation dictionary for user-friendly names
        dict_translator = {
            'drl_df_true_dx': "AsDrilled - True",
            'drl_df_grid_dx': "AsDrilled - Grid",
            'pln_df_true_dx': "Planned - True",
            'pln_df_grid_dx': "Planned - Grid"
        }

        # Retrieve survey type variables
        variables = [i for i, _ in df.items()]

        # Create radio buttons and checkboxes for each survey type
        for idx, survey_label in enumerate(variables):
            checkbox_creator()
            radio_button = QRadioButton(dict_translator[survey_label])
            radio_button.setObjectName(f"radio_survey_{idx}")
            self.ui.surveys_layout.addWidget(radio_button)
            self.button_group.addButton(radio_button, id=idx)
            # Use partial to ensure survey_label is captured correctly
            radio_button.clicked.connect(partial(self.writer.survey_writer, self.ui, survey_label))

        # Select the first radio button by default
        if variables:
            self.button_group.button(0).setChecked(True)
            self.writer.survey_writer(self.ui, variables[0])

    def bad_api_popup(self) -> None:
        """Display warning dialog for invalid API number input."""
        QMessageBox.warning(self, "Attention", "Invalid API Detected! Fix it! (Possibly a string?)",
                            QMessageBox.Ok)

    def missing_well_id(self) -> None:
        """Display warning dialog for invalid API number input."""
        QMessageBox.warning(self, "Attention", "You're missing either the api or the lateral number",
                            QMessageBox.Ok)

    def no_db_connect_popup(self) -> None:
        """Display warning dialog for invalid API number input."""
        QMessageBox.warning(self, "Attention", "No database connected",
                            QMessageBox.Ok)

    def db_connect_popup(self) -> None:
        """Display warning dialog for invalid API number input."""
        QMessageBox.warning(self, "Attention", "Database connected!",
                            QMessageBox.Ok)

    def api_loaded(self) -> None:
        """Display confirmation dialog when API is successfully loaded."""
        QMessageBox.warning(self, "Attention", "API Loaded!", QMessageBox.Ok)

    def no_dx_popup(self) -> None:
        """Display warning dialog when no directional survey is found."""
        QMessageBox.warning(self, "Attention", "No directional survey detected in database!",
                            QMessageBox.Ok)

    def imported_dx_survey(self) -> None:
        """Display confirmation dialog when survey is successfully imported."""
        QMessageBox.warning(self, "Attention", "Imported a new DX Survey!", QMessageBox.Ok)

    def retrieve_well_parameters(self) -> None:
        """Retrieve well permit number and name from database using API.

        This method queries the database to get the APD (Application for Permit
        to Drill) number and well name associated with the current API and lateral.

        Note:
            Sets self.apd_num and self.well_name instance attributes.
        """
        query = f"""SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = '{self.api_val}{self.lateral}'"""
        try:
            self.apd_num = self.db.query_to_dataframe(query)['APDNo'].unique()[0]
            self.well_name = self.db.query_to_dataframe(query)['Well_Nm'].unique()[0]
        except AttributeError:
            self.apd_num = None
            self.well_name = None

    def sql_query_survey(self, db_process: DatabaseManager, api: str, lateral: str) -> tuple:
        """Query directional survey data from the database.

        This method retrieves all survey points and header information for a
        specific well from the database, including surface location and elevation.

        Args:
            db_process: DatabaseManager instance for query execution.
            api: API number of the well (10 digits).
            lateral: Lateral identifier (typically 4 digits).

        Returns:
            Tuple containing:
                - survey_dx: DataFrame with survey points (MD, Inc, Azi)
                - well_elevation: Surface elevation in feet
                - north_ref: North reference ('t' for true, 'g' for grid)

        Note:
            Shows popup warning if no survey data is found.
        """
        query = f"""SELECT MeasuredDepth as measured_depth, Inclination as inclination, Azimuth as azimuth, 
        CitingType, dsh.SurveySurfaceElevation, dsh.SurfaceLatitude, dsh.SurfaceLongitude,dsh.NorthReference, dsh.LateralName
                FROM DirectionalSurveyHeader dsh
                JOIN DirectionalSurveyData dsd on dsd.DirectionalSurveyHeaderKey = dsh.Pkey
                WHERE dsh.APINumber = '{api}' and dsh.LateralName = '{lateral}' order by MeasuredDepth"""

        survey_dx = db_process.query_to_dataframe(query)
        try:
            # Extract header information
            well_elevation = survey_dx['SurveySurfaceElevation'].iloc[0]
            north_ref = survey_dx['NorthReference'].iloc[0][0].lower()

            # Clean up the survey data
            survey_dx = survey_dx.drop(['SurveySurfaceElevation', 'NorthReference'], axis=1)
            survey_dx = survey_dx.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
            survey_dx = survey_dx.sort_values(by=['CitingType', 'measured_depth'])

            # Standardize citing type capitalization
            survey_dx['CitingType'] = survey_dx['CitingType'].str.lower().replace(
                {'asdrilled': 'AsDrilled', 'planned': 'Planned'})

            return survey_dx, well_elevation, north_ref

        except IndexError:
            self.no_dx_popup()

    def run_api_when_entered(self) -> None:
        """Process API number entry and initialize well data retrieval."""

        # Store current values before clearing
        current_api = self.ui.well_api_val.text()
        current_lateral = self.ui.lateral_name_line_edit.text()

        # Block signals to prevent recursive calls during clearing
        self.ui.well_api_val.blockSignals(True)
        self.ui.lateral_name_line_edit.blockSignals(True)

        try:
            # Clear all existing data and visualizations
            self.clearer.execute_clear()

            # Restore the API and lateral values after clearing
            self.ui.well_api_val.setText(current_api)
            self.ui.lateral_name_line_edit.setText(current_lateral)

            # Continue with your existing processing logic...
            main_project_drawer.clear_widget(self.ui.well_viz_display)
            main_project_drawer.clear_layout(self.ui.well_viz_display_general)
            main_project_drawer.clear_layout(self.ui.well_viz_display_tsr)

            # Clear individual coordinate displays
            for i in range(8):
                ui_viz = getattr(self.ui, f"well_graphic_coords_{i + 1}")
                ui_viz_2 = getattr(self.ui, f"well_graphic_mp_individual_{i + 1}")
                main_project_drawer.clear_layout(ui_viz)
                main_project_drawer.clear_layout(ui_viz_2)

            # Reset file paths
            self.file_path_planned = None
            self.file_path_drilled = None
            self.file_path_dict = {'planned': self.file_path_planned, 'drilled': self.file_path_drilled}

            # Get and validate API input
            api_val = self.ui.well_api_val.text()
            if len(api_val) == 14:
                self.ui.lateral_name_line_edit.setText(api_val[-4:])
                api_val = api_val[:10]
                self.ui.well_api_val.setText(api_val)

            lateral_name = self.ui.lateral_name_line_edit.text()
            if lateral_name == '':
                dialog = LateralNameDialog(parent=self)  # 'self' would be your main window

                if dialog.exec_() == QDialog.Accepted:
                    lateral_name = dialog.get_value()
                    self.ui.lateral_name_line_edit.setText(lateral_name)
                    print(f"Lateral name provided by user: {lateral_name}")
                else:
                    # Handle the case where the user cancels the dialog
                    QMessageBox.critical(self, "Operation Aborted",
                                         "A valid lateral name is required to proceed. The process cannot continue.")
                    # self.ui.well_api_val.blockSignals(False)
                    # self.ui.lateral_name_line_edit.blockSignals(False)
                    return  # Or raise an exception to stop execution
            # if lateral_name == '':
            #     lateral_name = '0000'
            #     self.ui.lateral_name_line_edit.setText('0000')

            # Truncate API to 10 digits if longer


            # Validate API is numeric
            try:
                int(float(api_val))
            except ValueError:
                self.bad_api_popup()
                # self.ui.well_api_val.blockSignals(False)
                # self.ui.lateral_name_line_edit.blockSignals(False)
                return

            # Store validated values and retrieve well parameters
            self.api_val = api_val
            self.lateral = lateral_name
            self.retrieve_well_parameters()

        finally:
            # Always restore signals
            self.ui.well_api_val.blockSignals(False)
            self.ui.lateral_name_line_edit.blockSignals(False)

    def process_when_dx_button_pushed(self, survey_dx_imported=None, well_elevation=None, north_ref=None) -> None:
        if not self.lateral and not self.api_val:
            self.missing_well_id()

        """Process directional survey data when the DX button is clicked.

        This method initiates the main survey processing workflow, including:
        - Loading survey data from database or manual entry
        - Creating well object with all subsystems
        - Initializing visualization and analysis components
        - Setting up UI interactions for survey manipulation
        """
        # Attempt to load survey from database
        if survey_dx_imported is None:
            survey_dx, well_elevation, north_ref = self.sql_query_survey(self.db, self.api_val, self.lateral)
        else:
            # Fall back to manual entry if database query fails
            well_elevation = self.ui.dx_survey_elevation.text()
            north_ref = self.ui.dx_survey_north_ref_line.text()
            survey_dx = _get_data_from_qtableview(self.ui.dx_survey_table_mod)
            if survey_dx is None:
                survey_dx = survey_dx_imported


        if not well_elevation or not north_ref:
            dialog = ManualDataInputDialog(
                current_elevation=well_elevation,
                current_north_ref=north_ref,
                parent=self
            )

            if dialog.exec_() == QDialog.Accepted:
                # User provided manual input
                well_elevation, north_ref = dialog.get_values()
                print(f"Manual input received - Elevation: {well_elevation}, North Ref: {north_ref}")
            else:
                # User cancelled the dialog
                QMessageBox.information(self, "Operation Cancelled",
                                        "Manual data entry was cancelled. Process aborted.")
                return  # Exit the method early
        # Update UI with survey parameters
        self.ui.dx_survey_elevation.setText(str(well_elevation))
        self.ui.dx_survey_north_ref_line.setText(str(north_ref.lower()))

        # Create well object with all survey data
        self.well = EToolsWell(db=self.db, api=self.api_val, apd_num=self.apd_num, well_name=self.well_name,
                               lateral=self.lateral, survey_dx=survey_dx, well_elevation=well_elevation,
                               north_ref=north_ref, ui=self.ui, conn=self.conn)

        # Initialize UI components
        # self.find_more_sections_combo_box()
        self.main_processes_program(north_ref)

        # Create data writer for export and display
        self.writer = DataWriter(ui=self.ui,
                                 surveys=self.well.cl_dx_dict,
                                 spec_surveys=self.well.spec_surveys_dict,
                                 parameters=self.well.survey_parameters,
                                 plat_df=self.well.plat_df)

        # Set up survey selection UI
        self.write_radio_buttons(self.well.cl_dx_dict, self.well.spec_surveys_dict)

        # Connect additional UI buttons
        # self.ui.calc_new_dx_with_new_shl_pushbutton.clicked.connect(self.process_with_new_shl)
        self.ui.pushbutton_rerun_coords.pressed.connect(lambda: self.etools_process_with_new_coords(north_ref))

    def main_processes_program(self, north_ref: str) -> None:
        """Initialize all main processing components for the well.

        This method sets up the core functionality including visualization,
        clearance calculations, and UI interactions after survey data is loaded.

        Args:
            north_ref: North reference type ('t' for true, 'g' for grid).
        """
        # Update well name display
        self.ui.well_name.setText(self.well.well_name)

        # Initialize data drawer for visualizations
        self.drawer = DataDrawer(ui=self.ui, df_survey=self.well.cl_dx_dict)
        self.drawer.draw_2d_data(df_plat=self.well.plat_df, df_survey=self.well.cl_dx_dict)
        self.drawer.draw_3d_process(df=self.well.cl_dx_dict)

        # Initialize wellbore clearance report process
        # well_data_parameters = {'APINumber': [self.api_val], 'LateralNumber':[self.lateral], 'WellNameNumber': [self.well.well_name], "OperatorName": [None]}
        # self.final_data = {
        #     'SundryNo': [self.sundry_no_edit.text()],
        #     'OperatorName': [self.operator_name_edit.text()],
        #     'WellNameNumber': [self.well_name_edit.text()],
        #     'APINumber': [self.api_number_edit.text()],
        #     'ConstructKey': [self.lateral_name_edit.text()],
        #     'SubmitDate': [pd.to_datetime(self.submit_date_edit.date().toString("yyyy-MM-dd"))]
        # }
        known_parameters = pd.DataFrame(
            data={'SubmitDate': None, 'SundryNo': None, 'APINumber': [self.api_val], 'LateralNumber': [self.lateral],
                  'WellNameNumber': [self.well.well_name], "OperatorName": [None]})
        self.wcr_process = WCR_Main(df=self.well.cl_dx_dict, ui=self.ui, db=self.db, loc_df=self.well.loc_df,
                                    spec_surveys=self.well.spec_surveys_dict, north_ref=north_ref,
                                    known_parameters=known_parameters)
        self.wcr_process.process_wcr()

        # Connect visualization control buttons
        self.ui.add_pt_viz_button.pressed.connect(self.drawer.insert_user_generated_point)
        self.ui.border_100.stateChanged.connect(lambda state: self.drawer.change_visibility_100(state=state))
        self.ui.border_330.stateChanged.connect(lambda state: self.drawer.change_visibility_330(state=state))

    def determine_coord_system(self, x: float, y: float) -> list[float]:
        """Determine if coordinates are lat/lon or UTM and convert to lat/lon.

        This method automatically detects the coordinate system based on value
        ranges and converts UTM coordinates to latitude/longitude if needed.

        Args:
            x: First coordinate (latitude or easting).
            y: Second coordinate (longitude or northing).

        Returns:
            List containing [latitude, longitude] in decimal degrees.

        Notes:
            - Lat/lon ranges: -90 to 90 for latitude, -180 to 180 for longitude
            - UTM ranges: 166,000 to 834,000 for easting, 0 to 10,000,000 for northing
            - Assumes UTM Zone 12T for Utah coordinates
        """
        # Check if the point falls within typical lat/lon ranges
        if -180 <= y <= 180 and -90 <= x <= 90:
            return [x, y]

        # Check if the point falls within typical UTM ranges
        if 166000 <= x <= 834000 and 0 <= y <= 10000000:
            return utm.to_latlon(x, y, 12, 'T')

    def delete_row_and_recalculate(self, row: float) -> None:
        """Delete a survey row and recalculate all dependent data.

        This method removes a specific row from the current survey type,
        reprocesses all calculations, and updates the UI displays.

        Args:
            row: Row number to delete (1-based index).
        """

        def return_well_survey() -> pd.DataFrame:
            """Get the currently selected survey data."""
            dict_return = {
                'AsDrilled - True': self.well.cl_dx_dict['drl_df_true_dx'].clearance_data,
                'AsDrilled - Grid': self.well.cl_dx_dict['drl_df_grid_dx'].clearance_data,
                'Planned - True': self.well.cl_dx_dict['pln_df_true_dx'].clearance_data,
                'Planned - Grid': self.well.cl_dx_dict['pln_df_grid_dx'].clearance_data
            }
            checked_button = self.button_group.checkedButton()
            checked_button_text = checked_button.text()
            for k, v in dict_return.items():
                if k.lower() in checked_button_text.lower():
                    return dict_return[k]

        def filter_by_citing_type() -> list[pd.DataFrame]:
            """Filter survey by currently selected citing type and remove row."""
            lst_data = []
            checked_button = self.button_group.checkedButton().text()
            dict_return = {
                'AsDrilled - True': 'AsDrilled',
                'AsDrilled - Grid': 'AsDrilled',
                'Planned - True': 'Planned',
                'Planned - Grid': 'Planned'
            }
            current_citing = dict_return[checked_button]
            new_df = copy.copy(survey)
            new_df = new_df[new_df['CitingType'] == current_citing]
            try:
                new_df.insert(0, 'row', new_df.index + 1)
                new_df = new_df[new_df['row'] != row]
                new_df = new_df.drop(['row'], axis=1)
                lst_data.append(new_df)
            except IndexError:
                pass
            return lst_data

        # Get current survey and remove the specified row
        survey = self.well.get_survey()
        output = filter_by_citing_type()
        survey = pd.concat(output, ignore_index=True)
        survey = survey.sort_values(by=['CitingType', 'measured_depth'])

        # Update well with modified survey and reprocess
        self.well.set_survey(survey)
        self.well.reprocess_with_current_plat()
        self.main_processes_program(self.ui.dx_survey_north_ref_line.text())

        # Update writer with new data
        self.writer.set_clear_survey(self.well.cl_dx_dict)
        self.writer.set_spec_surveys(self.well.spec_surveys_dict)

        # Maintain current radio button selection
        first_button = self.button_group.button(self.button_group.checkedId())

    def recalculate_with_new_row(self, md: float, inc: float, azi: float) -> None:
        """Add a new survey row with specified values and recalculate.

        This method adds a new survey point to the current survey type and
        updates all dependent calculations and displays.

        Args:
            md: Measured depth for the new point.
            inc: Inclination angle in degrees.
            azi: Azimuth angle in degrees.
        """

        def return_well_survey() -> pd.DataFrame:
            """Get the currently selected survey data."""
            dict_return = {
                'AsDrilled - True': self.well.cl_dx_dict['drl_df_true_dx'].clearance_data,
                'AsDrilled - Grid': self.well.cl_dx_dict['drl_df_grid_dx'].clearance_data,
                'Planned - True': self.well.cl_dx_dict['pln_df_true_dx'].clearance_data,
                'Planned - Grid': self.well.cl_dx_dict['pln_df_grid_dx'].clearance_data
            }
            checked_button = self.button_group.checkedButton()
            checked_button_text = checked_button.text()
            for k, v in dict_return.items():
                if k.lower() in checked_button_text.lower():
                    return dict_return[k]

        def filter_by_citing_type() -> list[pd.DataFrame]:
            """Create new row data for each citing type in the survey."""
            lst_data = [survey]
            for citing, group in survey.groupby('CitingType'):
                try:
                    new_row = {
                        'measured_depth': md,
                        'inclination': inc,
                        'azimuth': azi,
                        'CitingType': citing,
                        'SurfaceLatitude': group['SurfaceLatitude'].iloc[0],
                        'SurfaceLongitude': group['SurfaceLongitude'].iloc[0],
                        'LateralName': group['LateralName'].iloc[0]
                    }
                    lst_data.append(pd.DataFrame([new_row]))
                except IndexError:
                    pass
            return lst_data

        # Get current survey and add new row
        survey = self.well.get_survey()
        output = filter_by_citing_type()
        survey = pd.concat(output, ignore_index=True)
        survey = survey.sort_values(by=['CitingType', 'measured_depth'])

        # Update well and reprocess
        self.well.set_survey(survey)
        self.well.reprocess_with_current_plat()
        self.main_processes_program(self.ui.dx_survey_north_ref_line.text())

        # Update writer and display
        self.writer.set_clear_survey(self.well.cl_dx_dict)
        self.writer.set_spec_surveys(self.well.spec_surveys_dict)
        self.writer.write_new_survey_line_to_display(return_well_survey(), md)

        # Refresh radio button selection
        first_button = self.button_group.button(self.button_group.checkedId())
        first_button.setChecked(True)
        first_button.clicked.emit()

    def recalculate_data_with_new_md_input(self, md) -> None:
        """Interpolate and add a new survey point at user-specified measured depth.

        This method reads a measured depth from the UI, interpolates inclination
        and azimuth values from surrounding points, and adds the new point to
        the survey. Special handling ensures proper interpolation of azimuth
        angles across the 0/360 degree boundary.
        """

        def return_well_survey() -> pd.DataFrame:
            """Get the currently selected survey data."""
            dict_return = {
                'AsDrilled - True': self.well.cl_dx_dict['drl_df_true_dx'].clearance_data,
                'AsDrilled - Grid': self.well.cl_dx_dict['drl_df_grid_dx'].clearance_data,
                'Planned - True': self.well.cl_dx_dict['pln_df_true_dx'].clearance_data,
                'Planned - Grid': self.well.cl_dx_dict['pln_df_grid_dx'].clearance_data
            }
            checked_button = self.button_group.checkedButton()
            checked_button_text = checked_button.text()
            for k, v in dict_return.items():
                if k.lower() in checked_button_text.lower():
                    return dict_return[k]

        def filter_by_citing_type() -> list[pd.DataFrame]:
            """Interpolate values for new point at specified MD."""

            def interpolate_azimuth() -> float:
                """Interpolate azimuth angles, handling circular wrap-around.

                This function uses vector decomposition to properly interpolate
                azimuth values across the 0/360 degree boundary. Angles are
                converted to unit vectors, interpolated in Cartesian space,
                then converted back to degrees.

                Returns:
                    Interpolated azimuth in degrees (0-360).
                """
                md_range = [float(lower_row['measured_depth']), float(upper_row['measured_depth'])]
                azimuth_range = [float(lower_row['azimuth']), float(upper_row['azimuth'])]

                # Convert degrees to radians for trigonometric functions
                azimuth_rad = np.deg2rad(azimuth_range)

                # Convert the angles to Cartesian coordinates
                x = np.cos(azimuth_rad)
                y = np.sin(azimuth_rad)

                # Interpolate the x and y components
                interp_x = np.interp(md, md_range, x)
                interp_y = np.interp(md, md_range, y)

                # Convert the interpolated Cartesian coordinates back to an angle
                interp_azimuth_rad = np.arctan2(interp_y, interp_x)

                # Convert back to degrees and ensure it's within 0-360 range
                interp_azimuth_deg = np.rad2deg(interp_azimuth_rad) % 360

                return interp_azimuth_deg

            lst_data = [survey]
            for citing, group in survey.groupby('CitingType'):
                try:
                    # Find surrounding points for interpolation
                    lower_row = group[group['measured_depth'].astype(float) < md].iloc[-1]
                    upper_row = group[group['measured_depth'].astype(float) > md].iloc[0]

                    # Create interpolated point
                    new_row = {
                        'measured_depth': md,
                        'inclination': np.interp(md,
                                                 [float(lower_row['measured_depth']),
                                                  float(upper_row['measured_depth'])],
                                                 [float(lower_row['inclination']),
                                                  float(upper_row['inclination'])]),
                        'azimuth': interpolate_azimuth(),
                        'CitingType': lower_row['CitingType'],
                        'SurfaceLatitude': lower_row['SurfaceLatitude'],
                        'SurfaceLongitude': lower_row['SurfaceLongitude'],
                        'LateralName': lower_row['LateralName']
                    }
                    lst_data.append(pd.DataFrame([new_row]))
                except IndexError:
                    pass
            return lst_data

        # Get MD from UI and process
        # md = float(self.ui.new_md_survey_box.text())
        survey = self.well.get_survey()
        output = filter_by_citing_type()
        survey = pd.concat(output, ignore_index=True)
        survey = survey.sort_values(by=['CitingType', 'measured_depth'])

        # Update well and reprocess
        self.well.set_survey(survey)
        self.well.reprocess_with_current_plat()
        self.main_processes_program(self.ui.dx_survey_north_ref_line.text())

        # Update writer and display
        self.writer.set_clear_survey(self.well.cl_dx_dict)
        self.writer.set_spec_surveys(self.well.spec_surveys_dict)
        self.writer.write_new_survey_line_to_display(return_well_survey(), md)

        # Refresh radio button
        first_button = self.button_group.button(self.button_group.checkedId())
        first_button.setChecked(True)
        first_button.clicked.emit()

    def process_with_new_shl(self) -> None:
        """Process survey with a new surface hole location (SHL).

        This method updates the starting point for all surveys when the user
        enters new surface coordinates. The coordinates are automatically
        detected as either lat/lon or UTM format.
        """
        # Get coordinates from UI and determine format
        # pt = self.determine_coord_system(float(self.ui.shl_lat_easting.text()),
        #                                  float(self.ui.shl_lon_northing.text()))

        # Update well with new starting point and reprocess
        self.well.set_starting_point(pt)
        self.main_processes_program(self.ui.dx_survey_north_ref_line.text())
        self.writer.set_clear_survey(self.well.cl_dx_dict)
        self.writer.set_spec_surveys(self.well.spec_surveys_dict)
        self.well.load_surveys()

    def etools_process_with_new_coords(self, north_ref: str) -> None:
        """Reprocess all data after plat coordinates have been edited.

        This method is called when the user modifies plat boundary coordinates.
        It triggers a complete recalculation of clearances and updates all
        displays with the new data.

        Args:
            north_ref: North reference type ('t' for true, 'g' for grid).
        """
        # Process edited plat coordinates
        self.well.process_plat_editor()

        # Update all data structures
        self.writer.set_clear_survey(self.well.cl_dx_dict)
        self.writer.set_spec_surveys(self.well.spec_surveys_dict)

        # Refresh all displays
        self.main_processes_program(north_ref)
        self.write_radio_buttons(self.well.cl_dx_dict, self.well.spec_surveys_dict)

        # Re-enable survey import buttons
        self.ui.load_as_drilled_survey_box.blockSignals(False)
        self.ui.load_planned_survey_box.blockSignals(False)

    def press_new_survey_button(self, label: str) -> None:
        """Handle survey import button clicks for planned or drilled surveys.

        This method manages the file selection and import process for external
        survey files. It temporarily blocks signals to prevent multiple imports
        and handles various error conditions gracefully.

        Args:
            label: Survey type identifier ('planned' or 'drilled').
        """
        # Block signals to prevent multiple simultaneous imports
        self.ui.load_as_drilled_survey_box.blockSignals(True)
        self.ui.load_planned_survey_box.blockSignals(True)

        def loader() -> bool:
            """Open file dialog and store selected file path.

            Returns:
                True if file was selected, False if canceled.
            """
            current_dir = os.getcwd()
            file_path = QFileDialog.getOpenFileName(None, 'Open file', current_dir)
            if file_path[0] == '':
                print("User canceled file selection")
                self.ui.load_as_drilled_survey_box.blockSignals(False)
                self.ui.load_planned_survey_box.blockSignals(False)
                return False
            self.file_path_dict[label] = file_path[0]
            return True

        def filter_out_same_citing() -> pd.DataFrame:
            """Remove existing survey of same type before adding new one.

            Returns:
                Combined DataFrame with old survey type removed and new added.
            """
            new_label = 'Planned' if label == 'planned' else 'AsDrilled'
            try:
                current_df = self.well.survey_dx
                current_df = current_df[current_df['CitingType'] != new_label]
                current_df = current_df.sort_values(by=['measured_depth'])
                new_df = pd.concat([current_df, df]).reset_index(drop=True)
                return new_df
            except AttributeError:
                return df

        restrict_lock = False
        try:
            result_boo = loader()
            if result_boo:  # If file was successfully selected
                # Import and process the survey file
                df, north_ref = self.survey_importer.load_and_process_data(label, self.db, self.api_val,
                                                                           self.file_path_dict)

                # Extract elevation and prepare data
                well_elevation = df['SurveySurfaceElevation'].iloc[0]
                df = df.sort_values(by=['measured_depth'])
                self.ui.dx_survey_elevation.setText(str(well_elevation))
                df = df.drop(['SurveySurfaceElevation'], axis=1)
                df['LateralName'] = self.lateral
                # Combine with existing surveys
                output_new_df = filter_out_same_citing()
                if self.well is None:
                    restrict_lock = True
                    self.process_when_dx_button_pushed(survey_dx_imported=df, well_elevation=well_elevation,
                                                       north_ref=north_ref)
                test_combo = copy.copy(self.well.plat_df)
                # Update well with new survey data
                self.well.set_survey(output_new_df)
                self.well.set_north_ref(north_ref)
                self.well.set_well_elevation(well_elevation)
                self.well.set_plat_data(test_combo)
                if not restrict_lock:
                    self.well.rerun_surveys()

                # Update displays
                self.writer.set_clear_survey(self.well.cl_dx_dict)
                self.writer.set_spec_surveys(self.well.spec_surveys_dict)
                if not restrict_lock:
                    self.main_processes_program(north_ref)
                self.write_radio_buttons(self.well.cl_dx_dict, self.well.spec_surveys_dict)

                # Re-enable buttons and show success message
                self.ui.load_as_drilled_survey_box.blockSignals(False)
                self.ui.load_planned_survey_box.blockSignals(False)
                self.imported_dx_survey()
            else:
                pass
        except (TypeError, ValueError, AttributeError, KeyError, FileNotFoundError) as e:
            error_traceback = traceback.format_exc()
            # Re-enable buttons on error
            self.ui.load_as_drilled_survey_box.blockSignals(False)
            self.ui.load_planned_survey_box.blockSignals(False)
            pass

    def find_more_sections_and_report(self) -> None:
        """Search for other wells in the same PLSS section and display results.

        This method queries the database for all wells within the same township,
        range, and section as specified in the UI. Results are displayed with
        clickable links to well plat PDFs.
        """

        def sql_find_section_data() -> pd.DataFrame:
            """Query database for wells in specified section.

            Returns:
                DataFrame containing APD numbers and API well numbers.
            """
            query = f"""select a.APDNo, a.API_WellNo
                    from [dbo].[tblAPDLoc] loc
                    inner join [dbo].[tblAPD] a on a.APDNo = loc.APDNO
                    where Wh_Sec = '{section}' and Wh_Twpn = '{ts}' and Wh_Twpd = '{ts_dir}' 
                    and Wh_RngN =' {rng}' and Wh_RngD = '{rng_dir}' and Wh_Pm = '{baseline}'"""
            output = self.db.query_to_dataframe(query)
            return output.drop_duplicates(keep="first")

        # Get search parameters from UI
        section = self.ui.searcher_section.text()
        ts = self.ui.searcher_township.text()
        ts_dir = self.ui.searcher_township_dir.text()
        rng = self.ui.searcher_range.text()
        rng_dir = self.ui.searcher_range_dir.text()
        baseline = self.ui.searcher_baseline.text()

        # Format section description
        township_rng_section = f"{section} {ts}{ts_dir} {rng}{rng_dir} {baseline}"

        # Query and display results
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

    def find_more_sections_combo_box(self) -> None:
        """Populate the plat searcher combo box with available sections.

        This method fills the dropdown with all unique plat sections from
        the current well's plat data, allowing quick section selection.
        """
        self.ui.plat_searcher_combo_box.clear()
        for idx, row in self.well.plat_df.iterrows():
            self.ui.plat_searcher_combo_box.addItem(row['label'])

    def plat_searcher_combo_process(self) -> None:
        """Handle plat searcher combo box selection changes.

        When a user selects a plat from the dropdown, this method automatically
        fills in the section search fields with the corresponding township,
        range, and section information.
        """
        current_label = self.ui.plat_searcher_combo_box.currentText()
        conc = self.well.plat_df[self.well.plat_df['label'] == current_label]['Conc'].iloc[0]

        # Parse concatenated location string
        self.ui.searcher_section.setText(str(int(float(conc[:2].strip()))))
        self.ui.searcher_township.setText(str(int(float(conc[2:4].strip()))))
        self.ui.searcher_township_dir.setText(conc[4].strip())
        self.ui.searcher_range.setText(str(int(float(conc[5:7].strip()))))
        self.ui.searcher_range_dir.setText(conc[7].strip())
        self.ui.searcher_baseline.setText(conc[-1].strip())


class EToolsWell:
    """Represents a well with all associated survey and location data.

    This class encapsulates all data and processing logic for a single well,
    including directional surveys, plat boundaries, clearance calculations,
    and coordinate transformations. It serves as the central data model for
    the application.

    Attributes:
        db: Database manager for data queries
        api: 10-digit API number
        apd_num: Application for Permit to Drill number
        well_name: Official well name
        lateral: Lateral identifier (typically 4 digits)
        survey_dx: DataFrame containing directional survey data
        well_elevation: Surface elevation in feet
        north_ref: North reference type ('t' or 'g')
        plat_df: DataFrame of plat boundary coordinates
        loc_df: DataFrame of well locations
        cl_dx_dict: Dictionary of clearance calculation results
    """

    def __init__(self, db: DatabaseManager, api: str, apd_num: str, well_name: str,
                 lateral: str, survey_dx: pd.DataFrame, well_elevation: float,
                 north_ref: str, ui, conn: sqlite3.Connection) -> None:
        """Initialize well object with survey and identification data.

        Args:
            db: Database manager instance
            api: Well API number
            apd_num: Permit number
            well_name: Well name
            lateral: Lateral identifier
            survey_dx: Survey data DataFrame
            well_elevation: Surface elevation
            north_ref: North reference type
            ui: User interface reference
            conn: SQLite connection for PLSS data
        """
        super().__init__()
        self.plat_editor = None
        self.conn = conn
        self.db = db
        self.ui = ui
        self.api = api
        self.apd_num = apd_num
        self.well_name = well_name
        self.lateral = lateral
        self.survey_dx = survey_dx
        self.rel_plats = SetupRelativeCoordsPage(conn=self.conn, ui=self.ui)

        # Extract starting point from first survey row
        first_pt = survey_dx.head(1)
        self.starting_point = [first_pt['SurfaceLatitude'].iloc[0], first_pt['SurfaceLongitude'].iloc[0]]
        self.well_elevation = well_elevation
        self.north_ref = north_ref

        # Initialize data containers
        self.plat_df_original = pd.DataFrame()
        self.loc_df_new = None
        self.plat_editor = None
        self.surveys_dict = {}
        self.plat_df = pd.DataFrame()
        self.loc_df = pd.DataFrame()
        self.cl_dx_dict = {}
        self.plat_editor = None

        self.surveys_dict, self.spec_surveys_dict, self.survey_parameters = None, None, None
        self.plat_df, self.loc_df, self.cl_dx_dict = None, None, None
        # Initialize with empty plat data and load surveys
        self.set_plat_data(None)
        self.load_surveys()

    def recreate_survey_objects(self) -> None:
        """Recreate survey processing objects for plat editor integration.

        This method creates specialized plat editor process objects for each
        combination of survey type (planned/drilled) and north reference
        (true/grid). These objects handle the intersection calculations
        between well paths and plat boundaries.

        Note:
            This method is currently incomplete and should be fully implemented
            to support dynamic plat editing functionality.
        """

        def decimal_converter(side: str, deg: float, minutes: float, sec: float,
                              dir_val: int) -> float:
            """Convert bearing notation to decimal degrees azimuth.

            This function handles the complex conversion from surveyor's bearing
            notation (e.g., N45°30'15"E) to standard azimuth values (0-360°).

            Args:
                side: Primary direction ('North', 'South', 'East', 'West')
                deg: Degrees component
                minutes: Minutes component
                sec: Seconds component
                dir_val: Quadrant indicator (1=SE, 2=NE, 3=SW, 4=NW)

            Returns:
                Azimuth in decimal degrees (0-360)
            """
            dec_val_base = deg + minutes / 60 + sec / 3600
            side_lower = side.lower()

            # Base orientations for each side
            if 'west' in side_lower:
                base_azimuth = 90
            elif 'east' in side_lower:
                base_azimuth = 270
            elif 'north' in side_lower:
                if dir_val in [3, 2]:  # SW, NE
                    base_azimuth = 90
                else:  # SE, NW
                    base_azimuth = 270
            elif 'south' in side_lower:
                if dir_val in [4, 1]:  # NW, SE
                    base_azimuth = 90
                else:  # NE, SW
                    base_azimuth = 270
            else:
                return dec_val_base

            # Determine if we add or subtract the bearing
            if ((side_lower.startswith('west') and dir_val in [4, 1]) or
                    (side_lower.startswith('east') and dir_val in [4, 1]) or
                    (side_lower.startswith('north') and dir_val not in [3, 2]) or
                    (side_lower.startswith('south') and dir_val in [4, 1])):
                return base_azimuth + dec_val_base
            else:
                return base_azimuth - dec_val_base

        def convert_conc(sec: float, ts: float, ts_dir: str, rng: float,
                         rng_dir: str, baseline: str) -> str:
            """Convert PLSS components to concatenated format.

            Args:
                sec: Section number
                ts: Township number
                ts_dir: Township direction code
                rng: Range number
                rng_dir: Range direction code
                baseline: Baseline code

            Returns:
                9-character concatenated string (e.g., "0101N01WU")
            """
            translations = {
                'rng': {'2': 'W', '1': 'E'},
                'township': {'2': 'S', '1': 'N'},
                'baseline': {'2': 'U', '1': 'S'},
                'alignment': {'1': 'SE', '2': 'NE', '3': 'SW', '4': 'NW'}
            }
            section = str(int(float(sec))).zfill(2)
            township = str(int(float(ts))).zfill(2)
            rng = str(int(float(rng))).zfill(2)

            # Handle direction codes (which might also be floats)
            ts_dir = str(ts_dir)
            rng_dir = str(rng_dir)
            baseline = str(baseline)

            # Translate direction codes
            ts_dir = translations.get('township', {}).get(ts_dir, ts_dir).upper()
            rng_dir = translations.get('rng', {}).get(rng_dir, rng_dir).upper()
            baseline = translations.get('baseline', {}).get(baseline, baseline).upper()

            return "".join([section, township, ts_dir, rng, rng_dir, baseline])

        def find_relevant_datasets() -> pd.core.groupby.DataFrameGroupBy:
            """Find plat data for the surface location section.

            Returns:
                Grouped DataFrame by section code and version.
            """
            first_plat = self.loc_df[self.loc_df['zone_name'].str.contains('Surface')]
            first_plat['conc'] = first_plat.apply(
                lambda row: convert_conc(row['section'], row['township'], row['township_dir'],
                                         row['rng'], row['rng_dir'], row['baseline']), axis=1)
            query = f"select * from section_plat_data where new_code = '{first_plat['conc'].iloc[0]}'"
            output = pd.read_sql(query, self.conn).drop_duplicates(keep="first")
            output = output.astype({"Length": float, "Degrees": float, "Minutes": float, "Seconds": float})
            output = output.astype({"Minutes": int, "Seconds": int})
            grouped = output.groupby(['new_code', 'Version'])
            return grouped

        # Get survey types and surface location
        citing_types = self.survey_dx['CitingType'].unique()
        shl_latlon = list(self.survey_dx.head(1)[['SurfaceLatitude', 'SurfaceLongitude']].iloc[0])
        ref_lst = ['_true_dx', '_grid_dx']
        type_map = {'planned': 'pln_df', 'asdrilled': 'drl_df'}

        # Get plat data for surface section
        first_plat_rel = find_relevant_datasets()
        _, first_plat_rel_out = next(iter(first_plat_rel))
        first_plat_coords = convert_to_pts(first_plat_rel_out)

        # Create plat editor process for each survey type and reference combination
        for citing in citing_types:
            key = type_map.get(citing.lower())
            if key:
                for ref in ref_lst:
                    attr_name = f"plat_editor_process_{key}{ref}"
                    used_data = self.cl_dx_dict[f"{key}{ref}"].clearance_data
                    setattr(self, attr_name, PlatEditorProcess(
                        conn=self.conn,
                        plat_df=first_plat_rel,
                        plat_coords=first_plat_coords,
                        shl=shl_latlon,
                        well_df=used_data
                    ))

    def set_plat_data(self, plat_data: pd.DataFrame | None) -> None:
        """Set the plat boundary data for the well.

        Args:
            plat_data: DataFrame containing plat coordinates or None.
        """
        self.plat_df = plat_data

    def get_plat_data(self) -> pd.DataFrame:
        """Get the current plat boundary data.

        Returns:
            DataFrame containing plat coordinates.
        """
        return self.plat_df

    def set_survey(self, survey: pd.DataFrame) -> None:
        """Set the directional survey data.

        Args:
            survey: DataFrame containing survey points.
        """
        self.survey_dx = survey

    def get_survey(self) -> pd.DataFrame:
        """Get the current directional survey data.

        Returns:
            DataFrame containing survey points.
        """
        return self.survey_dx

    def set_north_ref(self, north_ref: str) -> None:
        """Set the north reference type.

        Args:
            north_ref: 't' for true north, 'g' for grid north.
        """
        self.north_ref = north_ref

    def set_well_elevation(self, well_elevation: float) -> None:
        """Set the well surface elevation.

        Args:
            well_elevation: Elevation in feet.
        """
        self.well_elevation = well_elevation

    def set_starting_point(self, starting_point: list[float]) -> None:
        """Set new surface location for all surveys.

        Args:
            starting_point: [latitude, longitude] in decimal degrees.
        """
        self.survey_dx['SurfaceLatitude'] = starting_point[0]
        self.survey_dx['SurfaceLongitude'] = starting_point[1]

    def process_plat_editor(self) -> None:
        """Process edited plat coordinates and recalculate clearances.

        This method retrieves user-edited plat data from the UI and triggers
        a complete recalculation of all clearance values.
        """
        self.plat_editor.retrieve_all_data()
        self.rerun_plats()

    def load_surveys(self) -> None:
        """Initial survey load with full processing pipeline.

        This method performs the complete initialization sequence:
        1. Process survey data and calculate well paths
        2. Retrieve plat boundaries based on well locations
        3. Build plat editor UI
        4. Calculate clearances for all survey/reference combinations
        """
        # Run survey calculations
        self.surveys_dict, self.spec_surveys_dict, self.survey_parameters = self._run_survey_logic(self.well_elevation,
                                                                                                   self.north_ref)

        # Get initial plats & locations
        plats, locs = self.retrieve_location_data(self.surveys_dict)
        self.plat_df = plats
        self.loc_df = locs

        # Build the editor UI from the initial plat set
        self.plat_editor = PlatCoordEditor(self.plat_df, self.ui, self.conn)

        # Calculate clearances
        self._run_clearance()

    def rerun_surveys(self) -> None:
        """Reprocess surveys after changes with intelligent plat merging.

        When survey data changes, this method:
        1. Recalculates survey paths
        2. Finds any new plat sections crossed
        3. Merges new plats with existing ones
        4. Rebuilds UI and recalculates clearances
        """
        # Recompute surveys
        self.surveys_dict, self.spec_surveys_dict, self.survey_parameters = self._run_survey_logic(self.well_elevation,
                               self.north_ref)

        # Find new plats and merge with existing
        new_plats, new_locs = self.retrieve_location_data(self.surveys_dict)
        df = pd.concat([self.plat_df, new_plats])
        first_col = df.columns[0]
        df = df.drop_duplicates(subset=[first_col], keep='first')
        self.plat_df = df.reset_index(drop=True)

        # Merge location data
        self.loc_df = pd.concat([self.loc_df, new_locs]).drop_duplicates().reset_index(drop=True)

        # Rebuild editor and recalculate
        self.plat_editor = PlatCoordEditor(self.plat_df, self.ui, self.conn)
        self._run_clearance()

    def rerun_plats(self) -> None:
        """Reprocess after plat coordinate edits.

        This method handles the case where the user has manually edited
        plat coordinates in the UI. It retrieves the edited data and
        recalculates all clearances without changing surveys.
        """
        # Pull edited plat set from the editor
        edited_plats = self.plat_editor.section_df

        # Overwrite working plat_df
        self.plat_df = edited_plats

        # Recalculate clearances
        self._run_clearance()

    def _run_survey_logic(self, well_elevation, north_ref) -> tuple[Any, Any, Any]:
        """Execute survey processing with type enforcement.

        This internal method ensures all survey data has correct types
        and processes it through the survey calculation pipeline.
        """
        # Force correct data types
        df = self.survey_dx
        df['measured_depth'] = df['measured_depth'].astype(float)
        df['inclination'] = df['inclination'].astype(float)
        df['azimuth'] = df['azimuth'].astype(float)
        df['SurfaceLatitude'] = df['SurfaceLatitude'].astype(float)
        df['SurfaceLongitude'] = df['SurfaceLongitude'].astype(float)

        # Process surveys
        surveys_dict, spec_surveys_dict, survey_parameters = self.retrieve_survey_data(df, well_elevation, north_ref)
        return surveys_dict, spec_surveys_dict, survey_parameters

    def _run_clearance(self) -> None:
        """Calculate clearances for all survey/plat combinations.

        This internal method uses the current survey paths and plat
        boundaries to calculate minimum clearances.
        """
        self.cl_dx_dict = self.retrieve_clearance_data(
            self.surveys_dict,
            self.plat_df
        )
        self.rel_plats.set_well_path_dict(self.cl_dx_dict)
        self.rel_plats.set_tsr_data(self.loc_df)

    def etools_process(self, *, preserve_plat: bool = False, new_plat: bool = False) -> None:
        """Legacy processing method maintained for compatibility.

        Args:
            preserve_plat: Whether to preserve existing plat data.
            new_plat: Whether this is a new plat requiring location retrieval.

        Note:
            This method is deprecated in favor of the more specific
            load_surveys(), rerun_surveys(), and rerun_plats() methods.
        """
        # Coerce column types
        self.survey_dx['measured_depth'] = self.survey_dx['measured_depth'].astype(float)
        self.survey_dx['inclination'] = self.survey_dx['inclination'].astype(float)
        self.survey_dx['azimuth'] = self.survey_dx['azimuth'].astype(float)
        self.survey_dx['SurfaceLatitude'] = self.survey_dx['SurfaceLatitude'].astype(float)
        self.survey_dx['SurfaceLongitude'] = self.survey_dx['SurfaceLongitude'].astype(float)

        # Process surveys
        self.surveys_dict, self.spec_surveys_dict, self.survey_parameters = self.retrieve_survey_data(
            self.survey_dx, self.well_elevation, self.north_ref
        )

        # Handle plat data based on flags
        if not preserve_plat:
            if not new_plat:
                # First time - get plats from locations
                self.plat_df_original, self.loc_df_new = self.retrieve_location_data(self.surveys_dict)
                self.plat_editor = PlatCoordEditor(self.plat_df_original, self.ui, self.conn)
            else:
                # Get edited plats
                updated = self.plat_editor.retrieve_all_data()
                self.plat_df = updated

            # Merge location data if new plat
            self.loc_df = pd.concat([self.loc_df, self.loc_df_new]).drop_duplicates()

        # Always recalculate clearances
        self.cl_dx_dict = self.retrieve_clearance_data(self.surveys_dict, self.plat_df)

    def reprocess_with_current_plat(self) -> None:
        """Convenience method to rerun surveys with current plat data."""
        self.rerun_surveys()

    def retrieve_survey_data(self, survey_dx: pd.DataFrame, well_elevation: float,
                             north_ref: str) -> tuple:
        """Process raw survey data into calculated well paths.

        Args:
            survey_dx: Raw survey DataFrame with MD, Inc, Azi
            well_elevation: Surface elevation in feet
            north_ref: North reference type

        Returns:
            Tuple of (surveys_dict, spec_surveys_dict, survey_parameters)
        """
        surveys_dict = SurveyProcessBase(self.api, self.lateral, self.db, survey_dx,
                                         well_elevation, north_ref)
        return surveys_dict.dx_dict, surveys_dict.dx_dict_spec_depths, surveys_dict.survey_parameters

    def retrieve_location_data(self, survey_dict: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Get plat boundaries for sections crossed by well paths.

        Args:
            survey_dict: Dictionary of processed survey data

        Returns:
            Tuple of (plat_df, loc_df) DataFrames
        """
        plat_output = TownShipAndRangeProcess(self.api, self.lateral, self.db,
                                              survey_dict, self.conn)
        return plat_output.plat_df, plat_output.loc_df

    def retrieve_clearance_data(self, survey_dict: dict, plat_df: pd.DataFrame) -> dict:
        """Calculate clearances for all survey/reference combinations.

        Args:
            survey_dict: Dictionary of survey data by type
            plat_df: DataFrame of plat boundaries

        Returns:
            Dictionary of ClearanceProcess objects keyed by survey type
        """
        clearance_dx_df_dict = {}
        for i, v in survey_dict.items():
            for j in ['true_dx', 'grid_dx']:
                ref_label = f"{i}_{j}"
                clearance_dx_df_dict[ref_label] = self.clearance_process(
                    getattr(survey_dict[i], j), plat_df
                )
        return clearance_dx_df_dict

    def clearance_process(self, df: pd.DataFrame, plat_df: pd.DataFrame) -> ClearanceProcess:
        """Create clearance calculation object for survey/plat combination.

        Args:
            df: Survey path DataFrame
            plat_df: Plat boundary DataFrame

        Returns:
            ClearanceProcess object with calculated clearances
        """
        return ClearanceProcess(df, plat_df, self.conn)


class PointChecker:
    """Utility for checking distances between points and line segments.

    This class provides tools for measuring the perpendicular distance from
    a point to a line segment, useful for clearance verification and quality
    control. It includes both calculation and visualization capabilities.

    Attributes:
        ui: Reference to the main UI
        figure_check: Matplotlib figure for visualization
        ax_check: Matplotlib axes for plotting
        canvas_check: Canvas widget for Qt integration
    """

    def __init__(self, ui) -> None:
        """Initialize the point checker with UI references and plot setup.

        Args:
            ui: Main application UI reference
        """
        self.ui = ui

        # Connect all input fields to the calculation method
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
        self.ui.check_pt_e.editingFinished.connect(self.collect_data)
        self.ui.check_pt_n.editingFinished.connect(self.collect_data)

        # Set up matplotlib figure for visualization
        self.figure_check, self.ax_check = plt.subplots()
        self.canvas_check = self.figure_check.canvas
        self.ui.check_pt_graphic_display.addWidget(self.canvas_check)

        # Initialize plot elements
        self.check_pts = self.ax_check.scatter([], [],
                                               marker='o',
                                               color='black',
                                               s=25,
                                               zorder=1000)
        self.check_seg_plot, = self.ax_check.plot(
            [], [], color='red', linewidth=1, zorder=5)

        self.segment = None
        self.check_pt = None

    def set_segment(self, segment: list) -> None:
        """Set the line segment for distance calculations.

        Args:
            segment: List of two points defining the segment
        """
        self.segment = segment

    def set_check_pt(self, check_pt: tuple) -> None:
        """Set the point to check distance from.

        Args:
            check_pt: (x, y) coordinates of the point
        """
        self.check_pt = check_pt

    def gather_deg_pts(self) -> tuple[tuple, tuple, tuple]:
        """Convert degree/minute/second inputs to UTM coordinates.

        This method reads DMS (degrees, minutes, seconds) values from the UI
        and converts them to decimal degrees, then to UTM coordinates.

        Returns:
            Tuple of three UTM coordinate pairs: (point_a, point_b, check_point)

        Raises:
            ValueError: If any required field is empty
        """

        def converter(label: str, id: str) -> float:
            """Convert DMS to decimal degrees for a single coordinate."""
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

        # Convert DMS to decimal degrees
        lat_dec_a = converter('lat', 'a')
        lon_dec_a = -abs(converter('lon', 'a'))  # Western hemisphere negative
        lat_dec_b = converter('lat', 'b')
        lon_dec_b = -abs(converter('lon', 'b'))
        e_dec_pt = float(self.ui.check_pt_e.text())
        n_dec_pt = float(self.ui.check_pt_n.text())

        # Convert to UTM
        output_a = utm.from_latlon(lat_dec_a, lon_dec_a)[:2]
        output_b = utm.from_latlon(lat_dec_b, lon_dec_b)[:2]
        output_pt = self.check_if_utm_or_latlon(e_dec_pt, n_dec_pt)

        return output_a, output_b, output_pt

    def gather_pts(self) -> tuple[tuple, tuple, tuple] | None:
        """Gather point coordinates from UI fields with automatic format detection.

        This method attempts to read coordinates from decimal degree fields first,
        falling back to DMS fields if decimal fields are empty. It automatically
        detects whether inputs are in UTM or lat/lon format.

        Returns:
            Tuple of three coordinate pairs in UTM format, or None if invalid
        """
        fields = [
            self.ui.a_check_pt_e.text(),
            self.ui.a_check_pt_n.text(),
            self.ui.b_check_pt_e.text(),
            self.ui.b_check_pt_n.text(),
            self.ui.check_pt_e.text(),
            self.ui.check_pt_n.text()
        ]

        # If any field is empty, use DMS inputs
        if any(not field.strip() for field in fields):
            try:
                return self.gather_deg_pts()
            except ValueError as e:
                pass

        # Otherwise, proceed with decimal conversion
        try:
            e_dec_1 = float(self.ui.a_check_pt_e.text())
            n_dec_1 = float(self.ui.a_check_pt_n.text())
            e_dec_2 = float(self.ui.b_check_pt_e.text())
            n_dec_2 = float(self.ui.b_check_pt_n.text())
            e_dec_pt = float(self.ui.check_pt_e.text())
            n_dec_pt = float(self.ui.check_pt_n.text())

            # Convert each point to UTM if needed
            output_a = self.check_if_utm_or_latlon(e_dec_1, n_dec_1)
            output_b = self.check_if_utm_or_latlon(e_dec_2, n_dec_2)
            output_pt = self.check_if_utm_or_latlon(e_dec_pt, n_dec_pt)

            return output_a, output_b, output_pt
        except ValueError as f:
            # Try DMS as last resort
            try:
                return self.gather_deg_pts()
            except ValueError:
                pass

    def check_if_utm_or_latlon(self, x_coord: float, y_coord: float) -> tuple[float, float] | str:
        """Automatically detect coordinate system and convert to UTM if needed.

        This method uses value ranges to determine if coordinates are in
        latitude/longitude or UTM format, converting to UTM as needed.

        Args:
            x_coord: X coordinate (easting or latitude)
            y_coord: Y coordinate (northing or longitude)

        Returns:
            UTM coordinate tuple (easting, northing) or 'invalid'

        Notes:
            - Utah lat/lon ranges: 37-42°N, 109-114°W
            - Utah UTM ranges: 140,000-800,000 E, 3,800,000-4,800,000 N
        """
        try:
            x = float(x_coord)
            y = float(y_coord)

            # Check if lat/lon (with special handling for Utah coordinates)
            if (-180 <= y <= 180) and (-90 <= x <= 90):
                if (-114 <= y <= -109) and (37 <= x <= 42):
                    y = abs(y) * -1  # Ensure negative for western hemisphere
                    return utm.from_latlon(x, y)[:2]

            # Check if UTM
            if (140000 <= x <= 800000) and (3800000 <= y <= 4800000):
                return (x, y)

            return 'invalid'

        except ValueError:
            return 'invalid'

    def collect_data(self) -> None:
        """Collect input data, calculate distance, and update visualization.

        This method is called whenever any input field changes. It gathers
        all coordinates, calculates the perpendicular distance from the point
        to the line segment, and updates both the result display and the
        visualization plot.
        """
        global pt_a, pt_b, pt_used
        try:
            pt_a, pt_b, pt_used = self.gather_pts()
        except TypeError:
            pass

        try:
            # Create line and point geometries
            line = LineString([pt_a, pt_b])
            point = Point(pt_used)

            # Compute the distance in meters and convert to feet
            distance = point.distance(line)
            self.ui.check_pt_result_box.setText(f"{round(distance / 0.3048, 3)} ft")

            # Update visualization
            self.draw_graphic_for_checked_pts([pt_a, pt_b], pt_used)
        except ValueError:
            pass

    def draw_graphic_for_checked_pts(self, segment_pts: list, check_pt: tuple) -> None:
        """Update the visualization plot with segment and point.

        Args:
            segment_pts: List of two points defining the line segment
            check_pt: Point to check distance from
        """
        # Prepare data for plotting
        all_pts = segment_pts + [check_pt]
        x, y = LineString(segment_pts).xy

        # Update plot data
        self.check_seg_plot.set_data(x, y)
        self.check_pts.set_offsets(all_pts)

        # Refresh plot with equal aspect ratio
        self.ax_check.relim()
        self.ax_check.axis('equal')
        self.ax_check.autoscale_view()

        self.canvas_check.draw()


class ZoomPan:
    """Provides interactive zoom and pan functionality for matplotlib plots.

    This class implements mouse-based navigation for matplotlib figures,
    including scroll wheel zooming and click-and-drag panning. It also
    manages dynamic text scaling to maintain readability at different zoom levels.

    Attributes:
        press: Current mouse press state
        cur_xlim: Current x-axis limits
        cur_ylim: Current y-axis limits
        text_objects: List of text annotations to scale with zoom
    """

    def __init__(self) -> None:
        """Initialize zoom/pan controller with default state."""
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

    def zoom_factory(self, ax: plt.Axes, base_scale: float = 2.0):
        """Create zoom functionality for a matplotlib axes.

        Args:
            ax: Matplotlib axes to add zoom to
            base_scale: Zoom factor for each scroll event

        Returns:
            The zoom event handler function
        """

        def zoom(event):
            """Handle mouse scroll events for zooming."""
            if event.inaxes != ax:
                return

            cur_xlim = ax.get_xlim()
            cur_ylim = ax.get_ylim()

            xdata = event.xdata  # get event x location
            ydata = event.ydata  # get event y location

            if event.button == 'down':
                # Zoom in
                scale_factor = 1 / base_scale
            elif event.button == 'up':
                # Zoom out
                scale_factor = base_scale
            else:
                # Unknown scroll direction
                scale_factor = 1

            # Calculate new limits centered on mouse position
            new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
            new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor

            relx = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
            rely = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])

            ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * (relx)])
            ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * (rely)])

            # Update text scaling based on zoom level
            scale_factor = ax.get_xlim()[1] - ax.get_xlim()[0]
            for text in self.text_objects:
                new_fontsize = 12 / scale_factor * 2500  # Scale text appropriately
                text.set_fontsize(new_fontsize)
            ax.figure.canvas.draw()

        fig = ax.get_figure()
        fig.canvas.mpl_connect('scroll_event', zoom)
        return zoom

    def add_text(self, ax: plt.Axes, x: float, y: float, text_str: str) -> None:
        """Add text that scales with zoom level.

        Args:
            ax: Matplotlib axes to add text to
            x: X coordinate for text placement
            y: Y coordinate for text placement
            text_str: Text content to display
        """
        scale_factor = ax.get_xlim()[1] - ax.get_xlim()[0]
        text = ax.text(x, y, text_str, ha='center', va='center',
                       fontsize=12 / scale_factor * 2500, transform=ax.transData)
        self.text_objects.append(text)

    def pan_factory(self, ax: plt.Axes):
        """Create pan functionality for a matplotlib axes.

        Args:
            ax: Matplotlib axes to add panning to

        Returns:
            The motion event handler function
        """

        def onPress(event):
            """Handle mouse button press for pan start."""
            if event.inaxes != ax:
                return
            self.cur_xlim = ax.get_xlim()
            self.cur_ylim = ax.get_ylim()
            self.press = self.x0, self.y0, event.xdata, event.ydata
            self.x0, self.y0, self.xpress, self.ypress = self.press

        def onRelease(event):
            """Handle mouse button release for pan end."""
            self.press = None
            ax.figure.canvas.draw()

        def onMotion(event):
            """Handle mouse motion for panning."""
            if self.press is None:
                return
            if event.inaxes != ax:
                return

            # Calculate pan distance
            dx = event.xdata - self.xpress
            dy = event.ydata - self.ypress
            self.cur_xlim -= dx
            self.cur_ylim -= dy

            # Update plot limits
            ax.set_xlim(self.cur_xlim)
            ax.set_ylim(self.cur_ylim)
            ax.figure.canvas.draw()

        fig = ax.get_figure()

        # Connect event handlers
        fig.canvas.mpl_connect('button_press_event', onPress)
        fig.canvas.mpl_connect('button_release_event', onRelease)
        fig.canvas.mpl_connect('motion_notify_event', onMotion)

        return onMotion


def except_hook(cls: type, exception: Exception, tb) -> None:
    """Enhanced exception handler for debugging Qt applications.

    This custom exception handler provides detailed error information
    without calling the default handler, preventing error cascades.

    Args:
        cls: Exception class
        exception: Exception instance
        tb: Traceback object
    """
    print(f"Exception Type: {cls.__name__}")
    print(f"Exception Message: {str(exception)}")
    print("Traceback:")
    traceback.print_tb(tb)


if __name__ == "__main__":
    """Main entry point for the application with comprehensive error handling."""
    try:
        # Install custom exception handler
        sys.excepthook = except_hook

        # Create Qt application
        app = QApplication(sys.argv)
        print("QApplication created successfully")

        # Create main window
        w = ETools()
        print("ETools instance created successfully")

        # Show window
        w.show()
        print("Widget shown successfully")

        # Run application event loop
        sys.exit(app.exec_())

    except Exception as e:
        print(f"Python Exception: {type(e).__name__}: {e}")
        traceback.print_exc()
    except SystemExit:
        print("Application exited normally")
    except:
        print("Unknown error occurred")
        traceback.print_exc()
