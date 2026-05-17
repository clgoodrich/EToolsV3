"""
Database connection management for EToolsV3.

This module provides centralized database connection handling with pooling,
error handling, and support for both production and local databases.
"""

import sqlite3
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError, TimeoutError as SQLTimeoutError

from config.settings import settings, DatabaseConfig
from config.logging_config import get_logger
from utils.errors import (
    DatabaseConnectionError,
    DatabaseQueryError,
    DatabaseTimeoutError
)

logger = get_logger(__name__)


class DatabaseManager:
    """
    Manages connections to SQL Server databases (production and local fallback).

    Provides connection pooling, automatic failover to local database,
    and context managers for safe session handling.
    """

    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        Initialize database manager.

        Args:
            config: Database configuration. If None, uses global settings.
        """
        self.config = config or settings.database
        self._engine: Optional[Engine] = None
        self._session_factory = None
        self._connection_string: Optional[str] = None

    @property
    def engine(self) -> Engine:
        """
        Get SQLAlchemy engine, creating it if necessary.

        Returns:
            SQLAlchemy engine instance.

        Raises:
            DatabaseConnectionError: If connection cannot be established.
        """
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    def _build_connection_string(self, use_local: bool = False) -> str:
        """
        Build SQLAlchemy connection string.

        Args:
            use_local: If True, use local database settings.

        Returns:
            SQLAlchemy connection string.
        """
        if use_local or not self.config.has_credentials:
            # Local database with Windows authentication
            conn_str = (
                f"DRIVER={{{self.config.driver}}};"
                f"SERVER={self.config.local_server};"
                f"DATABASE={self.config.local_database};"
                "Trusted_Connection=yes;"
            )
            logger.info(f"Using local database: {self.config.local_server}")
        else:
            # Production database with SQL authentication
            conn_str = (
                f"DRIVER={{{self.config.driver}}};"
                f"SERVER={self.config.host};"
                f"DATABASE={self.config.database};"
                f"UID={self.config.user};"
                f"PWD={self.config.password};"
            )
            logger.info(f"Using production database: {self.config.host}")

        return f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}"

    def _create_engine(self) -> Engine:
        """
        Create SQLAlchemy engine with connection pooling.

        Returns:
            SQLAlchemy engine instance.

        Raises:
            DatabaseConnectionError: If connection cannot be established.
        """
        try:
            # Try production database first
            if self.config.has_credentials:
                connection_string = self._build_connection_string(use_local=False)
                try:
                    engine = create_engine(
                        connection_string,
                        pool_pre_ping=self.config.pool_pre_ping,
                        pool_size=self.config.pool_size,
                        pool_recycle=self.config.pool_recycle,
                        connect_args={
                            'timeout': self.config.connect_timeout
                        }
                    )
                    # Test connection
                    with engine.connect() as conn:
                        conn.execute(text("SELECT 1"))
                    logger.info("Successfully connected to production database")
                    self._connection_string = connection_string
                    return engine
                except (OperationalError, SQLAlchemyError) as e:
                    logger.warning(f"Failed to connect to production database: {e}")
                    if not self.config.local_fallback:
                        raise DatabaseConnectionError(
                            "Unable to connect to production database",
                            details=str(e)
                        )

            # Fallback to local database
            if self.config.local_fallback:
                logger.info("Attempting to connect to local database")
                connection_string = self._build_connection_string(use_local=True)
                engine = create_engine(
                    connection_string,
                    pool_pre_ping=self.config.pool_pre_ping,
                    pool_size=self.config.pool_size,
                    pool_recycle=self.config.pool_recycle
                )
                # Test connection
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info("Successfully connected to local database")
                self._connection_string = connection_string
                return engine

            raise DatabaseConnectionError("No database connection available")

        except Exception as e:
            logger.error(f"Failed to create database engine: {e}", exc_info=True)
            raise DatabaseConnectionError(
                "Failed to establish database connection",
                details=str(e)
            )

    @contextmanager
    def get_session(self):
        """
        Context manager for database sessions.

        Usage:
            with db.get_session() as session:
                result = session.execute(query)

        Yields:
            SQLAlchemy session instance.

        Raises:
            DatabaseError: If session operations fail.
        """
        if self._session_factory is None:
            self._session_factory = sessionmaker(bind=self.engine)

        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Session error: {e}", exc_info=True)
            raise
        finally:
            session.close()

    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.

        Usage:
            with db.get_connection() as conn:
                result = conn.execute(query)

        Yields:
            SQLAlchemy connection instance.

        Raises:
            DatabaseConnectionError: If connection fails.
        """
        try:
            connection = self.engine.connect()
            yield connection
        except OperationalError as e:
            logger.error(f"Connection error: {e}", exc_info=True)
            raise DatabaseConnectionError("Database connection failed", details=str(e))
        except SQLTimeoutError as e:
            logger.error(f"Connection timeout: {e}", exc_info=True)
            raise DatabaseTimeoutError("Database connection timeout", details=str(e))
        finally:
            connection.close()

    def execute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None
    ) -> List[tuple]:
        """
        Execute a raw SQL query and return results.

        Args:
            query: SQL query string.
            params: Query parameters as dictionary.

        Returns:
            List of result tuples.

        Raises:
            DatabaseQueryError: If query execution fails.
        """
        try:
            with self.get_connection() as conn:
                result = conn.execute(text(query), params or {})
                return result.fetchall()
        except SQLTimeoutError as e:
            logger.error(f"Query timeout: {query[:100]}...", exc_info=True)
            raise DatabaseTimeoutError("Query execution timeout", details=str(e))
        except SQLAlchemyError as e:
            logger.error(f"Query failed: {query[:100]}...", exc_info=True)
            raise DatabaseQueryError(f"Query execution failed: {str(e)}")

    def query_to_dataframe(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None
    ) -> pd.DataFrame:
        """
        Execute query and return results as pandas DataFrame.

        Args:
            query: SQL query string.
            params: Query parameters as dictionary.

        Returns:
            Query results as DataFrame.

        Raises:
            DatabaseQueryError: If query execution fails.
        """
        try:
            logger.debug(f"Executing query: {query[:100]}...")
            if params:
                logger.debug(f"Parameters: {params}")

            df = pd.read_sql_query(text(query), self.engine, params=params or {})
            logger.debug(f"Query returned {len(df)} rows")
            return df

        except SQLTimeoutError as e:
            logger.error(f"Query timeout: {query[:100]}...", exc_info=True)
            raise DatabaseTimeoutError("Query execution timeout", details=str(e))
        except SQLAlchemyError as e:
            logger.error(f"Query failed: {query[:100]}...", exc_info=True)
            raise DatabaseQueryError(f"Query execution failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in query: {query[:100]}...", exc_info=True)
            raise DatabaseQueryError(f"Unexpected error: {str(e)}")

    def test_connection(self) -> bool:
        """
        Test database connection.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            with self.get_connection() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def close(self):
        """Close database engine and all connections."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            logger.info("Database connections closed")


class SQLiteManager:
    """
    Manages connections to SQLite databases (for plats, casing, etc.).

    Simpler than DatabaseManager since SQLite doesn't need pooling or failover.
    """

    def __init__(self, db_path: str):
        """
        Initialize SQLite manager.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self.logger = get_logger(__name__)

    @contextmanager
    def get_connection(self):
        """
        Context manager for SQLite connections.

        Usage:
            with sqlite_mgr.get_connection() as conn:
                df = pd.read_sql_query(query, conn)

        Yields:
            SQLite connection instance.
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            yield conn
        except sqlite3.Error as e:
            self.logger.error(f"SQLite error: {e}", exc_info=True)
            raise DatabaseQueryError(f"SQLite query failed: {str(e)}")
        finally:
            if conn:
                conn.close()

    def query_to_dataframe(self, query: str, params: Optional[tuple] = None) -> pd.DataFrame:
        """
        Execute query and return results as DataFrame.

        Args:
            query: SQL query string.
            params: Query parameters as tuple.

        Returns:
            Query results as DataFrame.
        """
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query(query, conn, params=params or ())
        except Exception as e:
            self.logger.error(f"SQLite query failed: {query[:100]}...", exc_info=True)
            raise DatabaseQueryError(f"SQLite query failed: {str(e)}")


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """
    Get global database manager instance.

    Returns:
        DatabaseManager instance.
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
