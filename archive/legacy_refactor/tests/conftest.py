"""
Pytest configuration and fixtures for EToolsV3 tests.
"""

import pytest
import pandas as pd
from data.database import DatabaseManager, get_database_manager
from data.repositories.well_repository import WellRepository
from data.repositories.survey_repository import SurveyRepository
from data.repositories.plat_repository import PlatRepository
from data.repositories.casing_repository import CasingRepository
from config.settings import settings


@pytest.fixture
def db_manager():
    """Database manager fixture."""
    return get_database_manager()


@pytest.fixture
def well_repository(db_manager):
    """Well repository fixture."""
    return WellRepository(db_manager)


@pytest.fixture
def survey_repository(db_manager):
    """Survey repository fixture."""
    return SurveyRepository(db_manager)


@pytest.fixture
def plat_repository():
    """Plat repository fixture."""
    return PlatRepository()


@pytest.fixture
def casing_repository():
    """Casing repository fixture."""
    return CasingRepository()


@pytest.fixture
def sample_api():
    """Sample API number for testing."""
    return '4301354722'


@pytest.fixture
def sample_lateral():
    """Sample lateral name for testing."""
    return 'Reay_16-29-30-B4-2H'


@pytest.fixture
def sample_survey_data():
    """Sample survey data for testing."""
    return pd.DataFrame({
        'measured_depth': [0, 100, 200, 300, 400, 500],
        'inclination': [0, 5, 10, 15, 20, 25],
        'azimuth': [0, 45, 90, 135, 180, 225]
    })
