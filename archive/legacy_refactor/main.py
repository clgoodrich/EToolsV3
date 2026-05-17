"""
EToolsV3 Application Entry Point

This is the main entry point for the ETools V3 application.
It initializes logging, configuration, services, and launches the PyQt5 UI.
"""

import sys
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QMessageBox

# Import configuration and logging first
from config.logging_config import setup_logging, configure_third_party_loggers
from config.settings import settings

# Import main UI controller
from mainProject import MainWindow

# Import services
from services.well_service import WellService
from services.survey_service import SurveyService
from services.clearance_service import ClearanceService
from services.wcr_service import WCRService
from services.visualization_service import VisualizationService

# Import database manager
from data.database import get_database_manager


def initialize_application():
    """
    Initialize application configuration and services.

    Returns:
        Dictionary of initialized services.
    """
    # Setup logging
    setup_logging()
    configure_third_party_loggers()

    logger = setup_logging()
    logger.info("=" * 80)
    logger.info("Starting ETools V3 Application")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info("=" * 80)

    # Test database connection
    try:
        db_manager = get_database_manager()
        if not db_manager.test_connection():
            logger.warning("Database connection test failed - will attempt to connect on first use")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        # Don't fail - allow app to start and show error when actually using DB

    # Initialize services
    services = {
        'well_service': WellService(),
        'survey_service': SurveyService(),
        'clearance_service': ClearanceService(),
        'wcr_service': WCRService(),
        'visualization_service': VisualizationService()
    }

    logger.info("Services initialized successfully")

    return services


def main():
    """Main application entry point."""
    try:
        # Create Qt Application
        app = QApplication(sys.argv)
        app.setApplicationName(settings.ui.app_name)
        app.setApplicationVersion(settings.ui.app_version)

        # Initialize services
        services = initialize_application()

        # Create and show main window
        main_window = MainWindow(services)
        main_window.show()

        # Start event loop
        sys.exit(app.exec_())

    except Exception as e:
        # Show critical error dialog
        QMessageBox.critical(
            None,
            "Application Error",
            f"Failed to start ETools V3:\n\n{str(e)}\n\nCheck logs for details."
        )
        sys.exit(1)


if __name__ == '__main__':
    main()
