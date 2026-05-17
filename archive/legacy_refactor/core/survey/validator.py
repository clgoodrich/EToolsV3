"""
Survey data validation for EToolsV3.

This module provides comprehensive validation for directional survey data.
"""

from typing import List, Tuple
import pandas as pd
import numpy as np

from config.logging_config import get_logger
from utils.errors import ValidationError

logger = get_logger(__name__)


class SurveyValidator:
    """Validates directional survey data for correctness and quality."""

    def __init__(
        self,
        max_dogleg: float = 10.0,
        max_inclination: float = 180.0,
        min_station_spacing: float = 10.0
    ):
        """
        Initialize survey validator.

        Args:
            max_dogleg: Maximum acceptable dogleg severity (deg/100ft).
            max_inclination: Maximum inclination (degrees).
            min_station_spacing: Minimum spacing between stations (feet).
        """
        self.max_dogleg = max_dogleg
        self.max_inclination = max_inclination
        self.min_station_spacing = min_station_spacing
        self.logger = logger

    def validate(self, survey_df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate survey data and return status with warnings.

        Args:
            survey_df: Survey DataFrame to validate.

        Returns:
            Tuple of (is_valid, list_of_warnings).
        """
        warnings = []

        # Check required columns
        required = ['measured_depth', 'inclination', 'azimuth']
        missing = [col for col in required if col not in survey_df.columns]
        if missing:
            raise ValidationError(f"Missing required columns: {', '.join(missing)}")

        # Check for empty data
        if survey_df.empty:
            raise ValidationError("Survey data is empty")

        # Check for NaN values
        if survey_df[required].isnull().any().any():
            warnings.append("Survey contains null values")

        # Validate measured depth
        warnings.extend(self._validate_measured_depth(survey_df))

        # Validate inclination
        warnings.extend(self._validate_inclination(survey_df))

        # Validate azimuth
        warnings.extend(self._validate_azimuth(survey_df))

        # Check station spacing
        warnings.extend(self._check_station_spacing(survey_df))

        # Check for excessive dogleg
        if 'dogleg_severity' in survey_df.columns:
            warnings.extend(self._check_dogleg(survey_df))

        is_valid = len(warnings) == 0
        return is_valid, warnings

    def _validate_measured_depth(self, survey_df: pd.DataFrame) -> List[str]:
        """Validate measured depth values."""
        warnings = []

        md = survey_df['measured_depth']

        # Check for negative values
        if (md < 0).any():
            warnings.append("Measured depth contains negative values")

        # Check monotonicity
        if not md.is_monotonic_increasing:
            warnings.append("Measured depth is not monotonically increasing")

        # Check for duplicates
        if md.duplicated().any():
            warnings.append("Measured depth contains duplicate values")

        return warnings

    def _validate_inclination(self, survey_df: pd.DataFrame) -> List[str]:
        """Validate inclination values."""
        warnings = []

        inc = survey_df['inclination']

        # Check range
        if (inc < 0).any():
            warnings.append("Inclination contains negative values")

        if (inc > self.max_inclination).any():
            max_val = inc.max()
            warnings.append(f"Inclination exceeds maximum ({max_val:.1f}° > {self.max_inclination}°)")

        return warnings

    def _validate_azimuth(self, survey_df: pd.DataFrame) -> List[str]:
        """Validate azimuth values."""
        warnings = []

        azi = survey_df['azimuth']

        # Check range
        if (azi < 0).any():
            warnings.append("Azimuth contains negative values")

        if (azi >= 360).any():
            warnings.append("Azimuth contains values >= 360°")

        return warnings

    def _check_station_spacing(self, survey_df: pd.DataFrame) -> List[str]:
        """Check for adequate station spacing."""
        warnings = []

        if len(survey_df) < 2:
            return warnings

        md_diff = survey_df['measured_depth'].diff()[1:]

        # Check for very close stations
        close_stations = (md_diff < self.min_station_spacing).sum()
        if close_stations > 0:
            warnings.append(
                f"{close_stations} stations closer than {self.min_station_spacing} ft"
            )

        return warnings

    def _check_dogleg(self, survey_df: pd.DataFrame) -> List[str]:
        """Check for excessive dogleg severity."""
        warnings = []

        dls = survey_df['dogleg_severity']

        if (dls > self.max_dogleg).any():
            max_dls = dls.max()
            warnings.append(
                f"Excessive dogleg severity detected ({max_dls:.2f}° > {self.max_dogleg}°/100ft)"
            )

        return warnings
