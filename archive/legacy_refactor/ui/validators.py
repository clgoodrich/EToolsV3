"""
UI input validators for EToolsV3.

This module provides validation for user input in the UI.
"""

from PyQt5.QtGui import QValidator
from PyQt5.QtCore import QRegExp
import re


class APINumberValidator(QValidator):
    """Validator for 10-digit API numbers."""

    def validate(self, input_str: str, pos: int):
        """Validate API number input."""
        # Allow empty or partial input
        if not input_str:
            return QValidator.Intermediate, input_str, pos

        # Check if all digits
        if not input_str.isdigit():
            return QValidator.Invalid, input_str, pos

        # Check length
        if len(input_str) > 10:
            return QValidator.Invalid, input_str, pos

        if len(input_str) == 10:
            return QValidator.Acceptable, input_str, pos

        return QValidator.Intermediate, input_str, pos


class CoordinateValidator(QValidator):
    """Validator for coordinate values (latitude, longitude, etc.)."""

    def __init__(self, min_value: float = -180.0, max_value: float = 180.0, parent=None):
        """
        Initialize coordinate validator.

        Args:
            min_value: Minimum allowed value.
            max_value: Maximum allowed value.
            parent: Parent QObject.
        """
        super().__init__(parent)
        self.min_value = min_value
        self.max_value = max_value

    def validate(self, input_str: str, pos: int):
        """Validate coordinate input."""
        if not input_str or input_str == '-':
            return QValidator.Intermediate, input_str, pos

        try:
            value = float(input_str)

            if self.min_value <= value <= self.max_value:
                return QValidator.Acceptable, input_str, pos
            else:
                return QValidator.Invalid, input_str, pos

        except ValueError:
            return QValidator.Invalid, input_str, pos


class DepthValidator(QValidator):
    """Validator for depth values (positive numbers)."""

    def validate(self, input_str: str, pos: int):
        """Validate depth input."""
        if not input_str:
            return QValidator.Intermediate, input_str, pos

        try:
            value = float(input_str)

            if value >= 0:
                return QValidator.Acceptable, input_str, pos
            else:
                return QValidator.Invalid, input_str, pos

        except ValueError:
            return QValidator.Invalid, input_str, pos


def validate_api_number(api: str) -> tuple[bool, str]:
    """
    Validate API number format.

    Args:
        api: API number string.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not api:
        return False, "API number is required"

    if not api.isdigit():
        return False, "API number must contain only digits"

    if len(api) != 10:
        return False, "API number must be exactly 10 digits"

    return True, ""


def validate_lateral_name(lateral: str) -> tuple[bool, str]:
    """
    Validate lateral name.

    Args:
        lateral: Lateral name string.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not lateral:
        return False, "Lateral name is required"

    # Basic validation - adjust based on actual requirements
    if len(lateral) > 50:
        return False, "Lateral name too long (max 50 characters)"

    return True, ""
