"""
Well service for EToolsV3.

This service provides well-related operations orchestrating repositories and business logic.
"""

from typing import Optional

from data.repositories.well_repository import WellRepository
from data.repositories.casing_repository import CasingRepository
from data.models.well import WellInfo, WellLocation, WellConstruction
from config.logging_config import get_logger
from utils.errors import WellNotFoundError, DatabaseError

logger = get_logger(__name__)


class WellService:
    """Service for well operations."""

    def __init__(
        self,
        well_repo: Optional[WellRepository] = None,
        casing_repo: Optional[CasingRepository] = None
    ):
        """
        Initialize well service.

        Args:
            well_repo: Well repository. If None, creates new instance.
            casing_repo: Casing repository. If None, creates new instance.
        """
        self.well_repo = well_repo or WellRepository()
        self.casing_repo = casing_repo or CasingRepository()
        self.logger = logger

    def load_well(self, api: str, lateral: str = '0000') -> tuple[WellInfo, WellLocation]:
        """
        Load complete well information.

        Args:
            api: 10-digit API number.
            lateral: Lateral identifier.

        Returns:
            Tuple of (WellInfo, WellLocation).

        Raises:
            WellNotFoundError: If well not found.
            DatabaseError: If database operation fails.
        """
        try:
            self.logger.info(f"Loading well API={api}, Lateral={lateral}")

            # Get well info and location
            well_info = self.well_repo.get_well_info(api, lateral)
            well_location = self.well_repo.get_well_location(api, lateral)

            self.logger.info(f"Well loaded: {well_info.well_name}")

            return well_info, well_location

        except WellNotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to load well: {e}", exc_info=True)
            raise DatabaseError(f"Failed to load well: {str(e)}")

    def validate_well_exists(self, api: str, lateral: str = '0000') -> bool:
        """
        Check if well exists before processing.

        Args:
            api: 10-digit API number.
            lateral: Lateral identifier.

        Returns:
            True if well exists, False otherwise.
        """
        return self.well_repo.well_exists(api, lateral)

    def get_well_construction(self, api: str) -> WellConstruction:
        """
        Get well construction data including casing.

        Args:
            api: 10-digit API number.

        Returns:
            WellConstruction object.

        Raises:
            DatabaseError: If retrieval fails.
        """
        try:
            return self.well_repo.get_casing_data(api)
        except Exception as e:
            self.logger.error(f"Failed to get well construction: {e}", exc_info=True)
            raise DatabaseError(f"Failed to get construction data: {str(e)}")

    def get_casing_strengths(self):
        """
        Get casing strength database.

        Returns:
            DataFrame with casing specifications.
        """
        return self.casing_repo.get_all_casing_strengths()
