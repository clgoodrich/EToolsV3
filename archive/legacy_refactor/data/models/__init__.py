"""
Data models (DTOs) for EToolsV3.

This package contains all data transfer objects used throughout the application.
"""

from data.models.well import (
    WellLocation,
    WellInfo,
    CasingString,
    WellConstruction
)
from data.models.survey import (
    SurveyHeader,
    SurveyPoint,
    ProcessedSurvey,
    RawSurveyData,
    KOPDetectionResult
)
from data.models.plat import (
    PlatSection,
    PlatBoundary,
    AdjacentPlats,
    SpatialQuery
)
from data.models.clearance import (
    ClearancePoint,
    ClearanceResults,
    FootageCalculation,
    SectionFootage,
    WellboreSeparation
)

__all__ = [
    # Well models
    'WellLocation',
    'WellInfo',
    'CasingString',
    'WellConstruction',
    # Survey models
    'SurveyHeader',
    'SurveyPoint',
    'ProcessedSurvey',
    'RawSurveyData',
    'KOPDetectionResult',
    # Plat models
    'PlatSection',
    'PlatBoundary',
    'AdjacentPlats',
    'SpatialQuery',
    # Clearance models
    'ClearancePoint',
    'ClearanceResults',
    'FootageCalculation',
    'SectionFootage',
    'WellboreSeparation',
]
