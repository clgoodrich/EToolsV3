"""Shared 'Use as active well' promotion logic.

A *promote* turns parsed-PDF data (APD or WCR) sitting in ``AppState``
into the loaded-well shape the downstream tabs expect — a ``WellHeader``
in ``state.headers``/``state.primary`` plus a normalised survey in
``state.surveys`` — then runs the full post-load pipeline
(``state.post_load``: process survey → clearances → section geometry →
refresh every tab). Completing that pipeline also registers/updates the
well's workspace buffer (see :mod:`etools.ui.workspace`).

This used to be duplicated inline in both the Casing Review and WCR tabs.
It now lives here so:

* the manual "Use as active well" buttons delegate to it, and
* the Load Well tab can fire it **automatically** right after a parse,
  so loading a PDF immediately populates every tab with no extra click.

When the promote can't geolocate the well (no surface lat/lon derivable
from the PLSS or UTM), it returns ``False`` without disturbing state. In
the manual case (``silent=False``) it explains why; in the auto case
(``silent=True``) it stays quiet and leaves the manual button as a
fallback.
"""

from __future__ import annotations

from nicegui import ui

from etools.logging_setup import get_logger
from etools.ui.state import AppState

log = get_logger(__name__)


async def promote_apd_to_active(state: AppState, *, silent: bool = False) -> bool:
    """Promote ``state.apd_data`` to the active well. See module docstring."""
    from etools.core.casing_review.promote import (
        normalize_survey_dataframe,
        well_header_from_apd,
    )

    data = state.apd_data
    if data is None:
        if not silent:
            ui.notify("Parse an APD PDF first.", type="warning")
        return False
    try:
        header = well_header_from_apd(data)
    except Exception as exc:
        log.exception("promote.apd.header_failed")
        if not silent:
            ui.notify(f"Could not build well header: {exc}", type="negative")
        return False
    if header.surface_lat is None:
        if not silent:
            ui.notify(
                "APD has no PLSS section we can geolocate. Upload a survey PDF "
                "or load the well from the DB.",
                type="warning",
                multi_line=True,
                timeout=8000,
            )
        return False

    state.headers = [header]
    state.primary = header
    if state.casing_survey_df is not None and not state.casing_survey_df.empty:
        citing = header.citing_type or "Planned"
        state.surveys = {citing: normalize_survey_dataframe(state.casing_survey_df)}
        state.selected_citing = citing
    else:
        state.surveys = {}
        state.selected_citing = None
    state.processed = {}
    state.clearances = {}

    return await _run_post_load(state, header, what="APD")


async def promote_wcr_to_active(
    state: AppState, *, survey_df=None, silent: bool = False
) -> bool:
    """Promote ``state.wcr_data`` to the active well.

    ``survey_df`` lets the WCR tab pass the survey it resolved (DB lookup
    or PDF upload) directly; when omitted we fall back to
    ``state.wcr_survey_df``.
    """
    from etools.core.casing_review.promote import (
        normalize_survey_dataframe,
        well_header_from_wcr,
    )

    data = state.wcr_data
    if data is None:
        if not silent:
            ui.notify("Parse a WCR PDF first.", type="warning")
        return False
    try:
        header = well_header_from_wcr(data)
    except Exception as exc:
        log.exception("promote.wcr.header_failed")
        if not silent:
            ui.notify(f"Could not build well header: {exc}", type="negative")
        return False
    if header.surface_lat is None:
        if not silent:
            ui.notify(
                "WCR has no surface UTM or PLSS we can geolocate. Upload a "
                "survey PDF or load the well from the DB.",
                type="warning",
                multi_line=True,
                timeout=8000,
            )
        return False

    survey_df = survey_df if survey_df is not None else state.wcr_survey_df
    state.headers = [header]
    state.primary = header
    if survey_df is not None and not survey_df.empty:
        citing = header.citing_type or "AsDrilled"
        state.surveys = {citing: normalize_survey_dataframe(survey_df)}
        state.selected_citing = citing
    else:
        state.surveys = {}
        state.selected_citing = None
    state.processed = {}
    state.clearances = {}

    return await _run_post_load(state, header, what="WCR")


async def _run_post_load(state: AppState, header, *, what: str) -> bool:
    """Fire the shared post-load pipeline and report the result."""
    if state.post_load is None:
        ui.notify("Post-load orchestrator not registered.", type="warning")
        return False
    try:
        await state.post_load(switch_to_survey=False)
    except Exception as exc:
        log.exception("promote.post_load_failed", what=what)
        ui.notify(f"Promote post-load failed: {exc}", type="negative")
        return False
    ui.notify(
        f"Promoted {header.well_name or header.api} — other tabs populated.",
        type="positive",
        multi_line=True,
    )
    return True
