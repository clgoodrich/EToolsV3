"""
Coordinate conversion for EToolsV3.

This module provides coordinate transformations between different systems:
- Latitude/Longitude (WGS84)
- UTM (Universal Transverse Mercator)
- State Plane
- Grid coordinates with convergence angles
"""

import math
from typing import Tuple, Optional
import numpy as np
import pandas as pd
from pyproj import Transformer, CRS, Proj
import utm

from config.settings import settings
from config.logging_config import get_logger
from utils.errors import CoordinateTransformationError

logger = get_logger(__name__)


class CoordinateConverter:
    """
    Handles coordinate transformations between different coordinate systems.

    Primarily used for converting between lat/lon and UTM coordinates for
    wellbore trajectory calculations.
    """

    def __init__(self, utm_zone: int = 12, utm_hemisphere: str = 'N'):
        """
        Initialize coordinate converter.

        Args:
            utm_zone: UTM zone number (default 12 for Utah).
            utm_hemisphere: 'N' for northern hemisphere, 'S' for southern.
        """
        self.utm_zone = utm_zone
        self.utm_hemisphere = utm_hemisphere
        self.logger = logger

        # Create coordinate transformers
        self.wgs84 = CRS('EPSG:4326')  # WGS84 lat/lon
        self.utm = CRS(f'EPSG:269{utm_zone}')  # UTM Zone 12N for Utah

        # Transformers
        self.latlon_to_utm_transformer = Transformer.from_crs(
            self.wgs84,
            self.utm,
            always_xy=True
        )
        self.utm_to_latlon_transformer = Transformer.from_crs(
            self.utm,
            self.wgs84,
            always_xy=True
        )

    def latlon_to_utm(
        self,
        latitude: float,
        longitude: float,
        elevation: Optional[float] = None
    ) -> Tuple[float, float, int, str]:
        """
        Convert latitude/longitude to UTM coordinates.

        Args:
            latitude: Latitude in decimal degrees.
            longitude: Longitude in decimal degrees.
            elevation: Optional elevation in feet.

        Returns:
            Tuple of (easting, northing, zone_number, zone_letter).

        Raises:
            CoordinateTransformationError: If conversion fails.
        """
        try:
            # Use utm library for conversion
            easting, northing, zone_number, zone_letter = utm.from_latlon(
                latitude,
                longitude
            )

            self.logger.debug(
                f"Converted lat/lon ({latitude:.6f}, {longitude:.6f}) "
                f"to UTM ({easting:.2f}, {northing:.2f}) Zone {zone_number}{zone_letter}"
            )

            return easting, northing, zone_number, zone_letter

        except Exception as e:
            self.logger.error(f"Failed to convert lat/lon to UTM: {e}", exc_info=True)
            raise CoordinateTransformationError(
                f"Lat/Lon to UTM conversion failed: {str(e)}",
                details={'lat': latitude, 'lon': longitude}
            )

    def utm_to_latlon(
        self,
        easting: float,
        northing: float,
        zone_number: Optional[int] = None,
        zone_letter: Optional[str] = None
    ) -> Tuple[float, float]:
        """
        Convert UTM coordinates to latitude/longitude.

        Args:
            easting: UTM easting in meters.
            northing: UTM northing in meters.
            zone_number: UTM zone number (uses default if None).
            zone_letter: UTM zone letter (uses hemisphere if None).

        Returns:
            Tuple of (latitude, longitude) in decimal degrees.

        Raises:
            CoordinateTransformationError: If conversion fails.
        """
        try:
            if zone_number is None:
                zone_number = self.utm_zone

            if zone_letter is None:
                zone_letter = 'N' if self.utm_hemisphere == 'N' else 'M'

            latitude, longitude = utm.to_latlon(
                easting,
                northing,
                zone_number,
                zone_letter
            )

            self.logger.debug(
                f"Converted UTM ({easting:.2f}, {northing:.2f}) "
                f"to lat/lon ({latitude:.6f}, {longitude:.6f})"
            )

            return latitude, longitude

        except Exception as e:
            self.logger.error(f"Failed to convert UTM to lat/lon: {e}", exc_info=True)
            raise CoordinateTransformationError(
                f"UTM to Lat/Lon conversion failed: {str(e)}",
                details={'easting': easting, 'northing': northing}
            )

    def calculate_convergence_angle(
        self,
        latitude: float,
        longitude: float
    ) -> float:
        """
        Calculate grid convergence angle at a given location.

        Grid convergence is the angle between true north and grid north.

        Args:
            latitude: Latitude in decimal degrees.
            longitude: Longitude in decimal degrees.

        Returns:
            Convergence angle in degrees (positive = grid north is east of true north).

        Raises:
            CoordinateTransformationError: If calculation fails.
        """
        try:
            # Get central meridian for UTM zone
            central_meridian = (self.utm_zone - 1) * 6 - 180 + 3

            # Calculate convergence angle using standard formula
            # γ = (λ - λ₀) * sin(φ)
            # where λ is longitude, λ₀ is central meridian, φ is latitude

            delta_lon = longitude - central_meridian
            convergence = delta_lon * math.sin(math.radians(latitude))

            self.logger.debug(
                f"Calculated convergence angle: {convergence:.4f}° "
                f"at ({latitude:.6f}, {longitude:.6f})"
            )

            return convergence

        except Exception as e:
            self.logger.error(f"Failed to calculate convergence: {e}", exc_info=True)
            raise CoordinateTransformationError(
                f"Convergence calculation failed: {str(e)}",
                details={'lat': latitude, 'lon': longitude}
            )

    def apply_convergence_to_azimuth(
        self,
        azimuth_true: float,
        convergence: float
    ) -> float:
        """
        Convert true north azimuth to grid north azimuth.

        Args:
            azimuth_true: Azimuth relative to true north (degrees).
            convergence: Grid convergence angle (degrees).

        Returns:
            Azimuth relative to grid north (degrees).
        """
        azimuth_grid = azimuth_true - convergence

        # Normalize to 0-360
        while azimuth_grid < 0:
            azimuth_grid += 360
        while azimuth_grid >= 360:
            azimuth_grid -= 360

        return azimuth_grid

    def remove_convergence_from_azimuth(
        self,
        azimuth_grid: float,
        convergence: float
    ) -> float:
        """
        Convert grid north azimuth to true north azimuth.

        Args:
            azimuth_grid: Azimuth relative to grid north (degrees).
            convergence: Grid convergence angle (degrees).

        Returns:
            Azimuth relative to true north (degrees).
        """
        azimuth_true = azimuth_grid + convergence

        # Normalize to 0-360
        while azimuth_true < 0:
            azimuth_true += 360
        while azimuth_true >= 360:
            azimuth_true -= 360

        return azimuth_true

    def offset_coordinates(
        self,
        easting: float,
        northing: float,
        distance: float,
        azimuth: float
    ) -> Tuple[float, float]:
        """
        Calculate new coordinates offset by distance and azimuth.

        Args:
            easting: Starting easting coordinate.
            northing: Starting northing coordinate.
            distance: Offset distance in feet.
            azimuth: Azimuth in degrees (0 = north, 90 = east).

        Returns:
            Tuple of (new_easting, new_northing).
        """
        # Convert azimuth to radians
        azimuth_rad = math.radians(azimuth)

        # Calculate offsets
        delta_east = distance * math.sin(azimuth_rad)
        delta_north = distance * math.cos(azimuth_rad)

        new_easting = easting + delta_east
        new_northing = northing + delta_north

        return new_easting, new_northing

    def calculate_distance(
        self,
        easting1: float,
        northing1: float,
        easting2: float,
        northing2: float
    ) -> float:
        """
        Calculate straight-line distance between two points.

        Args:
            easting1: First point easting.
            northing1: First point northing.
            easting2: Second point easting.
            northing2: Second point northing.

        Returns:
            Distance in feet.
        """
        delta_east = easting2 - easting1
        delta_north = northing2 - northing1

        distance = math.sqrt(delta_east**2 + delta_north**2)
        return distance

    def calculate_azimuth(
        self,
        easting1: float,
        northing1: float,
        easting2: float,
        northing2: float
    ) -> float:
        """
        Calculate azimuth from point 1 to point 2.

        Args:
            easting1: First point easting.
            northing1: First point northing.
            easting2: Second point easting.
            northing2: Second point northing.

        Returns:
            Azimuth in degrees (0 = north, 90 = east).
        """
        delta_east = easting2 - easting1
        delta_north = northing2 - northing1

        # Calculate azimuth using atan2
        azimuth_rad = math.atan2(delta_east, delta_north)
        azimuth = math.degrees(azimuth_rad)

        # Normalize to 0-360
        while azimuth < 0:
            azimuth += 360
        while azimuth >= 360:
            azimuth -= 360

        return azimuth

    def convert_survey_coordinates(
        self,
        survey_df: pd.DataFrame,
        surface_lat: float,
        surface_lon: float,
        convergence: Optional[float] = None
    ) -> pd.DataFrame:
        """
        Convert survey trajectory coordinates to multiple systems.

        Assumes survey_df has columns: northing, easting (relative to surface).

        Args:
            survey_df: Survey DataFrame with northing/easting columns.
            surface_lat: Surface location latitude.
            surface_lon: Surface location longitude.
            convergence: Grid convergence angle. If None, will be calculated.

        Returns:
            Survey DataFrame with added coordinate columns.

        Raises:
            CoordinateTransformationError: If conversion fails.
        """
        try:
            df = survey_df.copy()

            # Get surface UTM coordinates
            surf_easting, surf_northing, zone, letter = self.latlon_to_utm(
                surface_lat,
                surface_lon
            )

            # Calculate absolute UTM coordinates
            df['utm_easting'] = surf_easting + df['easting']
            df['utm_northing'] = surf_northing + df['northing']

            # Convert to lat/lon for each point
            latitudes = []
            longitudes = []

            for _, row in df.iterrows():
                lat, lon = self.utm_to_latlon(
                    row['utm_easting'],
                    row['utm_northing'],
                    zone,
                    letter
                )
                latitudes.append(lat)
                longitudes.append(lon)

            df['latitude'] = latitudes
            df['longitude'] = longitudes

            # Calculate convergence if not provided
            if convergence is None:
                convergence = self.calculate_convergence_angle(surface_lat, surface_lon)

            df['convergence_angle'] = convergence

            self.logger.info(f"Converted coordinates for {len(df)} survey points")

            return df

        except Exception as e:
            self.logger.error(f"Failed to convert survey coordinates: {e}", exc_info=True)
            raise CoordinateTransformationError(
                f"Survey coordinate conversion failed: {str(e)}"
            )
