"""Load Well tab — single entry point for every downstream workflow.

Three on-ramps, presented as sub-tabs:

* **From Database** — API + lateral lookup against DirectionalSurveyHeader.
* **From APD PDF** — drag-drop an APD application PDF, parse it, route the
  user to the Casing Review tab where the rest of the workflow happens.
* **From WCR PDF** — drag-drop a Form 8 WCR, parse it, route to the WCR
  tab.

Everything that used to live on the WCR / Casing Review tabs as upload +
parse controls now lives here, so each downstream tab can focus on the
post-parse work (display, edit, generate). State that needs to survive
reconnects flows through ``AppState``.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Awaitable, Callable, Union

from nicegui import events, ui

from etools.core.pdf.apd_parser import parse_apd_pdf
from etools.core.pdf.wcr_parser import parse_wcr_pdf
from etools.logging_setup import get_logger
from etools.models import WellLookup
from etools.repositories import SurveyRepository
from etools.ui.promote import promote_apd_to_active, promote_wcr_to_active
from etools.ui.state import AppState

LoadHandler = Callable[[WellLookup], Union[None, Awaitable[None]]]
RouteHandler = Callable[[], None]

log = get_logger(__name__)


def render_load_tab(
    state: AppState,
    on_load: LoadHandler,
    on_route_to_casing: RouteHandler | None = None,
    on_route_to_wcr: RouteHandler | None = None,
) -> Callable[[], None]:
    """Render the consolidated Load Well tab.

    ``on_route_to_casing`` / ``on_route_to_wcr`` are called after a
    successful APD / WCR parse so the user lands directly in the tab
    that's ready to work with the parsed data.
    """
    survey_repo = SurveyRepository()
    cache: dict = {}

    with ui.column().classes("p-6 gap-4 w-full max-w-4xl"):
        ui.label("Load Well").classes("text-2xl font-semibold")
        ui.label(
            "Pick one of three on-ramps. After loading you'll be routed to "
            "the right downstream tab."
        ).classes("text-sm text-gray-600")

        with ui.tabs().classes("w-full").props("dense") as entry_tabs:
            tab_db = ui.tab("From Database", icon="storage")
            tab_apd = ui.tab("From APD PDF", icon="upload_file")
            tab_wcr = ui.tab("From WCR PDF", icon="upload_file")

        with ui.tab_panels(entry_tabs, value=tab_db).classes("w-full"):
            # --- DB --------------------------------------------------
            with ui.tab_panel(tab_db):
                with ui.column().classes("gap-3"):
                    ui.label(
                        "Enter the 10-digit API number and a 4-character lateral "
                        "identifier (default 0000). Pulls from DirectionalSurveyHeader."
                    ).classes("text-sm text-gray-600")
                    with ui.row().classes("gap-2 items-end"):
                        api_input = ui.input(
                            "API (10 digits)",
                            value="4301354722",
                            validation={
                                "Must be 10 digits": lambda v: bool(v) and v.isdigit() and len(v) == 10
                            },
                        ).props("dense outlined").classes("w-56")
                        lateral_input = ui.input(
                            "Lateral",
                            value="0000",
                            validation={"Max 4 chars": lambda v: v is not None and len(v) <= 4},
                        ).props("dense outlined").classes("w-32")

                        async def submit_db() -> None:
                            api = (api_input.value or "").strip()
                            lateral = (lateral_input.value or "0000").strip() or "0000"
                            try:
                                lookup = WellLookup(api=api, lateral=lateral)
                            except ValueError as exc:
                                ui.notify(f"Invalid input: {exc}", type="warning")
                                return
                            result = on_load(lookup)
                            if asyncio.iscoroutine(result):
                                await result

                        ui.button("Load Well", icon="download", on_click=submit_db).props(
                            "color=primary"
                        )

            # --- APD PDF ---------------------------------------------
            with ui.tab_panel(tab_apd):
                with ui.column().classes("gap-3"):
                    ui.label(
                        "Drop an APD application PDF. After parsing you'll be "
                        "routed to the Casing Review tab."
                    ).classes("text-sm text-gray-600")
                    with ui.row().classes("gap-3 items-center w-full"):
                        apd_upload = ui.upload(
                            label="Drop APD PDF",
                            auto_upload=True,
                            multiple=False,
                            on_upload=lambda e: _handle_apd_upload(e),
                            on_rejected=lambda e: ui.notify(
                                f"Upload rejected: {e}", type="negative"
                            ),
                        ).classes("max-w-md").props("accept=.pdf flat dense")
                        cache["apd_mode"] = (
                            ui.select(
                                options={
                                    "rules": "Rules only",
                                    "rules+llm": "Rules + LLM backfill",
                                    "llm": "LLM only",
                                },
                                value="rules+llm",
                                label="Parse mode",
                            )
                            .props("dense outlined")
                            .classes("w-56")
                        )
                        cache["apd_parse_btn"] = ui.button(
                            "Parse APD",
                            icon="play_arrow",
                            on_click=lambda: _parse_apd_now(),
                        ).props("color=primary dense")
                        cache["apd_parse_btn"].disable()
                    cache["apd_status"] = ui.label("No APD uploaded.").classes(
                        "text-xs text-slate-600"
                    )

            # --- WCR PDF ---------------------------------------------
            with ui.tab_panel(tab_wcr):
                with ui.column().classes("gap-3"):
                    ui.label(
                        "Drop a DOGM Form 8 WCR. After parsing you'll be "
                        "routed to the WCR tab."
                    ).classes("text-sm text-gray-600")
                    with ui.row().classes("gap-3 items-center w-full"):
                        wcr_upload = ui.upload(
                            label="Drop WCR PDF",
                            auto_upload=True,
                            multiple=False,
                            on_upload=lambda e: _handle_wcr_upload(e),
                            on_rejected=lambda e: ui.notify(
                                f"Upload rejected: {e}", type="negative"
                            ),
                        ).classes("max-w-md").props("accept=.pdf flat dense")
                        cache["wcr_mode"] = (
                            ui.select(
                                options={
                                    "rules": "Rules (regex)",
                                    "rules+llm": "Rules + LLM",
                                    "llm": "LLM only",
                                },
                                value="rules+llm",
                                label="Parse mode",
                            )
                            .props("dense outlined")
                            .classes("w-56")
                        )
                        cache["wcr_pages"] = (
                            ui.select(
                                options={
                                    "5": "First 5 pages (Form 8)",
                                    "10": "First 10 pages",
                                    "all": "All pages (incl. DDR)",
                                },
                                value="5",
                                label="Pages",
                            )
                            .props("dense outlined")
                            .classes("w-56")
                        )
                        cache["wcr_parse_btn"] = ui.button(
                            "Parse WCR",
                            icon="play_arrow",
                            on_click=lambda: _parse_wcr_now(),
                        ).props("color=primary dense")
                        cache["wcr_parse_btn"].disable()
                    cache["wcr_status"] = ui.label("No WCR uploaded.").classes(
                        "text-xs text-slate-600"
                    )

        ui.separator()

        @ui.refreshable
        def summary() -> None:
            primary = state.primary
            if primary is None:
                ui.label("No well loaded.").classes("text-gray-500 italic")
                return
            with ui.card().classes("w-full"):
                ui.label(primary.well_name or "(unnamed)").classes("text-xl font-medium")
                ui.label(f"{primary.operator or '—'}").classes("text-sm text-gray-600")
                ui.separator().classes("my-2")
                with ui.grid(columns=4).classes("gap-x-6 gap-y-1 text-sm"):
                    rows = [
                        ("API / Lateral", f"{primary.api} / {primary.lateral}"),
                        ("Citing", primary.citing_type or "—"),
                        ("Survey Co.", primary.survey_company or "—"),
                        ("Survey Type", primary.survey_type or "—"),
                        ("Surface Lat", primary.surface_lat),
                        ("Surface Lon", primary.surface_lon),
                        ("Elevation", primary.surface_elevation),
                        ("North Ref", primary.north_reference or "—"),
                        ("Grid Conv.", primary.grid_convergence),
                        ("Grid Scale", primary.grid_scale_factor),
                        ("UTM Zone", primary.utm_zone or "—"),
                        ("PLSS", primary.plss_location or "—"),
                    ]
                    for label, value in rows:
                        ui.label(label).classes("text-gray-500")
                        ui.label(str(value) if value not in (None, "") else "—")
                if state.surveys:
                    counts = " · ".join(f"{k}: {len(v)} pts" for k, v in state.surveys.items())
                    ui.label(f"Surveys → {counts}").classes("text-xs text-gray-500")

        summary()

    # ------------------------------------------------------------------
    # APD upload + parse handlers
    # ------------------------------------------------------------------
    async def _handle_apd_upload(e: events.UploadEventArguments) -> None:
        upload = getattr(e, "file", None) or getattr(e, "content", None)
        name = getattr(upload, "name", None) or getattr(e, "name", "uploaded.pdf")
        cache["apd_status"].text = f"Saving {name}…"
        try:
            tmp_path = await _save_upload(upload, name)
        except Exception as exc:
            ui.notify(f"Upload failed: {exc}", type="negative")
            return
        state.apd_pdf_path = tmp_path
        state.apd_pdf_name = name
        state.apd_data = None
        try:
            apd_upload.reset()
        except Exception:
            pass
        cache["apd_status"].text = f"Loaded {name}. Click 'Parse APD' to extract."
        cache["apd_parse_btn"].enable()

    async def _parse_apd_now() -> None:
        tmp_path = state.apd_pdf_path
        if not tmp_path:
            ui.notify("Upload an APD PDF first.", type="warning")
            return
        mode = cache["apd_mode"].value or "rules+llm"
        cache["apd_parse_btn"].disable()
        cache["apd_status"].text = f"Parsing {state.apd_pdf_name} (mode={mode})…"
        try:
            data = await asyncio.to_thread(parse_apd_pdf, tmp_path, mode=mode)
        except Exception as exc:
            log.exception("load_tab.apd_parse_failed")
            ui.notify(f"Parse failed: {exc}", type="negative")
            cache["apd_status"].text = "Parse failed."
            cache["apd_parse_btn"].enable()
            return
        state.apd_data = data
        if (
            state.casing_frac_gradient_psi_per_ft is None
            and data.frac_gradient_psi_per_ft is not None
        ):
            state.casing_frac_gradient_psi_per_ft = data.frac_gradient_psi_per_ft
        # Look up a survey from the DB by API if possible.
        await _try_db_survey_for_apd()
        cache["apd_status"].text = (
            f"Parsed {state.apd_pdf_name}: "
            f"{data.well_name or '(unnamed)'}  API {data.api or '—'}"
        )
        cache["apd_parse_btn"].enable()
        # Land the user on Casing Review, then auto 'Use as active well':
        # promote runs the full pipeline (survey → clearance → geometry)
        # and refreshes every tab. If the well can't be geolocated yet,
        # promote no-ops quietly and we fall back to a plain refresh so
        # Casing Review still shows the parsed APD + a manual promote button.
        if on_route_to_casing is not None:
            on_route_to_casing()
        promoted = await promote_apd_to_active(state, silent=True)
        if not promoted:
            if state.fire_refresh is not None:
                try:
                    await state.fire_refresh()
                except Exception as exc:
                    log.warning("load_tab.apd_fire_refresh.failed", error=str(exc))
            ui.notify(
                "APD parsed — review on the Casing Review tab.", type="positive"
            )

    async def _try_db_survey_for_apd() -> None:
        data = state.apd_data
        if data is None or not data.api:
            return
        api10 = data.api[:10]
        try:
            results = await asyncio.to_thread(
                survey_repo.get_points_by_api_lateral, api10, "0000"
            )
        except Exception as exc:
            log.warning("load_tab.apd_db_survey_failed", error=str(exc))
            return
        chosen = next(
            (c for c in ("AsDrilled", "Planned") if c in results and not results[c].empty),
            None,
        )
        if chosen is None:
            return
        state.casing_survey_df = results[chosen]
        state.casing_survey_label = f"DB / {chosen} ({len(results[chosen])} stations)"

    # ------------------------------------------------------------------
    # WCR upload + parse handlers
    # ------------------------------------------------------------------
    async def _handle_wcr_upload(e: events.UploadEventArguments) -> None:
        upload = getattr(e, "file", None) or getattr(e, "content", None)
        name = getattr(upload, "name", None) or getattr(e, "name", "uploaded.pdf")
        cache["wcr_status"].text = f"Saving {name}…"
        try:
            tmp_path = await _save_upload(upload, name)
        except Exception as exc:
            ui.notify(f"Upload failed: {exc}", type="negative")
            return
        state.wcr_pdf_path = tmp_path
        state.wcr_pdf_name = name
        state.wcr_data = None
        state.wcr_survey_df = None
        state.wcr_survey_label = None
        state.wcr_survey_source = None
        try:
            wcr_upload.reset()
        except Exception:
            pass
        cache["wcr_status"].text = f"Loaded {name}. Click 'Parse WCR' to extract."
        cache["wcr_parse_btn"].enable()

    async def _parse_wcr_now() -> None:
        tmp_path = state.wcr_pdf_path
        if not tmp_path:
            ui.notify("Upload a WCR PDF first.", type="warning")
            return
        mode = cache["wcr_mode"].value or "rules+llm"
        pages_val = cache["wcr_pages"].value or "5"
        max_pages = None if pages_val == "all" else int(pages_val)
        cache["wcr_parse_btn"].disable()
        cache["wcr_status"].text = f"Parsing {state.wcr_pdf_name} (mode={mode})…"
        try:
            data = await asyncio.to_thread(
                parse_wcr_pdf,
                tmp_path,
                use_llm=None,
                mode=mode,
                max_pages=max_pages,
                mine_ddr_events=False,
            )
        except Exception as exc:
            log.exception("load_tab.wcr_parse_failed")
            ui.notify(f"Parse failed: {exc}", type="negative")
            cache["wcr_status"].text = "Parse failed."
            cache["wcr_parse_btn"].enable()
            return
        state.wcr_data = data
        await _try_db_survey_for_wcr()
        cache["wcr_status"].text = (
            f"Parsed {state.wcr_pdf_name}: "
            f"{data.well_name or '(unnamed)'}  API {data.api or '—'}"
        )
        cache["wcr_parse_btn"].enable()
        # Land on the WCR tab, then auto 'Use as active well' (same
        # degrade-to-refresh fallback as the APD path).
        if on_route_to_wcr is not None:
            on_route_to_wcr()
        promoted = await promote_wcr_to_active(
            state, survey_df=state.wcr_survey_df, silent=True
        )
        if not promoted:
            if state.fire_refresh is not None:
                try:
                    await state.fire_refresh()
                except Exception as exc:
                    log.warning("load_tab.wcr_fire_refresh.failed", error=str(exc))
            ui.notify("WCR parsed — review on the WCR tab.", type="positive")

    async def _try_db_survey_for_wcr() -> None:
        data = state.wcr_data
        if data is None or not data.api:
            return
        api10 = data.api[:10]
        try:
            results = await asyncio.to_thread(
                survey_repo.get_points_by_api_lateral, api10, "0000"
            )
        except Exception as exc:
            log.warning("load_tab.wcr_db_survey_failed", error=str(exc))
            return
        chosen = next(
            (c for c in ("AsDrilled", "Planned") if c in results and not results[c].empty),
            None,
        )
        if chosen is None:
            return
        state.wcr_survey_df = results[chosen]
        state.wcr_survey_label = f"DB / {chosen} ({len(results[chosen])} stations)"
        state.wcr_survey_source = "db"

    return summary.refresh


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


async def _save_upload(upload, name: str) -> str:
    suffix = Path(name).suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    tmp.close()
    if upload is not None and hasattr(upload, "save"):
        await upload.save(tmp_path)
    elif upload is not None and hasattr(upload, "read"):
        read_result = upload.read()
        if hasattr(read_result, "__await__"):
            data = await read_result
        else:
            data = read_result
        Path(tmp_path).write_bytes(data if isinstance(data, bytes) else bytes(data))
    else:
        raise RuntimeError(
            f"Don't know how to read upload object: {type(upload).__name__}"
        )
    return tmp_path
