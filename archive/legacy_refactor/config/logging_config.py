"""
Logging configuration for EToolsV3.

This module sets up structured logging with file and console handlers.
Logs are formatted consistently and rotated to prevent disk space issues.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional

from config.settings import settings


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[Path] = None
) -> logging.Logger:
    """
    Configure application-wide logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                  If None, uses value from settings.
        log_file: Path to log file. If None, uses default from settings.

    Returns:
        Root logger instance.
    """
    # Get configuration
    if log_level is None:
        log_level = settings.logging.level

    if log_file is None:
        log_file = settings.paths.log_dir / 'etools.log'

    # Ensure log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create formatters
    detailed_formatter = logging.Formatter(
        fmt=settings.logging.format,
        datefmt=settings.logging.date_format
    )

    simple_formatter = logging.Formatter(
        fmt='%(levelname)s - %(message)s'
    )

    # File handler (rotating)
    if settings.logging.file_enabled:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=settings.logging.file_max_bytes,
            backupCount=settings.logging.file_backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)

    # Console handler
    if settings.logging.console_enabled:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(detailed_formatter if settings.debug else simple_formatter)
        logger.addHandler(console_handler)

    # Log initial message
    logger.info(f"Logging initialized - Level: {log_level}, File: {log_file}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.

    Args:
        name: Logger name (typically __name__ of the calling module).

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)


class LoggerMixin:
    """
    Mixin class to add logging capability to any class.

    Usage:
        class MyClass(LoggerMixin):
            def my_method(self):
                self.logger.info("Doing something")
    """

    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class."""
        return get_logger(self.__class__.__name__)


def log_function_call(func):
    """
    Decorator to log function calls with arguments and results.

    Usage:
        @log_function_call
        def my_function(arg1, arg2):
            return result
    """
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} returned {result}")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} raised {type(e).__name__}: {e}", exc_info=True)
            raise
    return wrapper


def configure_third_party_loggers():
    """
    Configure logging levels for third-party libraries.

    Reduces noise from verbose libraries while keeping application logs clear.
    """
    # SQLAlchemy - reduce verbosity
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)

    # PyQt - reduce verbosity
    logging.getLogger('PyQt5').setLevel(logging.WARNING)

    # Matplotlib - reduce verbosity
    logging.getLogger('matplotlib').setLevel(logging.WARNING)

    # Other libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)


# Initialize logging when module is imported
if not logging.getLogger().handlers:
    setup_logging()
    configure_third_party_loggers()
