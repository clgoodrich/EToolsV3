"""
Base repository pattern for EToolsV3.

This module provides base classes for all repository implementations,
ensuring consistent patterns for data access across the application.
"""

from typing import Optional, Dict, Any, List
from abc import ABC

import pandas as pd

from data.database import DatabaseManager, SQLiteManager, get_database_manager
from config.logging_config import get_logger
from utils.errors import DatabaseQueryError, DatabaseError


class BaseRepository(ABC):
    """
    Base repository for SQL Server database access.

    Provides common methods for executing queries with proper error handling
    and logging. All SQL Server repositories should inherit from this class.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize repository.

        Args:
            db_manager: Database manager instance. If None, uses global instance.
        """
        self.db = db_manager or get_database_manager()
        self.logger = get_logger(self.__class__.__name__)

    def _execute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        operation_name: str = "query"
    ) -> pd.DataFrame:
        """
        Execute parameterized query and return results as DataFrame.

        Args:
            query: SQL query string with named parameters.
            params: Query parameters as dictionary.
            operation_name: Name of the operation for logging.

        Returns:
            Query results as DataFrame.

        Raises:
            DatabaseQueryError: If query execution fails.
        """
        try:
            self.logger.debug(f"Executing {operation_name}: {query[:100]}...")
            result = self.db.query_to_dataframe(query, params)
            self.logger.debug(f"{operation_name} returned {len(result)} rows")
            return result

        except DatabaseError:
            # Re-raise database errors as-is
            raise
        except Exception as e:
            self.logger.error(
                f"{operation_name} failed: {query[:100]}...",
                exc_info=True
            )
            raise DatabaseQueryError(
                f"{operation_name} failed: {str(e)}",
                details={'query': query[:200], 'params': params}
            )

    def _execute_scalar(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        operation_name: str = "scalar query"
    ) -> Optional[Any]:
        """
        Execute query that returns a single value.

        Args:
            query: SQL query string.
            params: Query parameters as dictionary.
            operation_name: Name of the operation for logging.

        Returns:
            Single value or None if no results.

        Raises:
            DatabaseQueryError: If query execution fails.
        """
        result = self._execute_query(query, params, operation_name)

        if result.empty:
            return None

        # Return first value of first row
        return result.iloc[0, 0]

    def _validate_required_params(self, params: Dict[str, Any], required: List[str]):
        """
        Validate that required parameters are present and not None.

        Args:
            params: Parameter dictionary to validate.
            required: List of required parameter names.

        Raises:
            ValueError: If any required parameter is missing or None.
        """
        missing = [key for key in required if key not in params or params[key] is None]
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")

    def _sanitize_api_number(self, api: str) -> str:
        """
        Sanitize and validate API number.

        Args:
            api: API number to sanitize.

        Returns:
            Sanitized API number.

        Raises:
            ValueError: If API number format is invalid.
        """
        # Remove any whitespace
        api = api.strip()

        # Basic validation - should be 10 digits
        if not api.isdigit() or len(api) != 10:
            raise ValueError(f"Invalid API number format: '{api}'")

        return api


class BaseSQLiteRepository(ABC):
    """
    Base repository for SQLite database access.

    Provides common methods for accessing SQLite databases (plats, casing, etc.).
    """

    def __init__(self, db_path: str):
        """
        Initialize SQLite repository.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db = SQLiteManager(db_path)
        self.logger = get_logger(self.__class__.__name__)

    def _execute_query(
        self,
        query: str,
        params: Optional[tuple] = None,
        operation_name: str = "query"
    ) -> pd.DataFrame:
        """
        Execute query and return results as DataFrame.

        Args:
            query: SQL query string.
            params: Query parameters as tuple.
            operation_name: Name of the operation for logging.

        Returns:
            Query results as DataFrame.

        Raises:
            DatabaseQueryError: If query execution fails.
        """
        try:
            self.logger.debug(f"Executing {operation_name}: {query[:100]}...")
            result = self.db.query_to_dataframe(query, params)
            self.logger.debug(f"{operation_name} returned {len(result)} rows")
            return result

        except DatabaseError:
            raise
        except Exception as e:
            self.logger.error(
                f"{operation_name} failed: {query[:100]}...",
                exc_info=True
            )
            raise DatabaseQueryError(
                f"{operation_name} failed: {str(e)}",
                details={'query': query[:200], 'params': params}
            )

    def _execute_scalar(
        self,
        query: str,
        params: Optional[tuple] = None,
        operation_name: str = "scalar query"
    ) -> Optional[Any]:
        """
        Execute query that returns a single value.

        Args:
            query: SQL query string.
            params: Query parameters as tuple.
            operation_name: Name of the operation for logging.

        Returns:
            Single value or None if no results.
        """
        result = self._execute_query(query, params, operation_name)

        if result.empty:
            return None

        return result.iloc[0, 0]
