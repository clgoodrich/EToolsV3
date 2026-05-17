"""
PDF survey parser for EToolsV3.

This module extracts directional survey data from PDF files.
Wraps existing pdfminer functionality with clean interface and error handling.
"""

from typing import Optional, Tuple
import pandas as pd
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LTPage, LTChar, LTAnno, LAParams, LTTextBox, LTTextLine
from pdfminer.pdfpage import PDFPage
import re

from config.logging_config import get_logger
from utils.errors import PDFParseError

logger = get_logger(__name__)


class PDFDetailedAggregator(PDFPageAggregator):
    """Custom PDF aggregator that preserves text positioning."""

    def __init__(self, rsrcmgr, pageno=1, laparams=None):
        super().__init__(rsrcmgr, pageno=pageno, laparams=laparams)
        self.rows = []
        self.page_number = 0

    def receive_layout(self, ltpage):
        """Process layout and extract text with positions."""
        def render(item, page_number):
            if isinstance(item, (LTPage, LTTextBox)):
                for child in item:
                    render(child, page_number)
            elif isinstance(item, LTTextLine):
                child_str = ''
                for child in item:
                    if isinstance(child, (LTChar, LTAnno)):
                        child_str += child.get_text()

                child_str = ' '.join(child_str.split()).strip()
                if child_str:
                    # bbox = (x1, y1, x2, y2)
                    row = (
                        page_number,
                        item.bbox[0],  # x1
                        item.bbox[1],  # y1
                        item.bbox[2],  # x2
                        item.bbox[3],  # y2
                        child_str
                    )
                    self.rows.append(row)

        render(ltpage, self.page_number)
        self.page_number += 1

        # Sort by page, then by y-coordinate (descending)
        self.rows = sorted(self.rows, key=lambda x: (x[0], -x[2]))
        self.result = ltpage


class PDFSurveyParser:
    """Parser for extracting directional survey data from PDF files."""

    def __init__(self):
        """Initialize PDF parser."""
        self.logger = logger

    def parse_survey_from_pdf(self, pdf_path: str) -> pd.DataFrame:
        """
        Parse directional survey data from PDF file.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            DataFrame with columns: measured_depth, inclination, azimuth.

        Raises:
            PDFParseError: If parsing fails.
        """
        try:
            self.logger.info(f"Parsing PDF: {pdf_path}")

            # Extract text with positions
            text_data = self._extract_text_with_positions(pdf_path)

            if not text_data:
                raise PDFParseError("No text data extracted from PDF")

            # Convert to DataFrame
            df = pd.DataFrame(
                text_data,
                columns=['page', 'x1', 'y1', 'x2', 'y2', 'text']
            )

            # Parse survey data from text
            survey_df = self._parse_survey_data(df)

            if survey_df.empty:
                raise PDFParseError("No survey data found in PDF")

            self.logger.info(f"Successfully parsed {len(survey_df)} survey points")

            return survey_df

        except PDFParseError:
            raise
        except Exception as e:
            self.logger.error(f"PDF parsing failed: {e}", exc_info=True)
            raise PDFParseError(
                f"Failed to parse PDF: {str(e)}",
                details={'pdf_path': pdf_path}
            )

    def _extract_text_with_positions(self, pdf_path: str) -> list:
        """
        Extract text with bounding box positions from PDF.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            List of tuples (page, x1, y1, x2, y2, text).
        """
        resource_manager = PDFResourceManager()
        laparams = LAParams()
        device = PDFDetailedAggregator(resource_manager, laparams=laparams)
        interpreter = PDFPageInterpreter(resource_manager, device)

        with open(pdf_path, 'rb') as fp:
            for page in PDFPage.get_pages(fp):
                interpreter.process_page(page)

        return device.rows

    def _parse_survey_data(self, text_df: pd.DataFrame) -> pd.DataFrame:
        """
        Parse survey measurements from extracted text.

        Args:
            text_df: DataFrame with text and position columns.

        Returns:
            DataFrame with measured_depth, inclination, azimuth columns.
        """
        survey_points = []

        # Common patterns for survey data
        # MD pattern: number with optional decimal
        md_pattern = r'^\d+\.?\d*$'
        # INC/AZ pattern: decimal number
        angle_pattern = r'^\d+\.\d+$'

        # Group text by y-coordinate (rows)
        text_df['y_group'] = text_df['y1'].round(-1)  # Round to nearest 10

        for y_group, group in text_df.groupby('y_group'):
            # Sort by x-coordinate
            row_data = group.sort_values('x1')['text'].tolist()

            # Look for pattern: MD, INC, AZ
            if len(row_data) >= 3:
                try:
                    # Try to parse as survey point
                    md = self._try_parse_number(row_data[0])
                    inc = self._try_parse_number(row_data[1])
                    az = self._try_parse_number(row_data[2])

                    if md is not None and inc is not None and az is not None:
                        # Validate ranges
                        if 0 <= inc <= 180 and 0 <= az < 360:
                            survey_points.append({
                                'measured_depth': md,
                                'inclination': inc,
                                'azimuth': az
                            })
                except (ValueError, IndexError):
                    continue

        if not survey_points:
            return pd.DataFrame()

        survey_df = pd.DataFrame(survey_points)

        # Remove duplicates
        survey_df = survey_df.drop_duplicates()

        # Sort by measured depth
        survey_df = survey_df.sort_values('measured_depth').reset_index(drop=True)

        return survey_df

    def _try_parse_number(self, text: str) -> Optional[float]:
        """
        Try to parse text as a number.

        Args:
            text: Text to parse.

        Returns:
            Parsed number or None if not parseable.
        """
        try:
            # Remove commas
            text = text.replace(',', '')
            return float(text)
        except (ValueError, AttributeError):
            return None

    def validate_survey_data(self, survey_df: pd.DataFrame) -> Tuple[bool, list]:
        """
        Validate parsed survey data.

        Args:
            survey_df: Parsed survey DataFrame.

        Returns:
            Tuple of (is_valid, list_of_warnings).
        """
        warnings = []

        if survey_df.empty:
            return False, ["Survey data is empty"]

        # Check for required columns
        required = ['measured_depth', 'inclination', 'azimuth']
        missing = [col for col in required if col not in survey_df.columns]
        if missing:
            return False, [f"Missing columns: {', '.join(missing)}"]

        # Check for NaN values
        if survey_df[required].isnull().any().any():
            warnings.append("Survey contains null values")

        # Check measured depth monotonicity
        if not survey_df['measured_depth'].is_monotonic_increasing:
            warnings.append("Measured depth is not monotonically increasing")

        # Check inclination range
        if (survey_df['inclination'] < 0).any() or (survey_df['inclination'] > 180).any():
            warnings.append("Inclination values out of range")

        # Check azimuth range
        if (survey_df['azimuth'] < 0).any() or (survey_df['azimuth'] >= 360).any():
            warnings.append("Azimuth values out of range")

        is_valid = len(warnings) == 0
        return is_valid, warnings
