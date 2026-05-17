"""
Survey repository for EToolsV3.

This module provides data access for directional survey data.
"""

from typing import Optional
import pandas as pd

from data.repositories.base_repository import BaseRepository
from data.models.survey import SurveyHeader, RawSurveyData
from utils.errors import SurveyNotFoundError, InvalidAPINumberError, DatabaseQueryError


class SurveyRepository(BaseRepository):
    """Repository for directional survey data access."""

    def get_survey_data(
        self,
        api: str,
        lateral: str,
        citing_type: Optional[str] = None
    ) -> RawSurveyData:
        """
        Get raw survey data from database.

        Args:
            api: 10-digit API number.
            lateral: Lateral name.
            citing_type: Optional citing type filter ('Drilled', 'Planned', etc.).

        Returns:
            RawSurveyData object with survey measurements and header info.

        Raises:
            InvalidAPINumberError: If API format is invalid.
            SurveyNotFoundError: If survey not found.
            DatabaseQueryError: If query fails.
        """
        api = self._sanitize_api_number(api)

        # Build query with optional citing type filter
        query = """
            SELECT
                MeasuredDepth as measured_depth,
                Inclination as inclination,
                Azimuth as azimuth,
                CitingType,
                dsh.SurveySurfaceElevation,
                dsh.SurfaceLatitude,
                dsh.SurfaceLongitude,
                dsh.NorthReference,
                dsh.LateralName
            FROM DirectionalSurveyHeader dsh
            JOIN DirectionalSurveyData dsd ON dsd.DirectionalSurveyHeaderKey = dsh.Pkey
            WHERE dsh.APINumber = :api
                AND dsh.LateralName = :lateral
        """

        params = {'api': api, 'lateral': lateral}

        if citing_type:
            query += " AND CitingType = :citing_type"
            params['citing_type'] = citing_type

        query += " ORDER BY MeasuredDepth"

        result = self._execute_query(query, params, "get_survey_data")

        if result.empty:
            raise SurveyNotFoundError(api, lateral)

        # Extract header information from first row
        first_row = result.iloc[0]

        # Get measurements dataframe (MD, INC, AZ)
        measurements = result[['measured_depth', 'inclination', 'azimuth']].copy()

        return RawSurveyData(
            api_number=api,
            lateral_name=lateral,
            citing_type=first_row['CitingType'],
            surface_latitude=float(first_row['SurfaceLatitude']),
            surface_longitude=float(first_row['SurfaceLongitude']),
            surface_elevation=float(first_row['SurveySurfaceElevation']),
            north_reference=first_row['NorthReference'],
            measurements=measurements
        )

    def get_survey_header(self, api: str, lateral: str) -> SurveyHeader:
        """
        Get survey header information only (without measurements).

        Args:
            api: 10-digit API number.
            lateral: Lateral name.

        Returns:
            SurveyHeader object.

        Raises:
            InvalidAPINumberError: If API format is invalid.
            SurveyNotFoundError: If survey not found.
            DatabaseQueryError: If query fails.
        """
        api = self._sanitize_api_number(api)

        query = """
            SELECT
                dsh.APINumber,
                dsh.LateralName,
                dsh.SurfaceLatitude,
                dsh.SurfaceLongitude,
                dsh.SurveySurfaceElevation,
                dsh.NorthReference,
                dsh.SurfaceLat longDatum as Datum,
                dsh.OperatorName,
                dsh.WellNameNumber,
                dsh.CitingType,
                dsh.SurveyCompany
            FROM DirectionalSurveyHeader dsh
            WHERE dsh.APINumber = :api
                AND dsh.LateralName = :lateral
        """

        result = self._execute_query(query, {'api': api, 'lateral': lateral}, "get_survey_header")

        if result.empty:
            raise SurveyNotFoundError(api, lateral)

        row = result.iloc[0]

        return SurveyHeader(
            api_number=api,
            lateral_name=lateral,
            surface_latitude=float(row['SurfaceLatitude']),
            surface_longitude=float(row['SurfaceLongitude']),
            surface_elevation=float(row['SurveySurfaceElevation']),
            north_reference=row.get('NorthReference'),
            datum=row.get('Datum'),
            operator_name=row.get('OperatorName'),
            well_name=row.get('WellNameNumber'),
            citing_type=row.get('CitingType'),
            survey_company=row.get('SurveyCompany')
        )

    def get_available_surveys(self, api: str) -> pd.DataFrame:
        """
        Get list of all available surveys for a well.

        Args:
            api: 10-digit API number.

        Returns:
            DataFrame with available surveys (lateral names and citing types).

        Raises:
            InvalidAPINumberError: If API format is invalid.
            DatabaseQueryError: If query fails.
        """
        api = self._sanitize_api_number(api)

        query = """
            SELECT DISTINCT
                dsh.LateralName,
                dsh.CitingType,
                COUNT(dsd.MeasuredDepth) as PointCount,
                MAX(dsd.MeasuredDepth) as MaxMD
            FROM DirectionalSurveyHeader dsh
            JOIN DirectionalSurveyData dsd ON dsd.DirectionalSurveyHeaderKey = dsh.Pkey
            WHERE dsh.APINumber = :api
            GROUP BY dsh.LateralName, dsh.CitingType
            ORDER BY dsh.LateralName, dsh.CitingType
        """

        return self._execute_query(query, {'api': api}, "get_available_surveys")

    def survey_exists(self, api: str, lateral: str, citing_type: Optional[str] = None) -> bool:
        """
        Check if a survey exists.

        Args:
            api: 10-digit API number.
            lateral: Lateral name.
            citing_type: Optional citing type to check.

        Returns:
            True if survey exists, False otherwise.
        """
        try:
            api = self._sanitize_api_number(api)

            query = """
                SELECT COUNT(*) as count
                FROM DirectionalSurveyHeader dsh
                WHERE dsh.APINumber = :api
                    AND dsh.LateralName = :lateral
            """

            params = {'api': api, 'lateral': lateral}

            if citing_type:
                query += " AND dsh.CitingType = :citing_type"
                params['citing_type'] = citing_type

            count = self._execute_scalar(query, params, "survey_exists")
            return count > 0

        except Exception:
            return False

    def get_survey_point_count(self, api: str, lateral: str) -> int:
        """
        Get count of survey points.

        Args:
            api: 10-digit API number.
            lateral: Lateral name.

        Returns:
            Number of survey points.
        """
        api = self._sanitize_api_number(api)

        query = """
            SELECT COUNT(*) as count
            FROM DirectionalSurveyHeader dsh
            JOIN DirectionalSurveyData dsd ON dsd.DirectionalSurveyHeaderKey = dsh.Pkey
            WHERE dsh.APINumber = :api
                AND dsh.LateralName = :lateral
        """

        count = self._execute_scalar(query, {'api': api, 'lateral': lateral}, "get_survey_point_count")
        return int(count) if count else 0

    def get_max_inclination(self, api: str, lateral: str) -> Optional[float]:
        """
        Get maximum inclination from survey.

        Args:
            api: 10-digit API number.
            lateral: Lateral name.

        Returns:
            Maximum inclination in degrees, or None if no data.
        """
        api = self._sanitize_api_number(api)

        query = """
            SELECT MAX(dsd.Inclination) as MaxInclination
            FROM DirectionalSurveyHeader dsh
            JOIN DirectionalSurveyData dsd ON dsd.DirectionalSurveyHeaderKey = dsh.Pkey
            WHERE dsh.APINumber = :api
                AND dsh.LateralName = :lateral
        """

        result = self._execute_scalar(query, {'api': api, 'lateral': lateral}, "get_max_inclination")
        return float(result) if result else None
