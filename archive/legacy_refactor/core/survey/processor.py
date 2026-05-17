"""
Survey trajectory processor for EToolsV3.

This module processes directional survey data using minimum curvature method
and integrates magnetic field and coordinate transformations.
"""

from typing import Optional, Tuple
import numpy as np
import pandas as pd
import welleng as we
from welleng.survey import Survey, SurveyHeader

from core.coordinates.converter import CoordinateConverter
from core.coordinates.magnetic_field import MagneticFieldCalculator
from data.models.survey import ProcessedSurvey, RawSurveyData, SurveyHeader as SurveyHeaderModel
from config.logging_config import get_logger
from config.settings import settings
from utils.errors import SurveyProcessingError, ValidationError

logger = get_logger(__name__)


class SurveyProcessor:
    """
    Processes directional survey data with minimum curvature calculations.

    Uses welleng library for trajectory calculations and integrates
    coordinate and magnetic field transformations.
    """

    def __init__(
        self,
        coord_converter: Optional[CoordinateConverter] = None,
        mag_calculator: Optional[MagneticFieldCalculator] = None
    ):
        """
        Initialize survey processor.

        Args:
            coord_converter: Coordinate converter instance. If None, creates new.
            mag_calculator: Magnetic field calculator. If None, creates new.
        """
        self.coord_converter = coord_converter or CoordinateConverter()
        self.mag_calculator = mag_calculator or MagneticFieldCalculator()
        self.logger = logger

    def process_survey(
        self,
        raw_survey: RawSurveyData,
        interpolate: bool = True,
        interpolation_step: float = 100.0
    ) -> ProcessedSurvey:
        """
        Process raw survey data into complete trajectory.

        Args:
            raw_survey: Raw survey data from database.
            interpolate: Whether to interpolate survey points.
            interpolation_step: Interpolation step size in feet.

        Returns:
            ProcessedSurvey with all calculations completed.

        Raises:
            SurveyProcessingError: If processing fails.
            ValidationError: If survey data is invalid.
        """
        try:
            self.logger.info(
                f"Processing survey for API={raw_survey.api_number}, "
                f"Lateral={raw_survey.lateral_name}"
            )

            # Validate survey data
            self._validate_survey_data(raw_survey.measurements)

            # Get magnetic field parameters
            declination, dip, b_total = self.mag_calculator.calculate_magnetic_field(
                latitude=raw_survey.surface_latitude,
                longitude=raw_survey.surface_longitude,
                altitude=raw_survey.surface_elevation * 0.3048  # Convert ft to meters
            )

            # Calculate grid convergence
            convergence = self.coord_converter.calculate_convergence_angle(
                raw_survey.surface_latitude,
                raw_survey.surface_longitude
            )

            self.logger.debug(
                f"Magnetic declination: {declination:.2f}°, "
                f"Convergence: {convergence:.2f}°"
            )

            # Determine north reference and adjust azimuths if needed
            survey_df = self._prepare_survey_for_calculation(
                raw_survey.measurements.copy(),
                raw_survey.north_reference,
                declination,
                convergence
            )

            # Calculate trajectory using welleng
            trajectory_df = self._calculate_trajectory_welleng(
                survey_df,
                raw_survey.surface_latitude,
                raw_survey.surface_longitude,
                raw_survey.surface_elevation,
                declination,
                dip,
                b_total,
                convergence,
                interpolate,
                interpolation_step
            )

            # Convert coordinates to multiple systems
            trajectory_df = self.coord_converter.convert_survey_coordinates(
                trajectory_df,
                raw_survey.surface_latitude,
                raw_survey.surface_longitude,
                convergence
            )

            # Create survey header
            header = SurveyHeaderModel(
                api_number=raw_survey.api_number,
                lateral_name=raw_survey.lateral_name,
                surface_latitude=raw_survey.surface_latitude,
                surface_longitude=raw_survey.surface_longitude,
                surface_elevation=raw_survey.surface_elevation,
                north_reference=raw_survey.north_reference,
                convergence_angle=convergence,
                magnetic_declination=declination,
                citing_type=raw_survey.citing_type
            )

            # Create processed survey object
            processed = ProcessedSurvey(
                header=header,
                data=trajectory_df,
                true_north_trajectory=trajectory_df.copy()
            )

            self.logger.info(
                f"Survey processed successfully: {len(trajectory_df)} points, "
                f"Total MD: {processed.total_md:.1f} ft"
            )

            return processed

        except ValidationError:
            raise
        except Exception as e:
            self.logger.error(f"Survey processing failed: {e}", exc_info=True)
            raise SurveyProcessingError(
                f"Failed to process survey: {str(e)}",
                details={'api': raw_survey.api_number, 'lateral': raw_survey.lateral_name}
            )

    def _validate_survey_data(self, survey_df: pd.DataFrame):
        """
        Validate survey data before processing.

        Args:
            survey_df: Survey DataFrame to validate.

        Raises:
            ValidationError: If validation fails.
        """
        required_columns = ['measured_depth', 'inclination', 'azimuth']

        # Check required columns
        missing = [col for col in required_columns if col not in survey_df.columns]
        if missing:
            raise ValidationError(
                f"Survey data missing required columns: {', '.join(missing)}"
            )

        # Check for empty data
        if survey_df.empty:
            raise ValidationError("Survey data is empty")

        # Check for NaN values
        if survey_df[required_columns].isnull().any().any():
            raise ValidationError("Survey data contains null values")

        # Check inclination range
        if (survey_df['inclination'] < 0).any() or (survey_df['inclination'] > 180).any():
            raise ValidationError("Inclination values out of range [0, 180]")

        # Check azimuth range
        if (survey_df['azimuth'] < 0).any() or (survey_df['azimuth'] >= 360).any():
            raise ValidationError("Azimuth values out of range [0, 360)")

        # Check measured depth is monotonically increasing
        if not survey_df['measured_depth'].is_monotonic_increasing:
            self.logger.warning("Measured depth is not monotonically increasing, sorting...")
            survey_df.sort_values('measured_depth', inplace=True)

    def _prepare_survey_for_calculation(
        self,
        survey_df: pd.DataFrame,
        north_reference: str,
        declination: float,
        convergence: float
    ) -> pd.DataFrame:
        """
        Prepare survey data by converting azimuths to true north.

        Args:
            survey_df: Survey DataFrame.
            north_reference: Original north reference.
            declination: Magnetic declination.
            convergence: Grid convergence.

        Returns:
            Survey DataFrame with azimuths in true north.
        """
        df = survey_df.copy()

        # Convert azimuths to true north if needed
        if north_reference.lower() in ['magnetic', 'mag', 'm']:
            self.logger.debug("Converting magnetic north to true north")
            df['azimuth'] = df['azimuth'].apply(
                lambda az: self.mag_calculator.apply_declination_to_azimuth(az, declination)
            )
        elif north_reference.lower() in ['grid', 'g']:
            self.logger.debug("Converting grid north to true north")
            df['azimuth'] = df['azimuth'] + convergence
            df['azimuth'] = df['azimuth'] % 360

        # Ensure azimuths are in [0, 360)
        df['azimuth'] = df['azimuth'] % 360

        return df

    def _calculate_trajectory_welleng(
        self,
        survey_df: pd.DataFrame,
        surface_lat: float,
        surface_lon: float,
        surface_elevation: float,
        declination: float,
        dip: float,
        b_total: float,
        convergence: float,
        interpolate: bool,
        interpolation_step: float
    ) -> pd.DataFrame:
        """
        Calculate trajectory using welleng minimum curvature.

        Args:
            survey_df: Survey data with MD, INC, AZ (true north).
            surface_lat: Surface latitude.
            surface_lon: Surface longitude.
            surface_elevation: Surface elevation in feet.
            declination: Magnetic declination.
            dip: Magnetic dip.
            b_total: Total magnetic field.
            convergence: Grid convergence.
            interpolate: Whether to interpolate.
            interpolation_step: Interpolation step.

        Returns:
            DataFrame with calculated trajectory.
        """
        try:
            # Create welleng survey header
            header = SurveyHeader(
                latitude=surface_lat,
                longitude=surface_lon,
                altitude=surface_elevation * 0.3048,  # Convert feet to meters
                b_total=b_total,
                dip=dip,
                declination=declination,
                convergence=convergence,
                azi_reference='true'
            )

            # Create survey object
            survey = Survey(
                md=survey_df['measured_depth'].values,
                inc=survey_df['inclination'].values,
                azi=survey_df['azimuth'].values,
                header=header,
                start_nev=[0, 0, surface_elevation],  # Start at surface
                unit='feet'
            )

            # Interpolate if requested
            if interpolate and len(survey_df) > 1:
                total_md = survey_df['measured_depth'].max()
                num_points = int(total_md / interpolation_step) + 1
                interp_md = np.linspace(0, total_md, num_points)
                survey = survey.interpolate_survey(interp_md)

            # Extract calculated values
            result_df = pd.DataFrame({
                'measured_depth': survey.md,
                'inclination': survey.inc,
                'azimuth': survey.azi,
                'tvd': survey.z,  # True vertical depth
                'northing': survey.n,  # Northing offset from surface
                'easting': survey.e,  # Easting offset from surface
                'dogleg_severity': survey.dogleg if hasattr(survey, 'dogleg') else 0,
                'build_rate': survey.build_rate if hasattr(survey, 'build_rate') else 0,
                'turn_rate': survey.turn_rate if hasattr(survey, 'turn_rate') else 0
            })

            return result_df

        except Exception as e:
            self.logger.error(f"Welleng trajectory calculation failed: {e}", exc_info=True)
            raise SurveyProcessingError(f"Trajectory calculation failed: {str(e)}")

    def calculate_dogleg_severity(self, survey_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate dogleg severity between survey stations.

        Args:
            survey_df: Survey DataFrame with MD, INC, AZ columns.

        Returns:
            DataFrame with dogleg_severity column added.
        """
        df = survey_df.copy()

        if len(df) < 2:
            df['dogleg_severity'] = 0.0
            return df

        # Calculate dogleg using welleng's formula
        inc1 = np.radians(df['inclination'].iloc[:-1].values)
        inc2 = np.radians(df['inclination'].iloc[1:].values)
        azi1 = np.radians(df['azimuth'].iloc[:-1].values)
        azi2 = np.radians(df['azimuth'].iloc[1:].values)

        # Dogleg angle
        cos_dogleg = (
            np.cos(inc2 - inc1) -
            np.sin(inc1) * np.sin(inc2) * (1 - np.cos(azi2 - azi1))
        )
        dogleg = np.degrees(np.arccos(np.clip(cos_dogleg, -1, 1)))

        # Convert to dogleg severity (degrees per 100 ft)
        md_diff = df['measured_depth'].iloc[1:].values - df['measured_depth'].iloc[:-1].values
        dogleg_severity = (dogleg / md_diff) * 100

        # Add to dataframe
        df['dogleg_severity'] = np.concatenate([[0], dogleg_severity])

        return df
