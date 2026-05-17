"""
WCR (Well Completion Report) service for EToolsV3.

This service orchestrates WCR generation from survey, clearance, and well data.
"""

from typing import Optional
from pathlib import Path

from services.well_service import WellService
from services.survey_service import SurveyService
from services.clearance_service import ClearanceService
from core.wcr.generator import WCRGenerator
from config.logging_config import get_logger
from utils.errors import ExcelGenerationError

logger = get_logger(__name__)


class WCRService:
    """Service for WCR generation operations."""

    def __init__(
        self,
        well_service: Optional[WellService] = None,
        survey_service: Optional[SurveyService] = None,
        clearance_service: Optional[ClearanceService] = None,
        wcr_generator: Optional[WCRGenerator] = None
    ):
        """
        Initialize WCR service.

        Args:
            well_service: Well service.
            survey_service: Survey service.
            clearance_service: Clearance service.
            wcr_generator: WCR generator.
        """
        self.well_service = well_service or WellService()
        self.survey_service = survey_service or SurveyService()
        self.clearance_service = clearance_service or ClearanceService()
        self.wcr_generator = wcr_generator or WCRGenerator()
        self.logger = logger

    def generate_wcr(
        self,
        api: str,
        lateral: str,
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Generate complete WCR for a well.

        This orchestrates the full workflow:
        1. Load well information
        2. Process survey
        3. Calculate clearances
        4. Calculate footage
        5. Generate Excel report

        Args:
            api: 10-digit API number.
            lateral: Lateral name.
            output_path: Optional output path for WCR file.

        Returns:
            Path to generated WCR file.

        Raises:
            ExcelGenerationError: If generation fails.
        """
        try:
            self.logger.info(f"Generating WCR for API={api}, Lateral={lateral}")

            # Load well data
            well_info, well_location = self.well_service.load_well(api, lateral)

            # Process survey
            survey = self.survey_service.process_survey(api, lateral)

            # Calculate clearances
            clearances = self.clearance_service.calculate_clearances(survey)

            # Calculate footage
            footage = self.clearance_service.calculate_section_footage(survey)

            # Generate WCR Excel file
            wcr_path = self.wcr_generator.generate_wcr(
                well_info,
                survey,
                clearances,
                footage,
                output_path
            )

            self.logger.info(f"WCR generated successfully: {wcr_path}")

            return wcr_path

        except Exception as e:
            self.logger.error(f"WCR generation failed: {e}", exc_info=True)
            raise ExcelGenerationError(
                f"Failed to generate WCR: {str(e)}",
                details={'api': api, 'lateral': lateral}
            )

    def get_wcr_summary(self, api: str, lateral: str):
        """
        Get WCR summary data without generating full report.

        Args:
            api: API number.
            lateral: Lateral name.

        Returns:
            Summary DataFrame.
        """
        try:
            # Load and process data
            well_info, _ = self.well_service.load_well(api, lateral)
            survey = self.survey_service.process_survey(api, lateral)
            clearances = self.clearance_service.calculate_clearances(survey)
            footage = self.clearance_service.calculate_section_footage(survey)

            # Create summary
            summary = self.wcr_generator.create_summary_dataframe(
                survey,
                clearances,
                footage
            )

            return summary

        except Exception as e:
            self.logger.error(f"Failed to get WCR summary: {e}", exc_info=True)
            raise
