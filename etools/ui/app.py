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
from etools.ui.state import AppState
from etools.ui.tabs.clearance_tab import render_clearance_tab
from etools.ui.tabs.load_tab import render_load_tab
from etools.ui.tabs.survey_tab import render_survey_tab
from etools.ui.tabs.pdf_tab import render_pdf_tab
from etools.ui.tabs.plat_tab import render_plat_tab
from etools.ui.tabs.viz_tab import render_viz_tab
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

    @ui.page("/")
    def root() -> None:
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

        def fire_refresh() -> None:
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

        # Shared busy dialog — opened while we process survey + clearance after
        # a load or PDF inject, so the user sees progress instead of a frozen UI.
        with ui.dialog().props("persistent no-escape-dismiss") as busy_dialog, ui.card().classes("min-w-[400px]"):
            ui.label("Working…").classes("text-lg font-semibold")
            with ui.row().classes("items-center gap-3"):
                ui.spinner(size="lg", color="primary")
                busy_status = ui.label("").classes("text-sm")

        def set_busy(msg: str) -> None:
            busy_status.text = msg

        async def post_load_orchestrate() -> None:
            """Run after a well is loaded OR a PDF survey is injected.

            Processes the survey, calculates clearance, refreshes every tab,
            and routes the user to the Survey tab. Wrapped in a busy dialog.

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
                            None, partial(survey_service.process, state.headers, state.surveys)
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

                # ---- Step 3: refresh UI ----
                set_busy("Refreshing UI…")
                log.info("post_load.refresh.start")
                try:
                    fire_refresh()
                    log.info("post_load.refresh.done")
                except Exception:
                    log.exception("post_load.refresh.failed", traceback=traceback.format_exc())
                    raise

                # ---- Step 4: tab switch ----
                log.info("post_load.tab_switch.start", target="survey")
                try:
                    tabs.set_value(tab_survey)
                    log.info("post_load.tab_switch.done")
                except Exception:
                    log.exception("post_load.tab_switch.failed", traceback=traceback.format_exc())
                    raise

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

        def clear_all_state() -> None:
            """Wipe all in-memory state and reset every tab back to its empty look."""
            state.headers = []
            state.primary = None
            state.surveys = {}
            state.processed = {}
            state.clearances = {}
            state.selected_citing = None
            fire_refresh()
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
                ui.button(
                    "Clear everything",
                    icon="delete_forever",
                    on_click=lambda: (clear_all_state(), confirm_clear_dialog.close()),
                ).props("color=negative")

        with ui.header().classes("items-center justify-between bg-slate-800 text-white"):
            ui.label("ETools — DOGM Directional Survey & WCR").classes("text-lg font-medium")
            with ui.row().classes("items-center gap-3"):
                ui.button(
                    "Clear all",
                    icon="delete_forever",
                    on_click=confirm_clear_dialog.open,
                ).props("flat color=white dense")
                ui.label("v0.1").classes("text-xs text-slate-300")

        with ui.tabs().classes("w-full") as tabs:
            tab_load = ui.tab("Load Well", icon="search")
            tab_survey = ui.tab("Survey", icon="timeline")
            tab_map = ui.tab("Map & Viz", icon="map")
            tab_clearance = ui.tab("Clearance", icon="straighten")
            tab_wcr = ui.tab("WCR", icon="description")
            tab_plat = ui.tab("Plat Searcher", icon="grid_on")
            tab_pdf = ui.tab("PDF Import", icon="upload_file")

        with ui.tab_panels(tabs, value=tab_load).classes("w-full"):
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
                    ui.notify(
                        f"Loaded {bundle.primary.well_name or bundle.primary.api} "
                        f"({sum(len(d) for d in bundle.surveys.values())} survey points)",
                        type="positive",
                    )
                    await post_load_orchestrate()

                load_refresh = render_load_tab(
                    state,
                    load_handler,
                    on_route_to_pdf=lambda: tabs.set_value(tab_pdf),
                )
                refresh_callbacks.append(load_refresh)

            with ui.tab_panel(tab_survey):
                refresh_callbacks.append(render_survey_tab(state))

            with ui.tab_panel(tab_map):
                refresh_callbacks.append(render_viz_tab(state))
            with ui.tab_panel(tab_clearance):
                refresh_callbacks.append(render_clearance_tab(state))
            with ui.tab_panel(tab_wcr):
                refresh_callbacks.append(render_wcr_tab(state))
            with ui.tab_panel(tab_plat):
                refresh_callbacks.append(render_plat_tab())
            with ui.tab_panel(tab_pdf):
                async def _on_pdf_inject() -> None:
                    # Return a coroutine so the caller (inject_into_pipeline) can
                    # await it inside the proper NiceGUI per-client slot context.
                    # asyncio.create_task() loses that context and the WebSocket
                    # disconnects mid-refresh.
                    await post_load_orchestrate()

                refresh_callbacks.append(
                    render_pdf_tab(state, on_inject=_on_pdf_inject)
                )
