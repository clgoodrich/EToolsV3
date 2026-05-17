"""
Clearance service for EToolsV3.

This service orchestrates clearance calculations including plat location,
boundary segmentation, and distance calculations.
"""

from typing import Optional
import pandas as pd

from data.repositories.plat_repository import PlatRepository, LocationRepository
from data.models.survey import ProcessedSurvey
from data.models.clearance import ClearanceResults, SectionFootage, FootageCalculation
from data.models.plat import SpatialQuery
from core.plat.locator import PlatLocator
from core.clearance.boundary_segmenter import BoundarySegmenter
from core.clearance.calculator import ClearanceCalculator
from config.logging_config import get_logger
from utils.errors import CalculationError

logger = get_logger(__name__)


class ClearanceService:
    """Service for clearance calculation operations."""

    def __init__(
        self,
        plat_repo: Optional[PlatRepository] = None,
        location_repo: Optional[LocationRepository] = None,
        locator: Optional[PlatLocator] = None,
        segmenter: Optional[BoundarySegmenter] = None,
        calculator: Optional[ClearanceCalculator] = None
    ):
        """
        Initialize clearance service.

        Args:
            plat_repo: Plat repository.
            location_repo: Location repository.
            locator: Plat locator.
            segmenter: Boundary segmenter.
            calculator: Clearance calculator.
        """
        self.plat_repo = plat_repo or PlatRepository()
        self.location_repo = location_repo or LocationRepository()
        self.locator = locator or PlatLocator()
        self.segmenter = segmenter or BoundarySegmenter()
        self.calculator = calculator or ClearanceCalculator()
        self.logger = logger

    def calculate_clearances(self, survey: ProcessedSurvey) -> ClearanceResults:
        """
        Full clearance calculation workflow.

        Args:
            survey: Processed survey with trajectory data.

        Returns:
            ClearanceResults with all distance measurements.

        Raises:
            CalculationError: If calculation fails.
        """
        try:
            self.logger.info(
                f"Calculating clearances for API={survey.header.api_number}, "
                f"Lateral={survey.header.lateral_name}"
            )

            # Create spatial query from survey trajectory
            spatial_query = SpatialQuery.from_survey_data(survey.data, buffer=1000.0)

            # Get plats within bounding box
            plat_df = self.plat_repo.get_plats_in_bbox(
                spatial_query.min_easting,
                spatial_query.max_easting,
                spatial_query.min_northing,
                spatial_query.max_northing,
                spatial_query.buffer
            )

            if plat_df.empty:
                raise CalculationError("No plat sections found for survey trajectory")

            # Convert to GeoDataFrame
            plat_gdf = self.plat_repo.get_plats_as_geodataframe(plat_df)

            # Assign sections to survey points
            survey_with_sections = self.locator.assign_section_to_points(
                survey.data,
                plat_gdf
            )

            # Segment boundaries for each plat
            plat_boundaries = {}
            for _, plat in plat_gdf.iterrows():
                boundary = self.segmenter.segment_polygon_boundaries(
                    plat['geometry'],
                    plat['Conc']
                )
                plat_boundaries[plat['Conc']] = boundary

            # Calculate clearances
            clearances = self.calculator.calculate_clearances(
                survey_with_sections,
                plat_boundaries
            )

            self.logger.info(
                f"Clearances calculated: {clearances.num_sections} sections, "
                f"Min clearance: {clearances.min_overall_clearance:.1f} ft"
            )

            return clearances

        except Exception as e:
            self.logger.error(f"Clearance calculation failed: {e}", exc_info=True)
            raise CalculationError(f"Failed to calculate clearances: {str(e)}")

    def calculate_section_footage(self, survey: ProcessedSurvey) -> SectionFootage:
        """
        Calculate footage in each section.

        Args:
            survey: Processed survey.

        Returns:
            SectionFootage with footage by section.
        """
        try:
            # Get section assignments
            footage_df = self.locator.calculate_footage_by_section(survey.data)

            # Create FootageCalculation objects
            section_footages = []
            for _, row in footage_df.iterrows():
                footage_calc = FootageCalculation(
                    section_conc=row['section_conc'],
                    section_label=self.locator.format_tsr_label(row['section_conc']),
                    total_footage=row['footage'],
                    measured_depth_in=row['entry_md'],
                    measured_depth_out=row['exit_md']
                )
                section_footages.append(footage_calc)

            # Create summary
            total_drilled = footage_df['footage'].sum()

            footage = SectionFootage(
                api_number=survey.header.api_number,
                lateral_name=survey.header.lateral_name,
                section_footages=section_footages,
                total_drilled=total_drilled
            )

            self.logger.info(
                f"Calculated footage for {len(section_footages)} sections, "
                f"Total: {total_drilled:.1f} ft"
            )

            return footage

        except Exception as e:
            self.logger.error(f"Footage calculation failed: {e}", exc_info=True)
            raise CalculationError(f"Failed to calculate footage: {str(e)}")
