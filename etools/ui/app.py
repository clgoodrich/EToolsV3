"""NiceGUI application — top-level layout, header, and tab routing.

Phase 1 wires the *Load* and *Survey* tabs only. Tabs for Map/Viz, Clearance,
WCR, Plat Searcher, and PDF Import are stubbed and arrive in later phases.
"""

from __future__ import annotations

from nicegui import ui

from etools.logging_setup import get_logger, recent_errors
from etools.models import SurveyFrame, WellLookup
from etools.services import ClearanceService, SurveyService, WellService
from etools.services.well_service import WellNotFoundError
from etools.ui.state import AppState, reset_survey_edits
from etools.ui.workspace import (
    remove_document,
    switch_document,
    upsert_active_document,
)
from etools.ui.tabs.clearance_tab import render_clearance_tab
from etools.ui.tabs.load_tab import render_load_tab
from etools.ui.tabs.survey_tab import render_survey_tab
from etools.ui.tabs.plat_tab import render_plat_tab
from etools.ui.tabs.viz_tab import render_viz_tab
from etools.ui.tabs.casing_review_tab import render_casing_review_tab
from etools.ui.tabs.wcr_tab import render_wcr_tab

log = get_logger(__name__)


def _placeholder(name: str) -> None:
    with ui.column().classes("p-8 gap-2"):
        ui.label(name).classes("text-2xl font-semibold")
        ui.label("Coming in a later phase.").classes("text-gray-500")


def build_app() -> None:
    """Register the root page. Called once at import time."""

    # AppState lives at module scope so a transient WebSocket disconnect (which
    # causes NiceGUI to re-run @ui.page) doesn't wipe the user's loaded well,
    # processed survey, or clearance results. Services are also long-lived.
    persistent_state = AppState()
    service = WellService()
    survey_service = SurveyService()
    clearance_service = ClearanceService()

    # response_timeout=30 — root() awaits fire_refresh inline when the
    # persistent state already carries a loaded well. Survey + clearance +
    # viz tab refreshes total ~5 s; default 3 s response_timeout would
    # serve a fallback page that never fully initialises.
    @ui.page("/", response_timeout=30.0)
    async def root() -> None:
        state = persistent_state  # alias for readability inside the page
        log.info(
            "page.init",
            has_headers=bool(state.headers),
            has_surveys=bool(state.surveys),
            has_processed=bool(state.processed),
            has_clearances=bool(state.clearances),
        )

        # Hook NiceGUI's connect/disconnect events so we can correlate UI
        # crashes to the moment the WebSocket actually drops.
        try:
            import time as _t
            from nicegui import context
            client = context.client
            connect_t = {"t": _t.monotonic()}

            def _on_disconnect() -> None:
                # Pull the last few uncaught exceptions out of the ring so
                # the disconnect is correlated to a cause (instead of being
                # a context-free warning that says "websocket dropped").
                errs = recent_errors(3)
                tail = [{"type": e["type"], "msg": e["msg"][:200]} for e in errs]
                log.warning(
                    "page.disconnect",
                    client_id=getattr(client, "id", "?"),
                    uptime_s=round(_t.monotonic() - connect_t["t"], 2),
                    recent_errors=tail or None,
                )
                # Dump the most-recent full traceback so we can actually
                # debug it without scrolling through the rest of the log.
                if errs:
                    log.warning(
                        "page.disconnect.last_traceback",
                        traceback=errs[-1]["tb"],
                    )

            def _on_connect() -> None:
                connect_t["t"] = _t.monotonic()
                log.info("page.connect", client_id=getattr(client, "id", "?"))

            if hasattr(client, "on_disconnect"):
                client.on_disconnect(_on_disconnect)
            if hasattr(client, "on_connect"):
                client.on_connect(_on_connect)
        except Exception as exc:
            log.warning("page.hook.failed", error=str(exc))

        refresh_callbacks: list = []

        async def fire_refresh() -> None:
            """Run every tab's refresh callback, yielding to the event loop
            between each one so the WebSocket heartbeat can fire. Without
            the yield, the cumulative ~5 s of Leaflet + Plotly rendering
            across all tabs blocks the loop long enough to drop the
            connection."""
            import asyncio as _asyncio
            for cb in refresh_callbacks:
                cb_name = getattr(cb, "__qualname__", repr(cb))
                try:
                    cb()
                except Exception as exc:  # pragma: no cover
                    log.exception("ui.refresh.failed", callback=cb_name, error=str(exc))
                    try:
                        ui.notify(
                            f"Tab refresh failed in {cb_name}: {exc}",
                            type="negative",
                            multi_line=True,
                            timeout=8000,
                        )
                    except Exception:
                        pass
                # Yield so the websocket heartbeat / browser pings get
                # processed between heavy refreshes.
                await _asyncio.sleep(0)

        # Shared busy dialog — opened while we process survey + clearance after
        # a load or PDF inject, so the user sees progress instead of a frozen UI.
        with ui.dialog().props("persistent no-escape-dismiss") as busy_dialog, ui.card().classes("min-w-[400px]"):
            ui.label("Working…").classes("text-lg font-semibold")
            with ui.row().classes("items-center gap-3"):
                ui.spinner(size="lg", color="primary")
                busy_status = ui.label("").classes("text-sm")

        def set_busy(msg: str) -> None:
            busy_status.text = msg

        async def post_load_orchestrate(*, switch_to_survey: bool = True) -> None:
            """Run after a well is loaded OR a PDF survey is injected.

            Processes the survey, calculates clearance, refreshes every tab,
            and (optionally) routes the user to the Survey tab. Wrapped in
            a busy dialog.

            ``switch_to_survey`` is False when invoked from a tab that wants
            to keep the user where they are (e.g. the Casing Review tab's
            'Use as active well' button — switching mid-handler from a
            different tab's slot context tends to drop the websocket).

            Heavily logged: each step emits a structured event before and
            after so a WebSocket drop can be correlated to an exact stage.
            """
            import asyncio
            import time
            import traceback
            from functools import partial
            loop = asyncio.get_running_loop()

            t0 = time.monotonic()
            log.info(
                "post_load.begin",
                citings=list(state.surveys.keys()) if state.surveys else [],
                survey_rows={k: len(v) for k, v in (state.surveys or {}).items()},
                headers=len(state.headers) if state.headers else 0,
                primary_api=state.primary.api if state.primary else None,
            )
            busy_dialog.open()
            try:
                # ---- Step 1: process survey ----
                if state.surveys and state.headers:
                    set_busy("Processing survey (KOP / landing detection)…")
                    log.info("post_load.process.start")
                    try:
                        state.processed = await loop.run_in_executor(
                            None,
                            partial(
                                survey_service.process,
                                state.headers,
                                state.surveys,
                                surface_override=state.shl_override,
                                convergence_override=state.convergence_override,
                            ),
                        )
                        log.info(
                            "post_load.process.done",
                            elapsed_s=round(time.monotonic() - t0, 2),
                            results={
                                k: {"kop_md": r.kop.md, "landing_md": r.landing_md, "points": len(r.frames[SurveyFrame.TRUE].points)}
                                for k, r in state.processed.items()
                            },
                        )
                    except Exception:
                        log.exception("post_load.process.failed", traceback=traceback.format_exc())
                        raise

                # ---- Step 2: clearances ----
                if state.processed:
                    set_busy("Calculating clearances against PLSS sections…")
                    log.info("post_load.clearance.start", citings=list(state.processed.keys()))

                    def _calc():
                        results = {}
                        for citing, sr in state.processed.items():
                            ps = sr.frames[SurveyFrame.TRUE]
                            log.info(
                                "post_load.clearance.calc.begin",
                                citing=citing,
                                points=len(ps.points),
                                kop_md=sr.kop.md,
                                landing_md=sr.landing_md,
                            )
                            try:
                                results[citing] = clearance_service.calculate(
                                    ps, kop_md=sr.kop.md, landing_md=sr.landing_md
                                )
                                log.info(
                                    "post_load.clearance.calc.done",
                                    citing=citing,
                                    result_points=len(results[citing].points),
                                    result_sections=len(results[citing].sections),
                                    summary_rows=len(results[citing].summary),
                                )
                            except Exception as exc:
                                log.exception(
                                    "post_load.clearance.calc.failed",
                                    citing=citing,
                                    error=str(exc),
                                    traceback=traceback.format_exc(),
                                )
                                raise
                        return results

                    try:
                        state.clearances = await loop.run_in_executor(None, _calc)
                        log.info(
                            "post_load.clearance.done",
                            elapsed_s=round(time.monotonic() - t0, 2),
                            citings=list(state.clearances.keys()),
                        )
                    except Exception:
                        log.exception("post_load.clearance.failed", traceback=traceback.format_exc())
                        raise

                # ---- Step 2b: build SectionDefinitions ----
                # Authoritative model for plat geometry, keyed by Conc.
                # Section sheets read/write per-segment overrides; Map &
                # Viz reads the resolved polygons so user edits in the
                # Casing Review tab reshape the on-map polygons.
                if state.clearances:
                    set_busy("Loading section geometry from plat + Grid Numbers DBs…")
                    log.info("post_load.section_defs.start")
                    try:
                        def _seed_section_defs():
                            from etools.core.casing_review.grid_corners import (
                                GridCornerCatalog,
                            )
                            from etools.core.casing_review.sections import (
                                build_section_definitions,
                            )
                            from etools.repositories import PlatRepository
                            concs: set[str] = set()
                            for cr in state.clearances.values():
                                if cr.sections is not None and not cr.sections.empty:
                                    concs.update(cr.sections["Conc"].dropna().tolist())
                            if not concs:
                                return {}
                            catalog = GridCornerCatalog()
                            repo = PlatRepository()
                            return build_section_definitions(
                                concs=sorted(concs), catalog=catalog, plat_repo=repo
                            )

                        new_defs = await loop.run_in_executor(None, _seed_section_defs)
                        # Preserve any existing user overrides for sections
                        # already in state — don't clobber unsaved edits.
                        for conc, sd in new_defs.items():
                            existing = state.section_definitions.get(conc)
                            if existing is not None:
                                sd.segment_overrides = existing.segment_overrides
                                sd.corner_overrides = existing.corner_overrides
                                sd.north_ref_choice = existing.north_ref_choice
                        state.section_definitions = new_defs
                        log.info(
                            "post_load.section_defs.done",
                            sections=len(state.section_definitions),
                            concs=sorted(state.section_definitions.keys())[:8],
                        )
                    except Exception:
                        log.exception("post_load.section_defs.failed")
                        # Non-fatal: section UI falls back to plat polygons
                        # and Map & Viz keeps working with raw clearance data.

                # ---- Step 2c: register/update workspace buffer ----
                # Snapshot the now-complete active well into its document
                # buffer (keyed by API/lateral) so it shows up in the
                # header switcher and can be returned to later. Merge
                # semantics: re-loading the same well updates in place.
                try:
                    doc_id = upsert_active_document(state)
                    log.info(
                        "post_load.workspace.upsert",
                        doc_id=doc_id,
                        documents=len(state.documents),
                    )
                except Exception:
                    log.exception("post_load.workspace.upsert.failed")

                # ---- Step 3: refresh UI ----
                set_busy("Refreshing UI…")
                log.info("post_load.refresh.start")
                try:
                    await fire_refresh()
                    log.info("post_load.refresh.done")
                except Exception:
                    log.exception("post_load.refresh.failed", traceback=traceback.format_exc())
                    raise

                # ---- Step 4: tab switch ----
                if switch_to_survey:
                    log.info("post_load.tab_switch.start", target="survey")
                    try:
                        tabs.set_value(tab_survey)
                        log.info("post_load.tab_switch.done")
                    except Exception:
                        log.exception("post_load.tab_switch.failed", traceback=traceback.format_exc())
                        raise
                else:
                    log.info("post_load.tab_switch.skipped")

            except Exception as exc:  # pragma: no cover
                log.exception(
                    "post_load.failed",
                    error=str(exc),
                    elapsed_s=round(time.monotonic() - t0, 2),
                    traceback=traceback.format_exc(),
                )
                try:
                    ui.notify(
                        f"Post-load processing failed: {exc}",
                        type="negative",
                        multi_line=True,
                        timeout=10000,
                    )
                except Exception:
                    pass
            finally:
                busy_dialog.close()
                log.info("post_load.end", elapsed_s=round(time.monotonic() - t0, 2))

        # Expose the orchestrator on AppState so any tab can promote a
        # freshly-loaded well into shared state and trigger the same
        # pipeline the Load Well tab uses.
        state.post_load = post_load_orchestrate
        # Also expose fire_refresh so handlers that mutate state need to
        # poke every tab into rebuilding from it (e.g. Load Well's PDF
        # parse hands off to the Casing Review / WCR tab, which must
        # refresh from the new state.apd_data / state.wcr_data).
        state.fire_refresh = fire_refresh

        async def clear_all_state() -> None:
            """Wipe all in-memory state and reset every tab back to its empty look."""
            state.headers = []
            state.primary = None
            state.surveys = {}
            state.processed = {}
            state.clearances = {}
            state.selected_citing = None
            reset_survey_edits(state)
            # Casing Review per-tab state
            state.apd_data = None
            state.apd_pdf_path = None
            state.apd_pdf_name = None
            state.casing_survey_df = None
            state.casing_survey_label = None
            state.casing_overrides = {}
            state.casing_frac_gradient_psi_per_ft = None
            state.bope_overrides = {}
            state.casing_last_output_path = None
            state.section_definitions = {}
            # Close every workspace buffer too — Clear All is the nuclear
            # reset, not just "close the active well".
            state.documents = {}
            state.active_doc_id = None
            await fire_refresh()
            ui.notify("All loaded data cleared.", type="info")

        # Confirmation dialog for the header Clear All button.
        with ui.dialog() as confirm_clear_dialog, ui.card():
            ui.label("Clear all data?").classes("text-lg font-semibold")
            ui.label(
                "This wipes the loaded well, processed survey, clearances, and "
                "any PDF-parsed data from memory. You'll need to re-load to "
                "work with the same well again."
            ).classes("text-sm text-gray-700 max-w-sm")
            with ui.row().classes("justify-end w-full mt-3 gap-2"):
                ui.button("Cancel", on_click=confirm_clear_dialog.close).props("flat")

                async def _do_clear() -> None:
                    confirm_clear_dialog.close()
                    await clear_all_state()

                ui.button(
                    "Clear everything",
                    icon="delete_forever",
                    on_click=_do_clear,
                ).props("color=negative")

        # ---- Header well switcher --------------------------------------
        # Reentrancy guard: switching fires fire_refresh, which rebuilds
        # the switcher's <select>. Rebuilding sets its value programmatically
        # (no change event), but guard anyway against overlapping switches.
        switch_guard = {"busy": False}

        async def _on_doc_switch(new_id: str | None) -> None:
            if not new_id or new_id == state.active_doc_id or switch_guard["busy"]:
                return
            switch_guard["busy"] = True
            set_busy("Switching well…")
            busy_dialog.open()
            changed = False
            try:
                changed = switch_document(state, new_id)
                if changed:
                    await fire_refresh()
            except Exception as exc:
                log.exception("workspace.switch.failed", new_id=new_id)
                ui.notify(f"Switch failed: {exc}", type="negative")
            finally:
                busy_dialog.close()
                switch_guard["busy"] = False
            if changed:
                doc = state.documents.get(new_id)
                ui.notify(
                    f"Switched to {doc.label}" if doc else "Switched well",
                    type="info",
                )

        async def _close_active_doc() -> None:
            if state.active_doc_id is None:
                return
            closed = state.documents.get(state.active_doc_id)
            set_busy("Closing well…")
            busy_dialog.open()
            try:
                remove_document(state, state.active_doc_id)
                await fire_refresh()
            except Exception as exc:
                log.exception("workspace.close.failed")
                ui.notify(f"Close failed: {exc}", type="negative")
            finally:
                busy_dialog.close()
            ui.notify(
                f"Closed {closed.label}" if closed else "Closed well", type="info"
            )

        @ui.refreshable
        def doc_switcher() -> None:
            docs = state.documents
            if not docs:
                return
            # Tag each well with where it came from (APD / WCR / DB) so
            # multiple open files are distinguishable at a glance.
            options = {
                doc_id: f"{d.label}  [{d.source}]" if d.source else d.label
                for doc_id, d in docs.items()
            }
            with ui.row().classes("items-center gap-1"):
                (
                    ui.select(
                        options=options,
                        value=state.active_doc_id,
                        on_change=lambda e: _on_doc_switch(e.value),
                    )
                    .props("dense outlined dark options-dense")
                    .classes("min-w-[260px]")
                    .tooltip("Switch the active well — every tab reloads from it")
                )
                ui.button(icon="close", on_click=_close_active_doc).props(
                    "flat round dense color=white"
                ).tooltip("Close the active well")

        refresh_callbacks.append(doc_switcher.refresh)

        with ui.header().classes("items-center justify-between bg-slate-800 text-white"):
            with ui.row().classes("items-center gap-4"):
                ui.label("ETools — DOGM Directional Survey & WCR").classes(
                    "text-lg font-medium"
                )
                doc_switcher()
            with ui.row().classes("items-center gap-3"):
                ui.button(
                    "Clear all",
                    icon="delete_forever",
                    on_click=confirm_clear_dialog.open,
                ).props("flat color=white dense")
                ui.label("v0.1").classes("text-xs text-slate-300")

        with ui.tabs().classes("w-full") as tabs:
            tab_load = ui.tab("Load Well", icon="search")
            tab_casing = ui.tab("Casing Review", icon="construction")
            tab_wcr = ui.tab("WCR", icon="description")
            tab_survey = ui.tab("Survey", icon="timeline")
            tab_map = ui.tab("Map & Viz", icon="map")
            tab_clearance = ui.tab("Clearance", icon="straighten")
            tab_plat = ui.tab("Plat Searcher", icon="grid_on")

        import time as _tt

        def _tlog(name: str, t0: float) -> float:
            """Log one tab's render time; returns the start time for the next tab."""
            log.info("tab.render", tab=name, ms=round((_tt.monotonic() - t0) * 1000, 1))
            return _tt.monotonic()

        with ui.tab_panels(tabs, value=tab_load).classes("w-full"):
            _ts = _tt.monotonic()
            with ui.tab_panel(tab_load):
                async def load_handler(lookup: WellLookup) -> None:
                    try:
                        bundle = service.load(lookup)
                    except WellNotFoundError as exc:
                        ui.notify(str(exc), type="warning")
                        return
                    except Exception as exc:  # pragma: no cover - bubble up to user
                        log.exception("well.load.failed", error=str(exc))
                        ui.notify(f"Load failed: {exc}", type="negative")
                        return
                    state.headers = bundle.headers
                    state.primary = bundle.primary
                    state.surveys = bundle.surveys
                    state.selected_citing = next(iter(bundle.surveys), None)
                    state.processed = {}
                    state.clearances = {}
                    reset_survey_edits(state)
                    ui.notify(
                        f"Loaded {bundle.primary.well_name or bundle.primary.api} "
                        f"({sum(len(d) for d in bundle.surveys.values())} survey points)",
                        type="positive",
                    )
                    await post_load_orchestrate()

                load_refresh = render_load_tab(
                    state,
                    load_handler,
                    on_route_to_casing=lambda: tabs.set_value(tab_casing),
                    on_route_to_wcr=lambda: tabs.set_value(tab_wcr),
                )
                refresh_callbacks.append(load_refresh)
                _ts = _tlog("load", _ts)

            with ui.tab_panel(tab_survey):
                refresh_callbacks.append(render_survey_tab(state))
                _ts = _tlog("survey", _ts)

            with ui.tab_panel(tab_map):
                _viz_refresh = render_viz_tab(state)
                refresh_callbacks.append(_viz_refresh)
                state.viz_refresh = _viz_refresh
                _ts = _tlog("viz", _ts)
            with ui.tab_panel(tab_clearance):
                refresh_callbacks.append(render_clearance_tab(state))
                _ts = _tlog("clearance", _ts)
            with ui.tab_panel(tab_wcr):
                refresh_callbacks.append(render_wcr_tab(state))
                _ts = _tlog("wcr", _ts)
            with ui.tab_panel(tab_casing):
                refresh_callbacks.append(render_casing_review_tab(state))
                _ts = _tlog("casing", _ts)
            with ui.tab_panel(tab_plat):
                refresh_callbacks.append(render_plat_tab())
                _ts = _tlog("plat", _ts)

        # If the persistent_state already carries a loaded well (e.g. the
        # user uploaded an APD, the WebSocket dropped during heavy refresh
        # work, and they reconnected), fire every tab's refresh callback
        # once at the end of the page render so the tabs show that state
        # instead of their default empty placeholders.
        #
        # IMPORTANT: defer via ui.timer(once=True). Running fire_refresh
        # synchronously at page-render time blocks the event loop for 5+
        # seconds (Leaflet, Plotly, etc.), which causes the WebSocket
        # heartbeat to time out — the page disconnects, reconnects, and
        # re-enters this branch, creating an infinite reconnect loop.
        # The timer lets root() return first so the websocket gets a chance
        # to settle before the heavy work runs.
        if state.primary is not None or state.headers:
            log.info(
                "page.init.fire_refresh.inline",
                primary_api=state.primary.api if state.primary else None,
            )
            # Root is async — await fire_refresh directly. fire_refresh
            # yields to the event loop between tab callbacks, so the
            # websocket heartbeat stays alive throughout. No ui.timer
            # needed (and no stale-slot RuntimeError risk).
            await fire_refresh()
