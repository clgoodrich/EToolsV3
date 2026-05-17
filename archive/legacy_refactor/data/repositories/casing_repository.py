"""
Casing repository for EToolsV3.

This module provides data access for casing strength and specifications from SQLite database.
"""

from typing import Optional
import pandas as pd

from data.repositories.base_repository import BaseSQLiteRepository
from config.settings import settings
from utils.errors import DatabaseQueryError


class CasingRepository(BaseSQLiteRepository):
    """Repository for casing strength and specification data."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize casing repository.

        Args:
            db_path: Path to casing SQLite database. If None, uses path from settings.
        """
        if db_path is None:
            db_path = str(settings.paths.casing_db)
        super().__init__(db_path)

    def get_all_casing_strengths(self) -> pd.DataFrame:
        """
        Get all casing strength data.

        Returns:
            DataFrame with all casing specifications and strengths.

        Raises:
            DatabaseQueryError: If query fails.
        """
        query = "SELECT * FROM CasingStrengths"
        result = self._execute_query(query, None, "get_all_casing_strengths")

        if not result.empty:
            # Strip string columns
            result = result.map(lambda x: x.strip() if isinstance(x, str) else x)

            # Convert numeric columns
            if 'CasingDiameter' in result.columns:
                result['CasingDiameter'] = pd.to_numeric(result['CasingDiameter'], errors='coerce')
            if 'NominalWeight' in result.columns:
                result['NominalWeight'] = pd.to_numeric(result['NominalWeight'], errors='coerce')

            # Drop the first column if it's an index column
            if result.columns[0] in ['index', 'Unnamed: 0']:
                result = result.drop(result.columns[0], axis=1)

        return result

    def get_casing_by_size(self, diameter: float, weight: Optional[float] = None) -> pd.DataFrame:
        """
        Get casing specifications for a given size.

        Args:
            diameter: Casing outer diameter in inches.
            weight: Optional nominal weight in lbs/ft for exact match.

        Returns:
            DataFrame with matching casing specifications.

        Raises:
            DatabaseQueryError: If query fails.
        """
        if weight is not None:
            query = """
                SELECT *
                FROM CasingStrengths
                WHERE CasingDiameter = ?
                    AND NominalWeight = ?
            """
            params = (diameter, weight)
        else:
            query = """
                SELECT *
                FROM CasingStrengths
                WHERE CasingDiameter = ?
                ORDER BY NominalWeight
            """
            params = (diameter,)

        result = self._execute_query(query, params, "get_casing_by_size")

        if not result.empty:
            result = result.map(lambda x: x.strip() if isinstance(x, str) else x)

        return result

    def get_casing_by_grade(self, grade: str) -> pd.DataFrame:
        """
        Get all casing with a specific grade.

        Args:
            grade: Casing grade (e.g., 'P-110', 'N-80', 'L-80').

        Returns:
            DataFrame with matching casing specifications.

        Raises:
            DatabaseQueryError: If query fails.
        """
        query = """
            SELECT *
            FROM CasingStrengths
            WHERE Grade = ?
            ORDER BY CasingDiameter, NominalWeight
        """

        result = self._execute_query(query, (grade,), "get_casing_by_grade")

        if not result.empty:
            result = result.map(lambda x: x.strip() if isinstance(x, str) else x)

        return result

    def get_available_sizes(self) -> pd.DataFrame:
        """
        Get list of all available casing sizes.

        Returns:
            DataFrame with unique casing diameters and weight ranges.
        """
        query = """
            SELECT
                CasingDiameter,
                COUNT(*) as count,
                MIN(NominalWeight) as min_weight,
                MAX(NominalWeight) as max_weight
            FROM CasingStrengths
            GROUP BY CasingDiameter
            ORDER BY CasingDiameter
        """

        return self._execute_query(query, None, "get_available_sizes")

    def get_available_grades(self) -> pd.DataFrame:
        """
        Get list of all available casing grades.

        Returns:
            DataFrame with unique grades and their frequency.
        """
        query = """
            SELECT
                Grade,
                COUNT(*) as count
            FROM CasingStrengths
            GROUP BY Grade
            ORDER BY Grade
        """

        return self._execute_query(query, None, "get_available_grades")

    def get_connection_types(self) -> pd.DataFrame:
        """
        Get list of all connection types.

        Returns:
            DataFrame with unique connection types.
        """
        query = """
            SELECT DISTINCT ConnectionType
            FROM CasingStrengths
            WHERE ConnectionType IS NOT NULL
            ORDER BY ConnectionType
        """

        return self._execute_query(query, None, "get_connection_types")

    def find_casing_by_properties(
        self,
        min_diameter: Optional[float] = None,
        max_diameter: Optional[float] = None,
        min_weight: Optional[float] = None,
        max_weight: Optional[float] = None,
        grade: Optional[str] = None,
        min_internal_yield: Optional[float] = None,
        min_collapse: Optional[float] = None
    ) -> pd.DataFrame:
        """
        Find casing matching specific property requirements.

        Args:
            min_diameter: Minimum casing diameter in inches.
            max_diameter: Maximum casing diameter in inches.
            min_weight: Minimum nominal weight in lbs/ft.
            max_weight: Maximum nominal weight in lbs/ft.
            grade: Casing grade filter.
            min_internal_yield: Minimum internal yield pressure in psi.
            min_collapse: Minimum collapse pressure in psi.

        Returns:
            DataFrame with matching casing specifications.
        """
        conditions = []
        params = []

        if min_diameter is not None:
            conditions.append("CasingDiameter >= ?")
            params.append(min_diameter)

        if max_diameter is not None:
            conditions.append("CasingDiameter <= ?")
            params.append(max_diameter)

        if min_weight is not None:
            conditions.append("NominalWeight >= ?")
            params.append(min_weight)

        if max_weight is not None:
            conditions.append("NominalWeight <= ?")
            params.append(max_weight)

        if grade is not None:
            conditions.append("Grade = ?")
            params.append(grade)

        if min_internal_yield is not None:
            conditions.append("InternalYield >= ?")
            params.append(min_internal_yield)

        if min_collapse is not None:
            conditions.append("Collapse >= ?")
            params.append(min_collapse)

        if not conditions:
            # No filters, return all
            return self.get_all_casing_strengths()

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT *
            FROM CasingStrengths
            WHERE {where_clause}
            ORDER BY CasingDiameter, NominalWeight
        """

        result = self._execute_query(query, tuple(params), "find_casing_by_properties")

        if not result.empty:
            result = result.map(lambda x: x.strip() if isinstance(x, str) else x)

        return result

    def get_casing_statistics(self) -> dict:
        """
        Get statistics about the casing database.

        Returns:
            Dictionary with statistics (total records, diameter range, etc.).
        """
        stats = {}

        # Total records
        query = "SELECT COUNT(*) as total FROM CasingStrengths"
        stats['total_records'] = self._execute_scalar(query, None, "count_casing")

        # Diameter range
        query = """
            SELECT
                MIN(CasingDiameter) as min_diameter,
                MAX(CasingDiameter) as max_diameter
            FROM CasingStrengths
        """
        diameter_result = self._execute_query(query, None, "diameter_range")
        if not diameter_result.empty:
            stats.update(diameter_result.iloc[0].to_dict())

        # Grade count
        query = "SELECT COUNT(DISTINCT Grade) as grade_count FROM CasingStrengths"
        stats['grade_count'] = self._execute_scalar(query, None, "count_grades")

        return stats
