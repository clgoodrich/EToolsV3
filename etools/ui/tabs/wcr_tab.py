"""WCR tab — generate the WCR Excel from a WCR PDF.

Flow:
    1. User uploads the WCR PDF (DOGM Form 8). It's parsed immediately
       (PyMuPDF + regex — fast, no LLM).
    2. The tab uses the API number from the PDF to look up a directional
       survey in the local SQL Server (UTRBDMSNET.DirectionalSurveyData).
    3. If a survey is found, the user can hit Generate immediately.
    4. If no survey is found, an upload widget appears for a directional
       survey PDF; that PDF is run through the same parse_survey_pdf
       pipeline the regular PDF import uses (Docling → rules → LLM →
       vision). The extracted MD/INC/AZI rows feed the generator.

The legacy "from DB bundle" flow stays at the bottom of the tab.
"""

from __future__ import annotations

import asyncio
import tempfile
import traceback
from pathlib import Path
from typing import Callable

from nicegui import app, events, ui

from etools.config import settings
from etools.core.pdf.parser import parse_survey_pdf
from etools.logging_setup import get_logger
from etools.models import WCRPdfData
from etools.repositories import SurveyRepository
from etools.services import WCRService
from etools.services.tracking_service import update_tracking_workbook
from etools.services.wcr_pdf_service import WCRPdfResult, WCRPdfService
from etools.ui.promote import promote_wcr_to_active
from etools.ui.state import AppState

log = get_logger(__name__)


def render_wcr_tab(state: AppState) -> Callable[[], None]:
    wcr_service = WCRService()
    wcr_pdf_service = WCRPdfService()
    survey_repo = SurveyRepository()
    cache: dict = {
        "bundle": None,
        "api": None,
        "lateral": None,
        "wcr_pdf_path": None,
        "wcr_pdf_name": None,
        "wcr_data": None,            # WCRPdfData from parse_wcr_pdf
        "survey_source": None,       # "db" or "pdf"
        "surveys": None,             # pd.DataFrame of MD/INC/AZI
        "surveys_label": None,       # human-readable origin
        "survey_pdf_lat": None,      # parsed surface lat from a survey PDF
        "survey_pdf_lon": None,
        "survey_pdf_elev": None,
        "survey_pdf_north_ref": None,
        # Cache that supports the edit cascade after a successful generate.
        "last_result": None,         # WCRPdfResult (carries points/sections/elev)
        "edit_inputs": {},           # name -> {"md": ui.input, "easting": ui.input, "northing": ui.input}
    }

    with ui.column().classes("p-4 gap-3 w-full"):
        ui.label("WCR").classes("text-xl font-semibold")

        # Empty-state when no WCR has been loaded.
        empty_state = ui.card().classes(
            "w-full bg-slate-50 border border-dashed border-slate-300 p-6"
        )
        with empty_state:
            ui.label("No WCR loaded").classes("text-sm font-semibold text-slate-700")
            ui.label(
                "Go to the Load Well tab → From WCR PDF to upload and parse "
                "a Form 8 WCR. You'll be routed back here automatically."
            ).classes("text-xs text-slate-600")

        # --- COMPACT ACTION BAR (visible once a WCR is parsed) --------
        action_bar = ui.card().classes(
            "w-full bg-slate-50 border border-slate-200"
        )
        action_bar.visible = False
        with action_bar:
            with ui.row().classes("gap-3 items-center w-full"):
                source_label = ui.label("").classes(
                    "text-xs text-slate-600 font-mono"
                )
                ui.space()
                survey_status = ui.label("").classes(
                    "text-xs px-2 py-1 rounded bg-slate-200 text-slate-700"
                )
                promote_btn = ui.button(
                    "Use as active well",
                    icon="upgrade",
                    on_click=lambda: promote_to_primary(),
                ).props("color=secondary dense")
                promote_btn.tooltip(
                    "Push this WCR + survey into shared state so Survey, "
                    "Map & Viz, and Clearance tabs populate with this well."
                )
                generate_btn = ui.button(
                    "Generate WCR Excel",
                    icon="description",
                    on_click=lambda: generate_from_pdf(),
                ).props("color=primary dense")
            # Survey-PDF fallback upload — visible only when no DB survey was found.
            survey_upload_row = ui.row().classes("gap-2 items-center mt-1")
            with survey_upload_row:
                survey_upload = ui.upload(
                    label="Survey PDF",
                    auto_upload=True,
                    multiple=False,
                    on_upload=lambda e: handle_survey_upload(e),
                    on_rejected=lambda e: ui.notify(
                        f"Upload rejected: {e}", type="negative"
                    ),
                ).classes("max-w-xs").props("accept=.pdf flat dense")
                survey_parse_status = ui.label("").classes("text-xs text-gray-600")
            survey_upload_row.visible = False
            generate_status = ui.label("").classes("text-xs text-slate-500")

        # --- COLLAPSIBLE WORK AREAS (default-collapsed) ----------------
        wcr_meta_card = ui.expansion(
            "Parsed WCR data", icon="description", value=False,
        ).classes("w-full")
        wcr_meta_card.visible = False

        ddr_card = ui.expansion(
            "Operation Summary Reports (DDR)", icon="receipt_long", value=False,
        ).classes("w-full")
        ddr_card.visible = False

        results_card = ui.expansion(
            "Generated output", icon="folder_open", value=False,
        ).classes("w-full")
        results_card.visible = False

        # Legacy DB flow stays inside its own expansion at the bottom.
        with ui.expansion("Legacy flow — generate from DB bundle", value=False).classes("w-full"):
            legacy_header_label = ui.label("Calculate clearances first.").classes("text-gray-500 italic")
            legacy_controls = ui.row().classes("gap-3 items-center")
            with legacy_controls:
                ui.label("Citing:").classes("text-sm")
                citing_select = (
                    ui.select(options=[], on_change=lambda _: rerender_legacy())
                    .props("dense outlined")
                    .classes("w-44")
                )
                ui.button(
                    "Generate from DB", icon="description", on_click=lambda: generate_legacy()
                ).props("color=primary")
                legacy_status = ui.label("").classes("text-sm text-gray-500 ml-2")
            legacy_controls.set_visibility(False)

            legacy_info_card = ui.card().classes("w-full")

        # Personal processing tracker (V2's "Update Personal Record").
        with ui.expansion(
            "Personal record — TrackingWCR.xlsx", icon="fact_check", value=False
        ).classes("w-full"):
            ui.label(
                "Logs this WCR review into your tracking workbook — one row per API, "
                "date filed pulled from the latest sundry, date processed = today."
            ).classes("text-xs text-gray-500")
            with ui.row().classes("gap-4 items-center flex-wrap"):
                ui.label("Submission included:").classes("text-sm text-gray-600")
                trk_comp = ui.checkbox("Completion summary")
                trk_drill = ui.checkbox("Drilling summary")
                trk_cmt = ui.checkbox("Cement bond log")
                trk_logs = ui.checkbox("Logs")
                trk_asdrilled = ui.checkbox("As-drilled Excel survey")
            with ui.row().classes("gap-4 items-center flex-wrap"):
                trk_action = ui.checkbox("Action taken —")
                trk_utms = ui.checkbox("UTMs")
                trk_footages = ui.checkbox("Footages")
                trk_perfs = ui.checkbox("Perfs")
                trk_depths = ui.checkbox("Depths")
                trk_other = ui.input("Other edit").props("dense outlined").classes("w-48")
                trk_returns = ui.input("Returns", value="0").props(
                    "dense outlined type=number"
                ).classes("w-24").tooltip("How many times this WCR was returned to the operator")
            with ui.row().classes("gap-3 items-center"):
                ui.button(
                    "Update Personal Record",
                    icon="fact_check",
                    on_click=lambda: update_personal_record(),
                ).props("color=primary")
                tracking_status = ui.label("").classes("text-sm text-gray-500")

    # ----------------------------------------------------------------------
    # Upload + parse moved to the Load Well tab → From WCR PDF.
    # This tab now reads state.wcr_data and renders it.
    # ----------------------------------------------------------------------
    async def _try_db_survey_lookup() -> None:
        data: WCRPdfData | None = cache.get("wcr_data")
        if data is None or not data.api:
            survey_status.text = "WCR PDF has no API — cannot search DB. Upload a survey PDF below."
            survey_upload_row.visible = True
            return
        api10 = data.api[:10]
        try:
            results = await asyncio.to_thread(survey_repo.get_points_by_api_lateral, api10, "0000")
        except Exception as exc:
            log.warning("wcr.db_survey_lookup_failed", error=str(exc))
            survey_status.text = (
                f"DB lookup failed for API {api10} ({exc}). Upload a survey PDF below."
            )
            survey_upload_row.visible = True
            return

        # Prefer As-Drilled if both planned and as-drilled exist.
        preference = ("AsDrilled", "Planned")
        chosen_citing = next((c for c in preference if c in results and not results[c].empty), None)
        if chosen_citing is None:
            survey_status.text = (
                f"No directional survey in DB for API {api10}. Upload a survey PDF below."
            )
            survey_upload_row.visible = True
            return

        df = results[chosen_citing]
        cache["surveys"] = df
        cache["surveys_label"] = f"DB / {chosen_citing} ({len(df)} stations)"
        cache["survey_source"] = "db"
        survey_status.text = f"Found {chosen_citing} survey in DB for API {api10}: {len(df)} stations."
        survey_status.classes(
            replace="text-sm px-3 py-2 rounded bg-green-100 text-green-800"
        )
        survey_upload_row.visible = False

    # ----------------------------------------------------------------------
    # Step 2 — survey PDF fallback
    # ----------------------------------------------------------------------
    async def handle_survey_upload(e: events.UploadEventArguments) -> None:
        upload = getattr(e, "file", None) or getattr(e, "content", None)
        name = getattr(upload, "name", None) or getattr(e, "name", "uploaded.pdf")
        survey_parse_status.text = f"Saving {name}…"
        try:
            tmp_path = await _save_upload(upload, name)
        except Exception as exc:
            ui.notify(f"Upload failed: {exc}", type="negative")
            survey_parse_status.text = "Upload failed."
            return
        try:
            survey_upload.reset()
        except Exception:
            pass

        survey_parse_status.text = (
            f"Parsing {name} (Docling + rules + LLM)… this can take 30–90 s."
        )
        try:
            parsed = await asyncio.to_thread(parse_survey_pdf, tmp_path)
        except Exception as exc:
            tb = traceback.format_exc()
            log.exception("wcr.survey_pdf_parse_failed")
            ui.notify(f"Survey PDF parse failed: {exc}", type="negative")
            survey_parse_status.text = f"Parse failed: {exc}"
            log.debug(tb)
            return

        if parsed.surveys is None or parsed.surveys.empty:
            survey_parse_status.text = (
                f"Parsed {name} but found no MD/INC/AZI rows. Try a different PDF."
            )
            return

        cache["surveys"] = parsed.surveys
        cache["surveys_label"] = f"PDF / {name} ({len(parsed.surveys)} stations)"
        cache["survey_source"] = "pdf"
        cache["survey_pdf_lat"] = parsed.surface_lat
        cache["survey_pdf_lon"] = parsed.surface_lon
        cache["survey_pdf_elev"] = parsed.surface_elevation_ft
        cache["survey_pdf_north_ref"] = parsed.north_reference or "grid"

        survey_parse_status.text = (
            f"Parsed {name}: {len(parsed.surveys)} survey stations "
            f"(layers: {', '.join(parsed.layers_used)})."
        )
        survey_status.text = f"Using surveys from {name}: {len(parsed.surveys)} stations."
        survey_status.classes(
            replace="text-sm px-3 py-2 rounded bg-green-100 text-green-800"
        )
        _refresh_generate_button()

    # ----------------------------------------------------------------------
    # Step 3 — generate
    # ----------------------------------------------------------------------
    def _refresh_generate_button() -> None:
        has_wcr = bool(cache.get("wcr_data"))
        has_survey = cache.get("surveys") is not None
        if has_wcr and has_survey:
            generate_btn.enable()
        else:
            generate_btn.disable()
        # Promote needs WCR data; a survey is optional (downstream tabs can
        # still light up partially without one).
        if has_wcr:
            promote_btn.enable()
        else:
            promote_btn.disable()

    async def promote_to_primary() -> None:
        # Manual 'Use as active well'. Shares one implementation with the
        # Load Well tab's auto-promote. The WCR tab keeps its resolved
        # survey in ``cache["surveys"]`` (DB lookup or PDF upload made
        # right here), so pass it through explicitly.
        await promote_wcr_to_active(
            state, survey_df=cache.get("surveys"), silent=False
        )

    def generate_from_pdf() -> None:
        pdf_path = cache.get("wcr_pdf_path")
        wcr_data: WCRPdfData | None = cache.get("wcr_data")
        surveys = cache.get("surveys")
        if not pdf_path or wcr_data is None:
            ui.notify("Upload a WCR PDF first.", type="warning")
            return
        if surveys is None or surveys.empty:
            ui.notify("No surveys available — upload a survey PDF.", type="warning")
            return
        # Reuse the already-parsed WCR data so we don't re-run Docling/regex.
        kwargs: dict = {
            "wcr_data": wcr_data,
            "surveys": surveys,
        }
        if cache.get("survey_source") == "pdf":
            if cache.get("survey_pdf_lat") is not None:
                kwargs["surface_lat"] = cache["survey_pdf_lat"]
            if cache.get("survey_pdf_lon") is not None:
                kwargs["surface_lon"] = cache["survey_pdf_lon"]
            if cache.get("survey_pdf_elev") is not None:
                kwargs["surface_elevation_ft"] = cache["survey_pdf_elev"]
            if cache.get("survey_pdf_north_ref"):
                kwargs["north_reference"] = cache["survey_pdf_north_ref"]
        try:
            result = wcr_pdf_service.generate(**kwargs)
        except Exception as exc:
            log.exception("wcr.generate_failed")
            ui.notify(f"WCR generation failed: {exc}", type="negative")
            return

        cache["last_result"] = result
        path = result.output_path
        rel = Path(path).name
        generate_status.text = f"Saved {rel}"
        download_url = _serve_output_file(path)
        _render_results(
            results_card,
            result,
            download_url,
            str(path),
            edit_inputs_cache=cache["edit_inputs"],
            on_edit=lambda: recalculate_edits(),
            on_save=lambda: save_edited_excel(),
        )
        results_card.visible = True
        ui.notify(f"WCR generated: {rel}", type="positive")

    # ----------------------------------------------------------------------
    # Edit + cascade
    # ----------------------------------------------------------------------
    def _collect_edits() -> list[dict] | None:
        result = cache.get("last_result")
        inputs = cache.get("edit_inputs") or {}
        if result is None or not inputs:
            return None
        edits: list[dict] = []
        try:
            for row in result.location_rows:
                w = inputs.get(row.name)
                if w is None:
                    continue
                md_val = _parse_float(w["md"].value)
                e_val = _parse_float(w["easting"].value)
                n_val = _parse_float(w["northing"].value)
                # Only treat a cell as an "override" when the user actually
                # changed it (within ±0.5 ft of the original = no change,
                # because the input display is rounded to whole feet).
                e_changed = e_val is not None and not _close(e_val, w.get("orig_easting"), 0.5)
                n_changed = n_val is not None and not _close(n_val, w.get("orig_northing"), 0.5)
                edit = {"name": row.name}
                # MD: always send (changed or not) — the interpolation needs it.
                edit["measured_depth"] = md_val if md_val is not None else row.measured_depth
                # E/N: only send when truly changed — else the interpolated
                # value from MD should win.
                if e_changed:
                    edit["easting"] = e_val
                if n_changed:
                    edit["northing"] = n_val
                edits.append(edit)
        except (KeyError, AttributeError) as exc:
            ui.notify(f"Could not read edits: {exc}", type="negative")
            return None
        return edits


    def _close(a, b, tol: float) -> bool:
        if a is None or b is None:
            return False
        try:
            return abs(float(a) - float(b)) <= tol
        except (TypeError, ValueError):
            return False

    def recalculate_edits() -> None:
        # Wrap everything — this is called from on('blur') which fires on
        # browser focus changes, page unload, tab close, etc. Any uncaught
        # exception inside a UI event handler can take down the websocket
        # or the process depending on timing, so we swallow + log.
        try:
            result = cache.get("last_result")
            if result is None or result.sections is None:
                return
            edits = _collect_edits()
            if not edits:
                return
            new_rows = wcr_pdf_service.recompute_rows(
                edits=edits,
                points=result.points,
                sections=result.sections,
                elevation_ft=result.elevation_ft,
            )
            result.location_rows = new_rows
            inputs = cache.get("edit_inputs") or {}
            for r in new_rows:
                w = inputs.get(r.name)
                if w is None:
                    continue
                try:
                    w["tvd_label"].text = _fmt_num(r.tvd, 2)
                    w["fnl_label"].text = _fmt_num(r.fnl, 2)
                    w["fsl_label"].text = _fmt_num(r.fsl, 2)
                    w["fel_label"].text = _fmt_num(r.fel, 2)
                    w["fwl_label"].text = _fmt_num(r.fwl, 2)
                    w["sec_label"].text = r.section or "—"
                    w["twp_label"].text = r.township or "—"
                    w["twpdir_label"].text = r.township_dir or "—"
                    w["rng_label"].text = r.range or "—"
                    w["rngdir_label"].text = r.range_dir or "—"
                    w["base_label"].text = r.baseline or "—"
                except Exception:
                    # Widget may have been disposed (page disconnect / rerender).
                    log.debug("wcr.recompute.label_update_skipped", row=r.name)
        except Exception as exc:
            log.exception("wcr.recompute_failed")
            try:
                ui.notify(f"Recalculation failed: {exc}", type="negative")
            except Exception:
                pass

    def save_edited_excel() -> None:
        result = cache.get("last_result")
        if result is None:
            ui.notify("Generate the WCR first.", type="warning")
            return
        try:
            path = wcr_pdf_service.rewrite_excel(
                pdf_data=result.pdf_data,
                location_rows=result.location_rows,
                output_path=result.output_path,
            )
        except Exception as exc:
            log.exception("wcr.rewrite_failed")
            ui.notify(f"Save failed: {exc}", type="negative")
            return
        generate_status.text = f"Saved {Path(path).name}"
        ui.notify(f"WCR updated: {Path(path).name}", type="positive")

    # ----------------------------------------------------------------------
    # Legacy DB flow (kept for backwards compatibility)
    # ----------------------------------------------------------------------
    def load_legacy_bundle() -> None:
        if state.primary is None:
            return
        api = state.primary.api
        lateral = state.primary.lateral
        if cache.get("api") == api and cache.get("lateral") == lateral and cache.get("bundle") is not None:
            return
        try:
            cache["bundle"] = wcr_service.load_bundle(api, lateral)
            cache["api"] = api
            cache["lateral"] = lateral
        except Exception as exc:  # pragma: no cover
            ui.notify(f"WCR data fetch failed: {exc}", type="negative")
            cache["bundle"] = None

    def rerender_legacy() -> None:
        if state.primary is None:
            legacy_controls.set_visibility(False)
            legacy_header_label.visible = True
            return
        load_legacy_bundle()
        bundle = cache.get("bundle")
        if bundle is None or bundle.info is None:
            legacy_header_label.text = "No WCR data found for this well."
            legacy_header_label.visible = True
            legacy_controls.set_visibility(False)
            return
        legacy_header_label.visible = False
        legacy_controls.set_visibility(True)

        info = bundle.info
        legacy_info_card.clear()
        with legacy_info_card:
            with ui.grid(columns=4).classes("gap-x-6 gap-y-1 text-sm"):
                pairs = [
                    ("Well", info.well_name),
                    ("Operator", info.operator),
                    ("API / Lateral", f"{info.api_well_no[:10]} / {info.api_well_no[10:]}"),
                    ("Type", info.well_type),
                    ("Status", info.well_status),
                    ("Spud", _fmt_date(info.spud_date)),
                    ("Completed", _fmt_date(info.completion_date)),
                    ("Elevation (ft)", info.elevation_ft),
                ]
                for label, value in pairs:
                    ui.label(label).classes("text-gray-500")
                    ui.label(str(value) if value not in (None, "") else "—")

    def generate_legacy() -> None:
        if not state.clearances:
            ui.notify("Calculate clearances first.", type="warning")
            return
        citing = citing_select.value or next(iter(state.clearances), None)
        if citing not in state.clearances:
            ui.notify("No clearance data for selected citing.", type="warning")
            return
        clearance = state.clearances[citing]
        load_legacy_bundle()
        bundle = cache.get("bundle")
        if bundle is None or bundle.info is None:
            ui.notify("No WCR info available for this well.", type="negative")
            return
        try:
            path = wcr_service.generate(
                api=state.primary.api,
                lateral=state.primary.lateral,
                summary_footages=clearance.summary,
                bundle=bundle,
                points=clearance.points,
            )
        except Exception as exc:  # pragma: no cover
            ui.notify(f"WCR generation failed: {exc}", type="negative")
            raise
        rel = Path(path).name
        legacy_status.text = f"Saved {rel}"
        ui.notify(f"WCR generated: {rel}", type="positive")

    def update_personal_record() -> None:
        # Resolve the well from whichever flow is active (DB load or WCR PDF).
        api = well_name = operator = None
        if state.primary is not None:
            api = state.primary.api
            well_name = state.primary.well_name
            operator = state.primary.operator
        data = cache.get("wcr_data")
        if not api and data is not None and data.api:
            api = data.api[:10]
        if data is not None:
            well_name = well_name or data.well_name
            operator = operator or data.operator
        if not api:
            ui.notify("Load a well or parse a WCR PDF first.", type="warning")
            return

        sundry_no = date_filed = None
        try:
            sub = wcr_service.repo.get_latest_wcr_submission(api)
        except Exception as exc:
            sub = None
            log.warning("tracking.sundry_lookup_failed", api=api, error=str(exc))
        if sub:
            sundry_no = sub.get("sundry_no")
            date_filed = sub.get("submit_date")
            well_name = well_name or sub.get("well_name")

        edits = [
            label
            for label, on in (
                ("utms", trk_utms.value),
                ("footages", trk_footages.value),
                ("perfs", trk_perfs.value),
                ("depths", trk_depths.value),
            )
            if on
        ]
        if (trk_other.value or "").strip():
            edits.append(trk_other.value.strip())

        try:
            path = update_tracking_workbook(
                path=settings.tracking_workbook,
                api=api,
                well_name=well_name,
                operator=operator,
                sundry_no=sundry_no,
                date_filed=date_filed,
                returns=int(float(trk_returns.value or 0)),
                action_taken=bool(trk_action.value) or bool(edits),
                comp_sum=bool(trk_comp.value),
                drill_sum=bool(trk_drill.value),
                cement_log=bool(trk_cmt.value),
                logs_included=bool(trk_logs.value),
                as_drilled_excel=bool(trk_asdrilled.value),
                edits=edits,
            )
        except PermissionError:
            ui.notify(
                "TrackingWCR.xlsx is open in Excel — close it and try again.",
                type="negative",
            )
            return
        except Exception as exc:
            ui.notify(f"Tracking update failed: {exc}", type="negative")
            raise
        filed = f", filed {date_filed:%m/%d/%Y}" if date_filed else " (no sundry date found)"
        tracking_status.text = f"Saved row for API {api}{filed} → {Path(path).name}"
        ui.notify("Personal record updated.", type="positive")

    def refresh() -> None:
        # ---- Sync WCR data from state into local cache (used by the
        # generate / promote handlers above and the survey helpers).
        cache["wcr_data"] = state.wcr_data
        cache["wcr_pdf_path"] = state.wcr_pdf_path
        cache["wcr_pdf_name"] = state.wcr_pdf_name
        if state.wcr_survey_df is not None:
            cache["surveys"] = state.wcr_survey_df
            cache["surveys_label"] = state.wcr_survey_label
            cache["survey_source"] = state.wcr_survey_source

        data = state.wcr_data
        if data is None:
            empty_state.visible = True
            action_bar.visible = False
            wcr_meta_card.visible = False
            ddr_card.visible = False
            results_card.visible = False
        else:
            empty_state.visible = False
            action_bar.visible = True
            source_label.text = (
                f"{state.wcr_pdf_name or 'WCR'} · "
                f"{data.well_name or '(unnamed)'} · API {data.api or '—'}"
            )

            # Survey status pill + fallback upload row.
            if cache.get("surveys") is not None and cache.get("surveys_label"):
                survey_status.text = f"Survey: {cache['surveys_label']}"
                survey_status.classes(
                    replace="text-xs px-2 py-1 rounded bg-green-100 text-green-800"
                )
                survey_upload_row.visible = False
            else:
                survey_status.text = "No survey loaded — upload one below."
                survey_status.classes(
                    replace="text-xs px-2 py-1 rounded bg-amber-100 text-amber-800"
                )
                survey_upload_row.visible = True

            _refresh_generate_button()
            _render_wcr_metadata(wcr_meta_card, data)
            wcr_meta_card.visible = True
            # Always render — the card itself says when the PDF has no
            # Operation Summary appendix at all.
            _render_ddr_card(ddr_card, data)
            ddr_card.visible = True

        # ---- Legacy DB flow ----
        if state.clearances:
            opts = sorted(state.clearances.keys())
            citing_select.options = opts
            if not citing_select.value or citing_select.value not in opts:
                citing_select.value = opts[0]
            citing_select.update()
        if state.primary is None:
            legacy_header_label.text = "Load a well first."
            legacy_header_label.visible = True
            legacy_controls.set_visibility(False)
        else:
            cache["bundle"] = None  # invalidate so we reload for the new well
            rerender_legacy()

    return refresh


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _render_wcr_metadata(card: ui.card, data: WCRPdfData) -> None:
    card.clear()
    with card:
        ui.label("Extracted WCR data").classes("text-sm font-semibold")
        if data.form_type == "form15":
            ui.label(
                "⚠ This PDF is a FORM 15 (Workover/Recompletion Tax Credit "
                "Application), not a Form 8 WCR. The standard WCR fields "
                "will be empty — re-upload a Form 8 to generate a WCR Excel."
            ).classes(
                "text-xs p-2 rounded bg-amber-100 text-amber-900 border border-amber-300"
            )
        elif data.form_type == "unknown":
            ui.label(
                "Form type couldn't be confidently determined. Extraction "
                "may be incomplete."
            ).classes("text-xs p-2 rounded bg-slate-100 text-slate-700")
        for w in data.warnings:
            ui.label(w).classes("text-xs p-2 rounded bg-amber-50 text-amber-800")
        pairs = [
            ("Well", data.well_name),
            ("API", data.api),
            ("Operator", data.operator),
            ("Field", data.field_name),
            ("County", data.county),
            ("Type", data.well_type),
            ("Status", data.well_status),
            ("Spud", data.spud_date),
            ("Rotary rig", data.rotary_date),
            ("TD reached", data.td_date),
            ("Completed", data.completion_date),
            ("Elev / Ground (ft)", _pair_or_dash(data.elevation_ft, data.ground_elev_ft)),
            ("TD MD / TVD (ft)", _pair_or_dash(data.total_md_ft, data.total_tvd_ft)),
            ("PBTD MD / TVD (ft)", _pair_or_dash(data.pbtd_md_ft, data.pbtd_tvd_ft)),
            (
                "Perf stages",
                f"{len(data.perf_stages)} stages, MD {data.first_perf_md:g}–{data.last_perf_md:g}"
                if data.perf_stages
                else "—",
            ),
            ("Formations", f"{len(data.formations)} tops" if data.formations else "—"),
            (
                "Surface UTM (E / N)",
                _pair_or_dash(
                    data.surface_position.utm_easting if data.surface_position else None,
                    data.surface_position.utm_northing if data.surface_position else None,
                ),
            ),
        ]
        with ui.grid(columns=4).classes("gap-x-6 gap-y-1 text-sm"):
            for label, value in pairs:
                ui.label(label).classes("text-gray-500")
                ui.label(str(value) if value not in (None, "") else "—")


def _render_ddr_card(card: ui.card, data: WCRPdfData) -> None:
    """Show the Operation Summary Report (DDR) highlights for each job."""
    card.clear()
    with card:
        ui.label("Operation Summary Reports (DDR)").classes("text-sm font-semibold")
        if not data.ddrs:
            ui.label(
                "No Operation Summary Report found in this PDF — it only "
                "contains the Form 8 (no well-operations appendix)."
            ).classes("text-xs p-2 rounded bg-slate-100 text-slate-700")
            return
        for ddr in data.ddrs:
            # Rules-flagged problems (stuck pipe, equipment failure, …)
            # surfaced first — no LLM involved.
            _render_trouble(ddr)
            # The ops log exactly as the operator wrote it — no LLM
            # involved, available on every parse scope. Rows are filled
            # on first open so a 300-entry drilling log doesn't weigh
            # down the tab render.
            _render_raw_log(ddr)
            # LLM-generated summary surfaced above the events expansion so
            # the user sees the narrative without having to expand.
            if ddr.summary:
                with ui.row().classes("items-baseline gap-2 mt-2"):
                    ui.label(f"{ddr.job_category or 'DDR'} summary").classes(
                        "text-xs font-semibold text-gray-600"
                    )
                    ui.label("(LLM-generated)").classes("text-xs text-gray-400")
                ui.label(ddr.summary).classes(
                    "text-sm text-gray-800 p-2 rounded bg-blue-50 "
                    "border border-blue-200 max-w-4xl break-words"
                )

            # Per-entry plain-English translations next to the original log
            # text — only present when the user checked 'Parse Operations'
            # at load time.
            translated = [e for e in ddr.entries if e.plain_english]
            if translated or ddr.narrative:
                with ui.expansion(
                    f"{ddr.job_category or 'DDR'} — operations, plain English "
                    "(LLM-generated)",
                    icon="menu_book",
                    value=False,
                ).classes("w-full"):
                    if translated:
                        _render_ops_translations(ddr)
                    else:
                        ui.markdown(ddr.narrative).classes(
                            "text-sm text-gray-800 p-2 rounded bg-emerald-50 "
                            "border border-emerald-200 max-w-4xl break-words"
                        )

            with ui.expansion(
                f"{ddr.job_category or 'DDR'} — "
                f"{len(ddr.entries)} entries, {len(ddr.key_events)} key events"
                f" ({ddr.start_date.date() if ddr.start_date else '?'} → "
                f"{ddr.end_date.date() if ddr.end_date else '?'})",
                value=False,
            ).classes("w-full"):
                if ddr.key_events:
                    ui.label("Key events").classes(
                        "text-xs font-semibold mt-2 text-gray-600"
                    )
                    columns = [
                        {"name": "type", "label": "Type", "field": "type", "align": "left"},
                        {"name": "md", "label": "MD", "field": "md"},
                        {"name": "tvd", "label": "TVD", "field": "tvd"},
                        {"name": "ts", "label": "When", "field": "ts", "align": "left"},
                        {"name": "desc", "label": "Description", "field": "desc", "align": "left"},
                        {"name": "conf", "label": "Conf", "field": "conf"},
                    ]
                    rows = [
                        {
                            "type": e.event_type,
                            "md": _fmt_num(e.md_ft, 0) if e.md_ft is not None else "—",
                            "tvd": _fmt_num(e.tvd_ft, 0) if e.tvd_ft is not None else "—",
                            "ts": (
                                e.timestamp.strftime("%Y-%m-%d %H:%M")
                                if e.timestamp
                                else "—"
                            ),
                            "desc": e.description,
                            "conf": f"{e.confidence:.0%}",
                        }
                        for e in ddr.key_events
                    ]
                    ui.table(
                        columns=columns, rows=rows, row_key="desc"
                    ).classes("w-full text-xs").props("dense flat bordered")


def _render_trouble(ddr) -> None:
    """Problems the rules layer flagged in the ops log, with excerpts."""
    from etools.core.pdf.ddr_events import trouble_excerpt

    flagged = [e for e in ddr.entries if e.trouble]
    if not flagged:
        return
    title = (
        f"⚠ {ddr.job_category or 'DDR'} — {len(flagged)} "
        f"entr{'y' if len(flagged) == 1 else 'ies'} with problems flagged"
    )
    with ui.expansion(title, icon="warning", value=True).classes(
        "w-full bg-red-50"
    ):
        with ui.column().classes("gap-2 max-w-4xl"):
            for e in flagged:
                when = e.start_time.strftime("%m-%d") if e.start_time else "?"
                with ui.row().classes("items-center gap-1 flex-wrap"):
                    ui.label(when).classes("text-xs font-semibold text-gray-700")
                    if e.phase:
                        ui.label(e.phase).classes("text-xs text-gray-500")
                    for flag in e.trouble:
                        ui.label(flag).classes(
                            "text-xs px-2 py-0.5 rounded-full bg-red-100 "
                            "text-red-800 border border-red-300"
                        )
                ui.label(trouble_excerpt(e)).classes(
                    "text-xs text-gray-700 break-words"
                )


def _render_raw_log(ddr) -> None:
    """The operations log verbatim — one block per entry, lazily filled."""
    n = len(ddr.entries)
    title = (
        f"{ddr.job_category or 'DDR'} — operations log, as written"
        + (f" ({n} entries)" if n else "")
    )
    with ui.expansion(title, icon="article", value=False).classes("w-full") as exp:
        holder = ui.column().classes("max-w-4xl gap-1")
        if not n:
            with holder:
                ui.label(
                    "Job header found, but no log entries could be parsed "
                    "from this appendix."
                ).classes("text-xs text-amber-800 p-2 rounded bg-amber-50")
            return

    filled = {"done": False}

    def _fill(e, holder=holder, ddr=ddr, filled=filled) -> None:
        if filled["done"] or not getattr(e, "value", False):
            return
        filled["done"] = True
        with holder:
            for entry in ddr.entries:
                when = (
                    entry.start_time.strftime("%m-%d %H:%M")
                    if entry.start_time
                    else "?"
                )
                bits = [when]
                if entry.duration_hr is not None:
                    bits.append(f"{entry.duration_hr:g} h")
                op = entry.phase or entry.code2 or entry.code1
                if op:
                    bits.append(op)
                if entry.start_depth_ftkb is not None and entry.end_depth_ftkb is not None:
                    bits.append(
                        f"{entry.start_depth_ftkb:.0f} → {entry.end_depth_ftkb:.0f} ft"
                    )
                if entry.ops_category:
                    bits.append(entry.ops_category)
                with ui.row().classes("items-center gap-1 mt-1 flex-wrap"):
                    ui.label(" · ".join(bits)).classes(
                        "text-xs font-semibold text-gray-600"
                    )
                    for flag in entry.trouble:
                        ui.label(flag).classes(
                            "text-xs px-2 py-0.5 rounded-full bg-red-100 "
                            "text-red-800 border border-red-300"
                        )
                box = (
                    "bg-red-50 border-red-300"
                    if entry.trouble
                    else "bg-slate-50 border-slate-200"
                )
                ui.label(entry.comment or "—").classes(
                    "text-xs text-gray-700 whitespace-pre-wrap break-words "
                    f"p-1 rounded border {box} w-full"
                )

    exp.on_value_change(_fill)


def _render_ops_translations(ddr) -> None:
    """Side-by-side: original time-log text | caveman plain English."""
    with ui.grid(columns="1fr 1fr").classes("gap-x-4 gap-y-2 max-w-5xl mt-1"):
        ui.label("Original log").classes("text-xs font-semibold text-gray-500")
        ui.label("Plain English").classes("text-xs font-semibold text-gray-500")
        for e in ddr.entries:
            if not (e.comment or e.plain_english):
                continue
            when = e.start_time.strftime("%m-%d %H:%M") if e.start_time else "?"
            head = " · ".join(x for x in (when, e.phase or e.code2 or e.code1) if x)
            orig_box = (
                "bg-red-50 border-red-300" if e.trouble else "bg-slate-50 border-slate-200"
            )
            with ui.column().classes("gap-0 min-w-0"):
                with ui.row().classes("items-center gap-1 flex-wrap"):
                    ui.label(head).classes("text-xs font-semibold text-gray-600")
                    for flag in e.trouble:
                        ui.label(flag).classes(
                            "text-xs px-2 py-0.5 rounded-full bg-red-100 "
                            "text-red-800 border border-red-300"
                        )
                ui.label(e.comment or "—").classes(
                    "text-xs text-gray-600 whitespace-pre-wrap break-words "
                    f"p-1 rounded border {orig_box}"
                )
            ui.label(e.plain_english or "(not translated)").classes(
                "text-sm text-gray-900 whitespace-pre-wrap break-words p-1 "
                "rounded bg-emerald-50 border border-emerald-200 self-start min-w-0"
            )


def _render_results(
    card: ui.card,
    result: WCRPdfResult,
    download_url: str,
    path_str: str,
    *,
    edit_inputs_cache: dict,
    on_edit,
    on_save,
) -> None:
    """Render the 5 location rows with editable MD/Easting/Northing inputs.

    ``edit_inputs_cache`` is a dict the caller owns; this function writes
    back ``{name: {"md": ui.input, "easting": ui.input, "northing": ui.input}}``
    so the Recalc/Save handlers can read the live values.
    """
    card.clear()
    edit_inputs_cache.clear()

    with card:
        # Header row — title + download controls.
        with ui.row().classes("items-center gap-3 w-full"):
            ui.label("Generated WCR — Section 27 footages").classes(
                "text-sm font-semibold flex-1"
            )
            ui.button(
                "Open folder",
                icon="folder_open",
                on_click=lambda: ui.run_javascript(
                    f"window.open('{download_url}', '_blank')"
                ),
            ).props("flat dense")
            ui.button(
                "Download",
                icon="download",
                on_click=lambda: ui.download(path_str),
            ).props("flat dense color=primary")
        ui.label(path_str).classes("text-xs text-gray-500 break-all")
        ui.label(
            "Edit MD, Easting, or Northing to override the derived values. "
            "Changes cascade through TVD / footages / PLSS labels automatically "
            "when you leave the field; click Save to rewrite the Excel."
        ).classes("text-xs text-gray-600 mt-1")

        # 15-column grid: label + 3 editable + 9 read-only + section block.
        headers = [
            "Location", "MD", "TVD", "Easting", "Northing",
            "FNL", "FSL", "FEL", "FWL",
            "Sec", "Twp", "T-Dir", "Rng", "R-Dir", "Mer",
        ]
        with ui.grid(columns=15).classes("gap-x-2 gap-y-1 text-xs mt-2 w-full items-center"):
            for h in headers:
                ui.label(h).classes("font-semibold text-gray-600")

            for r in result.location_rows:
                # Column 1: location name.
                ui.label(r.name).classes("font-medium")
                # Column 2: editable MD. on('blur') fires the cascade so
                # tabbing or clicking away triggers a recalc without the
                # user needing to press a button.
                md_input = (
                    ui.input(value=_fmt_input(r.measured_depth, 0))
                    .props("dense outlined")
                    .classes("w-24")
                    .on("blur", lambda _: on_edit())
                    .on("keydown.enter", lambda _: on_edit())
                )
                # Column 3: read-only TVD.
                tvd_label = ui.label(_fmt_num(r.tvd, 2)).classes("text-gray-700")
                # Columns 4-5: editable Easting, Northing.
                e_input = (
                    ui.input(value=_fmt_input(r.easting, 0))
                    .props("dense outlined")
                    .classes("w-24")
                    .on("blur", lambda _: on_edit())
                    .on("keydown.enter", lambda _: on_edit())
                )
                n_input = (
                    ui.input(value=_fmt_input(r.northing, 0))
                    .props("dense outlined")
                    .classes("w-24")
                    .on("blur", lambda _: on_edit())
                    .on("keydown.enter", lambda _: on_edit())
                )
                # Columns 6-9: read-only footages.
                fnl_label = ui.label(_fmt_num(r.fnl, 2)).classes("text-gray-700")
                fsl_label = ui.label(_fmt_num(r.fsl, 2)).classes("text-gray-700")
                fel_label = ui.label(_fmt_num(r.fel, 2)).classes("text-gray-700")
                fwl_label = ui.label(_fmt_num(r.fwl, 2)).classes("text-gray-700")
                # Columns 10-15: read-only PLSS labels.
                sec_label = ui.label(r.section or "—")
                twp_label = ui.label(r.township or "—")
                twpdir_label = ui.label(r.township_dir or "—")
                rng_label = ui.label(r.range or "—")
                rngdir_label = ui.label(r.range_dir or "—")
                base_label = ui.label(r.baseline or "—")

                edit_inputs_cache[r.name] = {
                    "md": md_input,
                    "easting": e_input,
                    "northing": n_input,
                    # Read-only labels — the cascade handler updates these
                    # in place so the focused input field isn't destroyed.
                    "tvd_label": tvd_label,
                    "fnl_label": fnl_label,
                    "fsl_label": fsl_label,
                    "fel_label": fel_label,
                    "fwl_label": fwl_label,
                    "sec_label": sec_label,
                    "twp_label": twp_label,
                    "twpdir_label": twpdir_label,
                    "rng_label": rng_label,
                    "rngdir_label": rngdir_label,
                    "base_label": base_label,
                    # Originals (raw floats) so the recalc handler can tell
                    # whether the user actually changed a cell vs. left the
                    # auto-populated value alone.
                    "orig_md": r.measured_depth,
                    "orig_easting": r.easting,
                    "orig_northing": r.northing,
                }

        with ui.row().classes("gap-2 mt-3"):
            ui.button("Save updated Excel", icon="save", on_click=on_save).props(
                "color=positive"
            )
            ui.label(
                "Footages and PLSS labels recompute automatically when you edit a cell; "
                "click Save to write the file."
            ).classes("text-xs text-gray-500 ml-3 self-center")


def _fmt_input(value, ndigits: int) -> str:
    """Format a numeric value for placement inside an editable text input.
    Plain digits (no comma separators) so the round-trip via ``float()`` is
    trivial when the user edits the value."""
    if value is None:
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    if ndigits == 0:
        return f"{int(round(v))}"
    return f"{v:.{ndigits}f}"


def _parse_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_num(value, ndigits: int) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if ndigits == 0:
        return f"{int(round(v)):,}"
    return f"{v:,.{ndigits}f}"


def _pair_or_dash(a, b) -> str:
    if a is None and b is None:
        return "—"
    return f"{a if a is not None else '—'} / {b if b is not None else '—'}"


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
        raise RuntimeError(f"Don't know how to read upload object: {type(upload).__name__}")
    return tmp_path


def _serve_output_file(path: Path) -> str:
    out_dir = Path(settings.output_dir).resolve()
    mount_path = "/output"
    if not getattr(_serve_output_file, "_mounted", False):
        try:
            from starlette.staticfiles import StaticFiles

            app.mount(mount_path, StaticFiles(directory=str(out_dir)), name="etools_output")
        except Exception:
            pass
        _serve_output_file._mounted = True  # type: ignore[attr-defined]
    return f"{mount_path}/{Path(path).name}"


def _fmt_date(d) -> str:
    return d.strftime("%Y-%m-%d") if d is not None else "—"


def _refresh_llm_status(label: ui.label) -> None:
    """Show whether Ollama + the configured model are available so the user
    knows whether the LLM fallback layer can engage."""
    try:
        from etools.core.llm import OllamaClient

        cli = OllamaClient()
        if not settings.llm.enabled:
            label.text = "LLM: disabled in config (rules-only WCR parse)"
        elif cli.health() and cli.has_model():
            label.text = f"LLM: ready ({settings.llm.model}) — will backfill missing WCR fields"
        elif cli.health():
            label.text = f"LLM: Ollama up but model '{settings.llm.model}' not pulled"
        else:
            label.text = "LLM: Ollama not running — WCR parse will use rules only"
    except Exception as exc:
        label.text = f"LLM: status check failed ({exc})"
