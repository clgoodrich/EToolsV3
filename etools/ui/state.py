"""UI session state container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from etools.models import WellHeader
from etools.services import ClearanceResult, SurveyResult


@dataclass(slots=True)
class AppState:
    headers: list[WellHeader] = field(default_factory=list)
    primary: WellHeader | None = None
    surveys: dict[str, pd.DataFrame] = field(default_factory=dict)
    selected_citing: str | None = None
    processed: dict[str, SurveyResult] = field(default_factory=dict)
    clearances: dict[str, ClearanceResult] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


def empty_state() -> AppState:
    return AppState()
