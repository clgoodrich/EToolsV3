"""Pytest fixtures for the etools package.

The legacy fixtures that targeted the half-done PyQt refactor are kept under
``archive/legacy_refactor/tests/`` for reference only; they import modules
that no longer exist at the package root.
"""

from __future__ import annotations

import pytest

from etools.repositories import PlatRepository, SurveyRepository, WellRepository


@pytest.fixture(scope="session")
def well_repo() -> WellRepository:
    return WellRepository()


@pytest.fixture(scope="session")
def survey_repo() -> SurveyRepository:
    return SurveyRepository()


@pytest.fixture(scope="session")
def plat_repo() -> PlatRepository:
    return PlatRepository()


@pytest.fixture
def sample_api() -> str:
    return "4301354722"


@pytest.fixture
def sample_lateral() -> str:
    return "0000"
