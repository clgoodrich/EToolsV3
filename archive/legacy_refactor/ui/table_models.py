"""
PyQt5 table models for EToolsV3.

This module provides QAbstractTableModel implementations for displaying data.
"""

from typing import Optional
import pandas as pd
from PyQt5.QtCore import QAbstractTableModel, Qt, QModelIndex


class PandasTableModel(QAbstractTableModel):
    """Table model for displaying pandas DataFrames in QTableView."""

    def __init__(self, data: pd.DataFrame, parent=None):
        """
        Initialize table model.

        Args:
            data: Pandas DataFrame to display.
            parent: Parent QObject.
        """
        super().__init__(parent)
        self._data = data.copy()

    def rowCount(self, parent=QModelIndex()) -> int:
        """Return number of rows."""
        return len(self._data)

    def columnCount(self, parent=QModelIndex()) -> int:
        """Return number of columns."""
        return len(self._data.columns)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        """Return data for given index and role."""
        if not index.isValid():
            return None

        if role == Qt.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]

            # Format numeric values
            if isinstance(value, (int, float)):
                if pd.isna(value):
                    return ''
                return f'{value:.2f}' if isinstance(value, float) else str(value)

            return str(value)

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):
        """Return header data."""
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._data.columns[section])
            if orientation == Qt.Vertical:
                return str(self._data.index[section])

        return None

    def update_data(self, data: pd.DataFrame):
        """Update model data."""
        self.beginResetModel()
        self._data = data.copy()
        self.endResetModel()


class SurveyTableModel(PandasTableModel):
    """Specialized table model for survey data."""

    def __init__(self, data: pd.DataFrame, parent=None):
        """Initialize survey table model."""
        # Select and reorder columns for display
        display_columns = [
            'measured_depth', 'inclination', 'azimuth',
            'tvd', 'northing', 'easting'
        ]

        available_columns = [col for col in display_columns if col in data.columns]

        if available_columns:
            display_data = data[available_columns].copy()
        else:
            display_data = data.copy()

        super().__init__(display_data, parent)


class ClearanceTableModel(PandasTableModel):
    """Specialized table model for clearance data."""

    def __init__(self, data: pd.DataFrame, parent=None):
        """Initialize clearance table model."""
        # Select and reorder columns for display
        display_columns = [
            'measured_depth', 'section_label',
            'fnl', 'fsl', 'fel', 'fwl',
            'min_clearance', 'min_clearance_direction'
        ]

        available_columns = [col for col in display_columns if col in data.columns]

        if available_columns:
            display_data = data[available_columns].copy()
        else:
            display_data = data.copy()

        super().__init__(display_data, parent)
