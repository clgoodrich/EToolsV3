"""
Survey service for EToolsV3.

This service orchestrates survey data processing including trajectory calculations,
coordinate transformations, and KOP detection.
"""

from typing import Optional
from pathlib import Path

from data.repositories.survey_repository import SurveyRepository
from data.models.survey import ProcessedSurvey, RawSurveyData, KOPDetectionResult
from core.survey.processor import SurveyProcessor
from core.survey.kop_detector import KOPDetector
from core.survey.validator import SurveyValidator
from core.pdf.parser import PDFSurveyParser
from core.coordinates.converter import CoordinateConverter
from core.coordinates.magnetic_field import MagneticFieldCalculator
from config.logging_config import get_logger
from utils.errors import SurveyNotFoundError, SurveyProcessingError, PDFParseError

logger = get_logger(__name__)


class SurveyService:
    """Service for survey processing operations."""

    def __init__(
        self,
        survey_repo: Optional[SurveyRepository] = None,
        processor: Optional[SurveyProcessor] = None,
        kop_detector: Optional[KOPDetector] = None,
        validator: Optional[SurveyValidator] = None,
        pdf_parser: Optional[PDFSurveyParser] = None
    ):
        """
        Initialize survey service.

        Args:
            survey_repo: Survey repository.
            processor: Survey processor.
            kop_detector: KOP detector.
            validator: Survey validator.
            pdf_parser: PDF parser.
        """
        self.survey_repo = survey_repo or SurveyRepository()
        self.processor = processor or SurveyProcessor()
        self.kop_detector = kop_detector or KOPDetector()
        self.validator = validator or SurveyValidator()
        self.pdf_parser = pdf_parser or PDFSurveyParser()
        self.logger = logger

    def process_survey(
        self,
        api: str,
        lateral: str,
        citing_type: Optional[str] = None,
        interpolate: bool = True
    ) -> ProcessedSurvey:
        """
        Complete survey processing workflow.

        This is the main entry point for survey processing. It:
        1. Fetches raw survey data from database
        2. Calculates trajectory using minimum curvature
        3. Converts coordinates (lat/lon, UTM, grid)
        4. Detects KOP
        5. Returns processed survey with all fields populated

        Args:
            api: 10-digit API number.
            lateral: Lateral name.
            citing_type: Optional citing type filter.
            interpolate: Whether to interpolate survey points.

        Returns:
            ProcessedSurvey with complete calculations.

        Raises:
            SurveyNotFoundError: If survey not found.
            SurveyProcessingError: If processing fails.
        """
        try:
            self.logger.info(f"Processing survey API={api}, Lateral={lateral}")

            # Fetch raw survey data
            raw_survey = self.survey_repo.get_survey_data(api, lateral, citing_type)

            # Validate
            is_valid, warnings = self.validator.validate(raw_survey.measurements)
            if warnings:
                for warning in warnings:
                    self.logger.warning(f"Survey validation: {warning}")

            # Process trajectory
            processed = self.processor.process_survey(raw_survey, interpolate)

            # Detect KOP
            kop_result = self.kop_detector.detect(processed.data)
            processed.kop_md = kop_result.measured_depth
            processed.kop_method = kop_result.method
            processed.kop_confidence = kop_result.confidence

            self.logger.info(
                f"Survey processed: {len(processed.data)} points, "
                f"KOP={processed.kop_md:.1f} ft, "
                f"Total MD={processed.total_md:.1f} ft"
            )

            return processed

        except SurveyNotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"Survey processing failed: {e}", exc_info=True)
            raise SurveyProcessingError(
                f"Failed to process survey: {str(e)}",
                details={'api': api, 'lateral': lateral}
            )

    def import_from_pdf(self, pdf_path: Path, api: str, lateral: str) -> ProcessedSurvey:
        """
        Import and process survey from PDF file.

        Args:
            pdf_path: Path to PDF file.
            api: API number for the survey.
            lateral: Lateral name.

        Returns:
            ProcessedSurvey.

        Raises:
            PDFParseError: If PDF parsing fails.
            SurveyProcessingError: If processing fails.
        """
        try:
            self.logger.info(f"Importing survey from PDF: {pdf_path}")

            # Parse PDF
            survey_df = self.pdf_parser.parse_survey_from_pdf(str(pdf_path))

            # Validate parsed data
            is_valid, warnings = self.pdf_parser.validate_survey_data(survey_df)
            if not is_valid:
                raise PDFParseError(f"Invalid survey data: {', '.join(warnings)}")

            # Note: PDF doesn't contain header info, so we need to get it from database
            # or have user provide it. For now, we'll create a basic RawSurveyData
            # This would need to be enhanced based on actual requirements

            self.logger.info(f"Successfully imported {len(survey_df)} points from PDF")

            # Return the dataframe for now - calling code can process it further
            return survey_df

        except PDFParseError:
            raise
        except Exception as e:
            self.logger.error(f"PDF import failed: {e}", exc_info=True)
            raise PDFParseError(f"Failed to import PDF: {str(e)}")

    def calculate_kop(self, survey: ProcessedSurvey) -> KOPDetectionResult:
        """
        Calculate KOP for existing survey.

        Args:
            survey: Processed survey.

        Returns:
            KOPDetectionResult.
        """
        return self.kop_detector.detect(survey.data)

    def get_available_surveys(self, api: str):
        """
        Get list of available surveys for a well.

        Args:
            api: API number.

        Returns:
            DataFrame with available surveys.
        """
        return self.survey_repo.get_available_surveys(api)
