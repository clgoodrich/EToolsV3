"""
Magnetic field calculations for EToolsV3.

This module provides magnetic field parameter calculations including:
- Magnetic declination
- Magnetic dip angle
- Total magnetic field strength

Uses the World Magnetic Model (WMM) via PyGeoMag library.
"""

from datetime import datetime
from typing import Tuple, Optional
import numpy as np
from pygeomag import GeoMag

from config.logging_config import get_logger
from utils.errors import MagneticFieldError

logger = get_logger(__name__)


class MagneticFieldCalculator:
    """
    Calculates magnetic field parameters for a given location and time.

    Uses the World Magnetic Model (WMM) for accurate magnetic field calculations.
    """

    def __init__(self):
        """Initialize magnetic field calculator."""
        self.logger = logger
        self.geomag = GeoMag()

    @staticmethod
    def get_decimal_year(date: Optional[datetime] = None) -> float:
        """
        Calculate decimal year from datetime.

        Args:
            date: Datetime object. If None, uses current date.

        Returns:
            Year as decimal (e.g., 2024.5 for mid-year 2024).
        """
        if date is None:
            date = datetime.now()

        year_start = datetime(date.year, 1, 1)
        year_end = datetime(date.year + 1, 1, 1)

        year_length = (year_end - year_start).total_seconds()
        year_elapsed = (date - year_start).total_seconds()

        return date.year + (year_elapsed / year_length)

    def calculate_magnetic_field(
        self,
        latitude: float,
        longitude: float,
        altitude: float = 0.0,
        date: Optional[datetime] = None
    ) -> Tuple[float, float, float]:
        """
        Calculate magnetic field parameters for a location.

        Args:
            latitude: Latitude in decimal degrees.
            longitude: Longitude in decimal degrees.
            altitude: Altitude in meters above MSL (default 0).
            date: Date for calculation. If None, uses current date.

        Returns:
            Tuple of (declination, dip, total_field):
                - declination: Magnetic declination in degrees (+ east, - west)
                - dip: Magnetic dip angle in degrees (+ down, - up)
                - total_field: Total field strength in nanoTesla

        Raises:
            MagneticFieldError: If calculation fails.
        """
        try:
            # Get decimal year
            decimal_year = self.get_decimal_year(date)

            # Calculate magnetic field using GeoMag
            result = self.geomag.calculate(
                glat=latitude,
                glon=longitude,
                alt=altitude / 1000.0,  # Convert meters to km
                time=decimal_year
            )

            declination = result.d  # Declination in degrees
            dip = result.i  # Inclination/dip in degrees
            total_field = result.f  # Total field in nanoTesla

            self.logger.debug(
                f"Magnetic field at ({latitude:.4f}, {longitude:.4f}): "
                f"Decl={declination:.2f}°, Dip={dip:.2f}°, Total={total_field:.1f}nT"
            )

            return declination, dip, total_field

        except Exception as e:
            self.logger.error(
                f"Failed to calculate magnetic field: {e}",
                exc_info=True
            )
            raise MagneticFieldError(
                f"Magnetic field calculation failed: {str(e)}",
                details={'lat': latitude, 'lon': longitude, 'alt': altitude}
            )

    def get_declination(
        self,
        latitude: float,
        longitude: float,
        altitude: float = 0.0,
        date: Optional[datetime] = None
    ) -> float:
        """
        Get magnetic declination only.

        Args:
            latitude: Latitude in decimal degrees.
            longitude: Longitude in decimal degrees.
            altitude: Altitude in meters above MSL.
            date: Date for calculation. If None, uses current date.

        Returns:
            Magnetic declination in degrees (+ east, - west).
        """
        declination, _, _ = self.calculate_magnetic_field(
            latitude,
            longitude,
            altitude,
            date
        )
        return declination

    def get_dip(
        self,
        latitude: float,
        longitude: float,
        altitude: float = 0.0,
        date: Optional[datetime] = None
    ) -> float:
        """
        Get magnetic dip angle only.

        Args:
            latitude: Latitude in decimal degrees.
            longitude: Longitude in decimal degrees.
            altitude: Altitude in meters above MSL.
            date: Date for calculation. If None, uses current date.

        Returns:
            Magnetic dip angle in degrees (+ down, - up).
        """
        _, dip, _ = self.calculate_magnetic_field(
            latitude,
            longitude,
            altitude,
            date
        )
        return dip

    def get_total_field(
        self,
        latitude: float,
        longitude: float,
        altitude: float = 0.0,
        date: Optional[datetime] = None
    ) -> float:
        """
        Get total magnetic field strength only.

        Args:
            latitude: Latitude in decimal degrees.
            longitude: Longitude in decimal degrees.
            altitude: Altitude in meters above MSL.
            date: Date for calculation. If None, uses current date.

        Returns:
            Total magnetic field strength in nanoTesla.
        """
        _, _, total_field = self.calculate_magnetic_field(
            latitude,
            longitude,
            altitude,
            date
        )
        return total_field

    def apply_declination_to_azimuth(
        self,
        azimuth_magnetic: float,
        declination: float
    ) -> float:
        """
        Convert magnetic north azimuth to true north azimuth.

        Args:
            azimuth_magnetic: Azimuth relative to magnetic north (degrees).
            declination: Magnetic declination (degrees, + east).

        Returns:
            Azimuth relative to true north (degrees).
        """
        azimuth_true = azimuth_magnetic + declination

        # Normalize to 0-360
        while azimuth_true < 0:
            azimuth_true += 360
        while azimuth_true >= 360:
            azimuth_true -= 360

        return azimuth_true

    def remove_declination_from_azimuth(
        self,
        azimuth_true: float,
        declination: float
    ) -> float:
        """
        Convert true north azimuth to magnetic north azimuth.

        Args:
            azimuth_true: Azimuth relative to true north (degrees).
            declination: Magnetic declination (degrees, + east).

        Returns:
            Azimuth relative to magnetic north (degrees).
        """
        azimuth_magnetic = azimuth_true - declination

        # Normalize to 0-360
        while azimuth_magnetic < 0:
            azimuth_magnetic += 360
        while azimuth_magnetic >= 360:
            azimuth_magnetic -= 360

        return azimuth_magnetic

    def convert_azimuth_reference(
        self,
        azimuth: float,
        from_reference: str,
        to_reference: str,
        declination: float,
        convergence: float
    ) -> float:
        """
        Convert azimuth between different reference systems.

        Args:
            azimuth: Input azimuth in degrees.
            from_reference: Source reference ('true', 'magnetic', or 'grid').
            to_reference: Target reference ('true', 'magnetic', or 'grid').
            declination: Magnetic declination in degrees.
            convergence: Grid convergence in degrees.

        Returns:
            Azimuth in target reference system (degrees).

        Raises:
            ValueError: If invalid reference system specified.
        """
        # Normalize input references
        from_ref = from_reference.lower()
        to_ref = to_reference.lower()

        if from_ref == to_ref:
            return azimuth

        # Convert to true north first
        if from_ref == 'magnetic':
            azimuth_true = self.apply_declination_to_azimuth(azimuth, declination)
        elif from_ref == 'grid':
            azimuth_true = azimuth + convergence
        elif from_ref == 'true':
            azimuth_true = azimuth
        else:
            raise ValueError(f"Invalid from_reference: {from_reference}")

        # Normalize
        while azimuth_true < 0:
            azimuth_true += 360
        while azimuth_true >= 360:
            azimuth_true -= 360

        # Convert from true north to target
        if to_ref == 'magnetic':
            result = self.remove_declination_from_azimuth(azimuth_true, declination)
        elif to_ref == 'grid':
            result = azimuth_true - convergence
        elif to_ref == 'true':
            result = azimuth_true
        else:
            raise ValueError(f"Invalid to_reference: {to_reference}")

        # Final normalization
        while result < 0:
            result += 360
        while result >= 360:
            result -= 360

        return result

    def calculate_field_components(
        self,
        latitude: float,
        longitude: float,
        altitude: float = 0.0,
        date: Optional[datetime] = None
    ) -> dict:
        """
        Calculate all magnetic field components.

        Args:
            latitude: Latitude in decimal degrees.
            longitude: Longitude in decimal degrees.
            altitude: Altitude in meters above MSL.
            date: Date for calculation. If None, uses current date.

        Returns:
            Dictionary with all magnetic field components:
                - declination: Declination in degrees
                - dip: Dip angle in degrees
                - total_field: Total field in nT
                - horizontal: Horizontal component in nT
                - north: North component in nT
                - east: East component in nT
                - vertical: Vertical component in nT
        """
        try:
            decimal_year = self.get_decimal_year(date)

            result = self.geomag.calculate(
                glat=latitude,
                glon=longitude,
                alt=altitude / 1000.0,
                time=decimal_year
            )

            return {
                'declination': result.d,
                'dip': result.i,
                'total_field': result.f,
                'horizontal': result.h,
                'north': result.x,
                'east': result.y,
                'vertical': result.z
            }

        except Exception as e:
            self.logger.error(f"Failed to calculate field components: {e}", exc_info=True)
            raise MagneticFieldError(
                f"Field component calculation failed: {str(e)}",
                details={'lat': latitude, 'lon': longitude}
            )
