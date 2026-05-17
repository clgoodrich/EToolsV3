"""
Main UI Controller for EToolsV3

This module connects the PyQt5 UI (EToolsLimited.py) to the service layer.
It handles all UI interactions, delegates business logic to services, and
displays results using proper error handling.

This is a complete rewrite with clean architecture separating UI from business logic.
"""

from typing import Optional, Dict
from PyQt5.QtWidgets import QMainWindow, QMessageBox, QFileDialog, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt

from EToolsLimited import Ui_MainWindow
from ui.table_models import PandasTableModel, SurveyTableModel, ClearanceTableModel
from ui.visualizations import MatplotlibCanvas, PlotlyWidget
from ui.validators import validate_api_number, validate_lateral_name
from services.well_service import WellService
from services.survey_service import SurveyService
from services.clearance_service import ClearanceService
from services.wcr_service import WCRService
from services.visualization_service import VisualizationService
from config.logging_config import get_logger
from utils.errors import (
    EToolsError, WellNotFoundError, SurveyNotFoundError,
    DatabaseError, ValidationError, format_error_for_user
)

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """Main application window controller."""

    def __init__(self, services: Dict, parent=None):
        """
        Initialize main window.

        Args:
            services: Dictionary of initialized service instances.
            parent: Parent QWidget.
        """
        super().__init__(parent)

        # Setup UI from designer file
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Store services
        self.well_service: WellService = services['well_service']
        self.survey_service: SurveyService = services['survey_service']
        self.clearance_service: ClearanceService = services['clearance_service']
        self.wcr_service: WCRService = services['wcr_service']
        self.viz_service: VisualizationService = services['visualization_service']

        # State variables
        self.current_survey = None
        self.current_clearances = None
        self.current_well_info = None
        self.current_well_location = None

        # Connect signals
        self._connect_signals()

        logger.info("Main window initialized")

    def _connect_signals(self):
        """Connect UI signals to handler methods."""
        # Well loading
        if hasattr(self.ui, 'load_well_button'):
            self.ui.load_well_button.clicked.connect(self.on_load_well)

        # Survey processing
        if hasattr(self.ui, 'process_survey_button'):
            self.ui.process_survey_button.clicked.connect(self.on_process_survey)

        # Clearance calculation
        if hasattr(self.ui, 'calculate_clearance_button'):
            self.ui.calculate_clearance_button.clicked.connect(self.on_calculate_clearances)

        # WCR generation
        if hasattr(self.ui, 'generate_wcr_button'):
            self.ui.generate_wcr_button.clicked.connect(self.on_generate_wcr)

        # PDF import
        if hasattr(self.ui, 'import_pdf_button'):
            self.ui.import_pdf_button.clicked.connect(self.on_import_pdf)

        # Visualization
        if hasattr(self.ui, 'create_2d_plot_button'):
            self.ui.create_2d_plot_button.clicked.connect(self.on_create_2d_plot)

        if hasattr(self.ui, 'create_3d_plot_button'):
            self.ui.create_3d_plot_button.clicked.connect(self.on_create_3d_plot)

    def on_load_well(self):
        """Handle load well button click."""
        try:
            # Get and validate API and lateral
            api = self.ui.well_api_val.text().strip() if hasattr(self.ui, 'well_api_val') else ''
            lateral = self.ui.lateral_name_line_edit.text().strip() if hasattr(self.ui, 'lateral_name_line_edit') else '0000'

            is_valid, error_msg = validate_api_number(api)
            if not is_valid:
                self._show_error("Validation Error", error_msg)
                return

            logger.info(f"Loading well: API={api}, Lateral={lateral}")

            # Load well data
            self.current_well_info, self.current_well_location = self.well_service.load_well(api, lateral)

            # Display well information
            self._display_well_info(self.current_well_info, self.current_well_location)

            self._show_success("Well Loaded", f"Successfully loaded {self.current_well_info.well_name}")

        except WellNotFoundError as e:
            self._show_error("Well Not Found", format_error_for_user(e))
        except DatabaseError as e:
            self._show_error("Database Error", format_error_for_user(e))
        except Exception as e:
            logger.error(f"Unexpected error loading well: {e}", exc_info=True)
            self._show_error("Error", f"Failed to load well: {str(e)}")

    def on_process_survey(self):
        """Handle process survey button click."""
        try:
            # Get and validate inputs
            api = self.ui.well_api_val.text().strip() if hasattr(self.ui, 'well_api_val') else ''
            lateral = self.ui.lateral_name_line_edit.text().strip() if hasattr(self.ui, 'lateral_name_line_edit') else ''

            is_valid, error_msg = validate_api_number(api)
            if not is_valid:
                self._show_error("Validation Error", error_msg)
                return

            logger.info(f"Processing survey: API={api}, Lateral={lateral}")

            # Process survey
            self.current_survey = self.survey_service.process_survey(api, lateral)

            # Display survey data
            self._display_survey_data(self.current_survey)

            self._show_success(
                "Survey Processed",
                f"Successfully processed survey: {len(self.current_survey.data)} points, "
                f"Total MD: {self.current_survey.total_md:.1f} ft, "
                f"KOP: {self.current_survey.kop_md:.1f} ft"
            )

        except SurveyNotFoundError as e:
            self._show_error("Survey Not Found", format_error_for_user(e))
        except Exception as e:
            logger.error(f"Unexpected error processing survey: {e}", exc_info=True)
            self._show_error("Error", f"Failed to process survey: {str(e)}")

    def on_calculate_clearances(self):
        """Handle calculate clearances button click."""
        try:
            if self.current_survey is None:
                self._show_error("No Survey Data", "Please process survey first")
                return

            logger.info("Calculating clearances")

            # Calculate clearances
            self.current_clearances = self.clearance_service.calculate_clearances(self.current_survey)

            # Display clearance data
            self._display_clearance_data(self.current_clearances)

            self._show_success(
                "Clearances Calculated",
                f"Min clearance: {self.current_clearances.min_overall_clearance:.1f} ft, "
                f"Sections: {self.current_clearances.num_sections}"
            )

        except Exception as e:
            logger.error(f"Unexpected error calculating clearances: {e}", exc_info=True)
            self._show_error("Error", f"Failed to calculate clearances: {str(e)}")

    def on_generate_wcr(self):
        """Handle generate WCR button click."""
        try:
            api = self.ui.well_api_val.text().strip() if hasattr(self.ui, 'well_api_val') else ''
            lateral = self.ui.lateral_name_line_edit.text().strip() if hasattr(self.ui, 'lateral_name_line_edit') else ''

            is_valid, error_msg = validate_api_number(api)
            if not is_valid:
                self._show_error("Validation Error", error_msg)
                return

            logger.info(f"Generating WCR: API={api}, Lateral={lateral}")

            # Generate WCR
            wcr_path = self.wcr_service.generate_wcr(api, lateral)

            self._show_success("WCR Generated", f"WCR saved to:\n{wcr_path}")

        except Exception as e:
            logger.error(f"Unexpected error generating WCR: {e}", exc_info=True)
            self._show_error("Error", f"Failed to generate WCR: {str(e)}")

    def on_import_pdf(self):
        """Handle import PDF button click."""
        try:
            # Open file dialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Survey PDF",
                "",
                "PDF Files (*.pdf)"
            )

            if not file_path:
                return

            logger.info(f"Importing PDF: {file_path}")

            # Get API and lateral
            api = self.ui.well_api_val.text().strip() if hasattr(self.ui, 'well_api_val') else ''
            lateral = self.ui.lateral_name_line_edit.text().strip() if hasattr(self.ui, 'lateral_name_line_edit') else ''

            # Import PDF
            survey_df = self.survey_service.import_from_pdf(file_path, api, lateral)

            self._show_success("PDF Imported", f"Successfully imported {len(survey_df)} survey points")

        except Exception as e:
            logger.error(f"Unexpected error importing PDF: {e}", exc_info=True)
            self._show_error("Error", f"Failed to import PDF: {str(e)}")

    def on_create_2d_plot(self):
        """Handle create 2D plot button click."""
        try:
            if self.current_survey is None:
                self._show_error("No Survey Data", "Please process survey first")
                return

            logger.info("Creating 2D plot")

            # Create plot
            fig = self.viz_service.create_2d_plot(
                self.current_survey,
                clearances=self.current_clearances
            )

            # Display plot
            self._display_matplotlib_figure(fig)

        except Exception as e:
            logger.error(f"Unexpected error creating 2D plot: {e}", exc_info=True)
            self._show_error("Error", f"Failed to create plot: {str(e)}")

    def on_create_3d_plot(self):
        """Handle create 3D plot button click."""
        try:
            if self.current_survey is None:
                self._show_error("No Survey Data", "Please process survey first")
                return

            logger.info("Creating 3D plot")

            # Create plot
            fig = self.viz_service.create_3d_plot(self.current_survey)

            # Display plot
            self._display_plotly_figure(fig)

        except Exception as e:
            logger.error(f"Unexpected error creating 3D plot: {e}", exc_info=True)
            self._show_error("Error", f"Failed to create plot: {str(e)}")

    def _display_well_info(self, well_info, well_location):
        """Display well information in UI."""
        # Update UI labels/fields with well info
        # Implementation depends on actual UI structure
        pass

    def _display_survey_data(self, survey):
        """Display survey data in table view."""
        if hasattr(self.ui, 'survey_table'):
            model = SurveyTableModel(survey.data)
            self.ui.survey_table.setModel(model)

    def _display_clearance_data(self, clearances):
        """Display clearance data in table view."""
        if hasattr(self.ui, 'clearance_table'):
            model = ClearanceTableModel(clearances.clearances)
            self.ui.clearance_table.setModel(model)

    def _display_matplotlib_figure(self, fig):
        """Display matplotlib figure in UI."""
        # Implementation depends on UI structure
        # Typically would replace widget or add to layout
        pass

    def _display_plotly_figure(self, fig):
        """Display plotly figure in UI."""
        # Implementation depends on UI structure
        pass

    def _show_error(self, title: str, message: str):
        """Show error message dialog."""
        QMessageBox.critical(self, title, message)
        logger.error(f"{title}: {message}")

    def _show_success(self, title: str, message: str):
        """Show success message dialog."""
        QMessageBox.information(self, title, message)
        logger.info(f"{title}: {message}")
