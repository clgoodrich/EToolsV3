"""UI session state container.

Everything that needs to survive a WebSocket reconnect lives here. Tabs
should NEVER cache load-bearing data in closure-local variables — those
get GC'd whenever NiceGUI re-renders the root page (e.g. after a 5+
second blocking refresh causes a heartbeat timeout). Closure-locals
should hold only the live UI element references created during the
current render.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import pandas as pd

from etools.models import APDPdfData, WellHeader
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
    # Bound by the root page to its post-load orchestrator. Lets any tab
    # promote a freshly-loaded well into shared state and trigger the
    # full pipeline (process survey → calculate clearances → refresh
    # every tab) the same way the Load Well tab does.
    post_load: Callable[[], Awaitable[None]] | None = None

    # ---- Casing Review tab persistent state ----------------------------
    # Survives WebSocket reconnects so the tab can rebuild its full UI
    # (parsed APD card, editable inputs, design table, WBD diagram, last
    # output link) from a fresh page render.
    apd_data: APDPdfData | None = None
    apd_pdf_path: str | None = None
    apd_pdf_name: str | None = None
    # Survey DataFrame used to interpolate TVD for each casing string.
    # Sourced from either DB lookup or PDF upload. Cleared on Clear All.
    casing_survey_df: Optional[pd.DataFrame] = None
    casing_survey_label: str | None = None
    # Per-string engineering-knob overrides. Keyed by design-slot index
    # (0=Surface, 1=Intermediate, 2=Production, 3=Liner) → {attr: value}.
    casing_overrides: dict[int, dict[str, Any]] = field(default_factory=dict)
    # Frac gradient override (psi/ft) the user typed into the input box.
    casing_frac_gradient_psi_per_ft: float | None = None
    # Path of the most recently generated Casing Review xlsx.
    casing_last_output_path: Optional[Path] = None


def empty_state() -> AppState:
    return AppState()
