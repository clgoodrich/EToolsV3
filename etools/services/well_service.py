"""WellService — orchestrates well + survey repositories for the UI.

The UI does not talk to repositories directly. Services own the workflow,
return DTOs/dataframes, and centralize errors so the UI handles a small,
predictable surface.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from etools.logging_setup import get_logger
from etools.models import WellHeader, WellLookup
from etools.repositories import SurveyRepository, WellRepository

log = get_logger(__name__)


class WellNotFoundError(Exception):
    pass


@dataclass(slots=True)
class WellBundle:
    """Everything the UI needs after a 'Load Well' click."""

    headers: list[WellHeader]
    primary: WellHeader
    surveys: dict[str, pd.DataFrame]  # citing_type -> raw MD/INC/AZI frame


class WellService:
    def __init__(
        self,
        well_repo: WellRepository | None = None,
        survey_repo: SurveyRepository | None = None,
    ) -> None:
        self.well_repo = well_repo or WellRepository()
        self.survey_repo = survey_repo or SurveyRepository()

    def load(self, lookup: WellLookup) -> WellBundle:
        headers = self.well_repo.list_headers(lookup.api, lookup.lateral)
        if not headers:
            raise WellNotFoundError(
                f"No well found for API={lookup.api} lateral={lookup.lateral}"
            )

        # Prefer a "drilled" header as the primary if present; fall back to the
        # most recently uploaded one.
        primary = next(
            (h for h in headers if (h.citing_type or "").lower().startswith("drill")),
            sorted(
                headers,
                key=lambda h: h.upload_datetime or 0,
                reverse=True,
            )[0],
        )
        surveys = self.survey_repo.get_points_by_api_lateral(lookup.api, lookup.lateral)
        log.info(
            "well.loaded",
            api=lookup.api,
            lateral=lookup.lateral,
            headers=len(headers),
            citings=list(surveys.keys()),
            total_points=sum(len(df) for df in surveys.values()),
        )
        return WellBundle(headers=headers, primary=primary, surveys=surveys)

    def laterals_for(self, api: str) -> list[str]:
        return list(self.well_repo.laterals_for_api(api))
