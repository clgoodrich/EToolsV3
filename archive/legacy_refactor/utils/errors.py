"""
Custom exception hierarchy for EToolsV3.

This module defines all custom exceptions used throughout the application.
Exceptions are organized hierarchically for easy catching and handling.
"""

from typing import Optional, Any


class EToolsError(Exception):
    """
    Base exception for all ETools application errors.

    All custom exceptions inherit from this class, making it easy to catch
    all application-specific errors with a single except clause.
    """

    def __init__(self, message: str, details: Optional[Any] = None):
        """
        Initialize exception.

        Args:
            message: Human-readable error message.
            details: Optional additional details (e.g., original exception, context).
        """
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.details:
            return f"{self.message} (Details: {self.details})"
        return self.message


# Database Errors

class DatabaseError(EToolsError):
    """Base class for all database-related errors."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""
    pass


class DatabaseQueryError(DatabaseError):
    """Raised when a database query fails."""
    pass


class DatabaseTimeoutError(DatabaseError):
    """Raised when a database operation times out."""
    pass


# Validation Errors

class ValidationError(EToolsError):
    """Base class for all validation errors."""
    pass


class InvalidAPINumberError(ValidationError):
    """Raised when API number format is invalid."""

    def __init__(self, api: str):
        super().__init__(
            f"Invalid API number format: '{api}'. Expected 10-digit numeric string.",
            details={'api': api}
        )


class InvalidSurveyDataError(ValidationError):
    """Raised when survey data is invalid or incomplete."""
    pass


class InvalidCoordinateError(ValidationError):
    """Raised when coordinate values are invalid."""
    pass


class MissingRequiredFieldError(ValidationError):
    """Raised when a required field is missing from data."""

    def __init__(self, field_name: str, context: Optional[str] = None):
        message = f"Required field '{field_name}' is missing"
        if context:
            message += f" in {context}"
        super().__init__(message, details={'field': field_name, 'context': context})


# Calculation Errors

class CalculationError(EToolsError):
    """Base class for all calculation errors."""
    pass


class SurveyProcessingError(CalculationError):
    """Raised when survey processing fails."""
    pass


class ClearanceCalculationError(CalculationError):
    """Raised when clearance calculation fails."""
    pass


class CoordinateTransformationError(CalculationError):
    """Raised when coordinate transformation fails."""
    pass


class KOPDetectionError(CalculationError):
    """Raised when KOP detection fails."""
    pass


class MagneticFieldError(CalculationError):
    """Raised when magnetic field calculation fails."""
    pass


# Data Not Found Errors

class DataNotFoundError(EToolsError):
    """Base class for data not found errors."""
    pass


class WellNotFoundError(DataNotFoundError):
    """Raised when well is not found in database."""

    def __init__(self, api: str, lateral: Optional[str] = None):
        message = f"Well not found: API={api}"
        if lateral:
            message += f", Lateral={lateral}"
        super().__init__(message, details={'api': api, 'lateral': lateral})


class SurveyNotFoundError(DataNotFoundError):
    """Raised when survey data is not found."""

    def __init__(self, api: str, lateral: str):
        super().__init__(
            f"No survey data found for API={api}, Lateral={lateral}",
            details={'api': api, 'lateral': lateral}
        )


class PlatNotFoundError(DataNotFoundError):
    """Raised when plat is not found."""
    pass


# File Errors

class FileError(EToolsError):
    """Base class for file-related errors."""
    pass


class PDFParseError(FileError):
    """Raised when PDF parsing fails."""
    pass


class ExcelGenerationError(FileError):
    """Raised when Excel file generation fails."""
    pass


class ConfigurationError(FileError):
    """Raised when configuration file is invalid or missing."""
    pass


# Business Logic Errors

class BusinessLogicError(EToolsError):
    """Base class for business logic errors."""
    pass


class InvalidOperationError(BusinessLogicError):
    """Raised when an operation is not valid in the current context."""
    pass


class UnsupportedFeatureError(BusinessLogicError):
    """Raised when a feature is not supported."""

    def __init__(self, feature: str):
        super().__init__(
            f"Feature not supported: {feature}",
            details={'feature': feature}
        )


# UI Errors

class UIError(EToolsError):
    """Base class for UI-related errors."""
    pass


class VisualizationError(UIError):
    """Raised when plot/visualization generation fails."""
    pass


class TableModelError(UIError):
    """Raised when table model operations fail."""
    pass


# Utility Functions

def format_error_for_user(error: Exception) -> str:
    """
    Format an error message for display to the user.

    Converts technical exceptions into user-friendly messages.

    Args:
        error: Exception to format.

    Returns:
        User-friendly error message.
    """
    if isinstance(error, WellNotFoundError):
        return f"Well not found. Please check the API number and lateral name."

    elif isinstance(error, SurveyNotFoundError):
        return f"No survey data found for this well."

    elif isinstance(error, DatabaseConnectionError):
        return "Unable to connect to database. Please check your connection settings."

    elif isinstance(error, InvalidAPINumberError):
        return "Invalid API number format. Please enter a 10-digit number."

    elif isinstance(error, PDFParseError):
        return "Unable to parse PDF file. Please check the file format."

    elif isinstance(error, ValidationError):
        return f"Validation error: {error.message}"

    elif isinstance(error, CalculationError):
        return f"Calculation error: {error.message}"

    elif isinstance(error, DatabaseError):
        return f"Database error: {error.message}"

    elif isinstance(error, EToolsError):
        return error.message

    else:
        return f"An unexpected error occurred: {str(error)}"


def is_user_error(error: Exception) -> bool:
    """
    Determine if an error is caused by user input.

    Args:
        error: Exception to check.

    Returns:
        True if error is likely caused by user input, False otherwise.
    """
    user_error_types = (
        ValidationError,
        InvalidAPINumberError,
        WellNotFoundError,
        SurveyNotFoundError,
        DataNotFoundError
    )
    return isinstance(error, user_error_types)


def should_log_traceback(error: Exception) -> bool:
    """
    Determine if full traceback should be logged for an error.

    User errors typically don't need full tracebacks, while system errors do.

    Args:
        error: Exception to check.

    Returns:
        True if traceback should be logged, False otherwise.
    """
    return not is_user_error(error)
