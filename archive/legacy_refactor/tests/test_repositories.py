"""
Integration tests for repositories.
"""

import pytest
from utils.errors import WellNotFoundError, SurveyNotFoundError


class TestWellRepository:
    """Tests for WellRepository."""

    def test_well_exists(self, well_repository, sample_api):
        """Test checking if well exists."""
        exists = well_repository.well_exists(sample_api)
        assert isinstance(exists, bool)

    def test_get_well_info_valid(self, well_repository, sample_api, sample_lateral):
        """Test retrieving well info for valid API."""
        try:
            well_info = well_repository.get_well_info(sample_api, sample_lateral)
            assert well_info.api_number == sample_api
        except WellNotFoundError:
            pytest.skip("Test well not found in database")

    def test_get_well_info_invalid(self, well_repository):
        """Test retrieving well info for invalid API."""
        with pytest.raises(WellNotFoundError):
            well_repository.get_well_info('0000000000', 'NonExistent')


class TestSurveyRepository:
    """Tests for SurveyRepository."""

    def test_survey_exists(self, survey_repository, sample_api, sample_lateral):
        """Test checking if survey exists."""
        exists = survey_repository.survey_exists(sample_api, sample_lateral)
        assert isinstance(exists, bool)

    def test_get_survey_data_valid(self, survey_repository, sample_api, sample_lateral):
        """Test retrieving survey data for valid well."""
        try:
            survey = survey_repository.get_survey_data(sample_api, sample_lateral)
            assert survey.api_number == sample_api
            assert not survey.measurements.empty
        except SurveyNotFoundError:
            pytest.skip("Test survey not found in database")

    def test_get_available_surveys(self, survey_repository, sample_api):
        """Test getting list of available surveys."""
        surveys = survey_repository.get_available_surveys(sample_api)
        assert isinstance(surveys, pd.DataFrame) or surveys.empty
