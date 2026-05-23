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

import pandas as pd
from nicegui import app, events, ui

from etools.config import settings
from etools.core.pdf.parser import parse_survey_pdf
from etools.core.pdf.wcr_parser import parse_wcr_pdf
from etools.logging_setup import get_logger
from etools.models import WCRPdfData
from etools.repositories import SurveyRepository
from etools.services import WCRService
from etools.services.wcr_pdf_service import WCRPdfResult, WCRPdfService
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
        ui.label("Generate WCR Excel").classes("text-xl font-semibold")

        # ------------------------------------------------------------------
        # Step 1 — upload WCR PDF
        # ------------------------------------------------------------------
        ui.label("Step 1 — WCR PDF").classes("text-sm font-semibold mt-2")
        with ui.row().classes("gap-3 items-center w-full"):
            wcr_upload = ui.upload(
                label="Drop WCR PDF here",
                auto_upload=True,
                multiple=False,
                on_upload=lambda e: handle_wcr_upload(e),
                on_rejected=lambda e: ui.notify(f"Upload rejected: {e}", type="negative"),
            ).classes("max-w-md").props("accept=.pdf")
            wcr_status = ui.label("No WCR PDF uploaded.").classes("text-xs text-gray-600")

        # Parsing controls — mode + page range + the trigger buttons.
        with ui.row().classes("gap-3 items-center w-full mt-1"):
            ui.label("Mode:").classes("text-sm")
            mode_select = (
                ui.select(
                    options={
                        "rules": "Rules (Docling + regex)",
                        "rules+llm": "Rules + LLM (regex first, LLM fills gaps)",
                        "llm": "LLM only (skip regex)",
                    },
                    value="rules+llm",
                )
                .props("dense outlined")
                .classes("w-72")
            )
            ui.label("Pages:").classes("text-sm ml-2")
            pages_select = (
                ui.select(
                    options={
                        "5": "First 5 pages (Form 8 only)",
                        "10": "First 10 pages",
                        "all": "All pages (includes Operation Summary)",
                    },
                    value="5",
                )
                .props("dense outlined")
                .classes("w-64")
            )
            parse_wcr_btn = ui.button(
                "Parse WCR PDF",
                icon="play_arrow",
                on_click=lambda: parse_wcr_now(),
            ).props("color=primary")
            parse_wcr_btn.disable()

        with ui.row().classes("gap-3 items-center w-full mt-1"):
            mine_events_checkbox = ui.checkbox(
                "Mine extra events from time-log comments (slow)",
                value=False,
            )
            mine_events_checkbox.tooltip(
                "When enabled, the LLM does a second pass over uncategorized "
                "time-log entries to find additional events the regex missed "
                "(formation picks, screen-outs, BHA failures, etc.). Adds "
                "~5 min per DDR to the parse time."
            )

        # LLM availability indicator — mirrors the regular PDF Import tab.
        llm_status_label = ui.label("").classes("text-xs text-gray-500")
        _refresh_llm_status(llm_status_label)

        # Card with extracted WCR metadata
        wcr_meta_card = ui.card().classes("w-full")
        wcr_meta_card.visible = False

        # Card with DDR (drilling/completion daily log) highlights.
        ddr_card = ui.card().classes("w-full")
        ddr_card.visible = False

        # ------------------------------------------------------------------
        # Step 2 — survey source (DB lookup, fallback to PDF upload)
        # ------------------------------------------------------------------
        ui.label("Step 2 — Survey source").classes("text-sm font-semibold mt-2")
        survey_status = ui.label("Upload a WCR PDF first.").classes(
            "text-sm px-3 py-2 rounded bg-slate-100 text-slate-700"
        )

        survey_upload_row = ui.row().classes("gap-3 items-center w-full")
        with survey_upload_row:
            survey_upload = ui.upload(
                label="Drop directional survey PDF here",
                auto_upload=True,
                multiple=False,
                on_upload=lambda e: handle_survey_upload(e),
                on_rejected=lambda e: ui.notify(f"Upload rejected: {e}", type="negative"),
            ).classes("max-w-md").props("accept=.pdf")
            survey_parse_status = ui.label("").classes("text-xs text-gray-600")
        survey_upload_row.visible = False

        # ------------------------------------------------------------------
        # Step 3 — generate
        # ------------------------------------------------------------------
        ui.label("Step 3 — Generate").classes("text-sm font-semibold mt-2")
        with ui.row().classes("gap-3 items-center"):
            generate_btn = ui.button(
                "Generate WCR Excel",
                icon="description",
                on_click=lambda: generate_from_pdf(),
            ).props("color=primary")
            generate_btn.disable()
            generate_status = ui.label("").classes("text-sm text-gray-500 ml-2")

        # Card showing the generated WCR's five location rows.
        results_card = ui.card().classes("w-full mt-2")
        results_card.visible = False

        ui.separator()

        # ------------------------------------------------------------------
        # Legacy DB-driven flow (kept available)
        # ------------------------------------------------------------------
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
                legacy_generate_btn = ui.button(
                    "Generate from DB", icon="description", on_click=lambda: generate_legacy()
                ).props("color=primary")
                legacy_status = ui.label("").classes("text-sm text-gray-500 ml-2")
            legacy_controls.set_visibility(False)

            legacy_info_card = ui.card().classes("w-full")

    # ----------------------------------------------------------------------
    # Step 1 — WCR PDF upload + immediate parse
    # ----------------------------------------------------------------------
    async def handle_wcr_upload(e: events.UploadEventArguments) -> None:
        """Stage the upload only. Parsing waits for the user to click the
        ``Parse WCR PDF`` button so they stay in control of when the
        pipeline kicks off."""
        upload = getattr(e, "file", None) or getattr(e, "content", None)
        name = getattr(upload, "name", None) or getattr(e, "name", "uploaded.pdf")
        wcr_status.text = f"Saving {name}…"
        try:
            tmp_path = await _save_upload(upload, name)
        except Exception as exc:
            ui.notify(f"Upload failed: {exc}", type="negative")
            wcr_status.text = "Upload failed."
            return
        cache["wcr_pdf_path"] = tmp_path
        cache["wcr_pdf_name"] = name
        try:
            wcr_upload.reset()
        except Exception:
            pass

        # Reset any prior parse output — we're staging a new file.
        cache["wcr_data"] = None
        cache["surveys"] = None
        cache["surveys_label"] = None
        cache["survey_source"] = None
        cache["survey_pdf_lat"] = None
        cache["survey_pdf_lon"] = None
        cache["survey_pdf_elev"] = None
        cache["survey_pdf_north_ref"] = None
        wcr_meta_card.visible = False
        survey_upload_row.visible = False
        results_card.visible = False
        survey_status.text = "Click 'Parse WCR PDF' to extract metadata."
        survey_status.classes(
            replace="text-sm px-3 py-2 rounded bg-slate-100 text-slate-700"
        )
        _refresh_generate_button()

        wcr_status.text = f"Loaded {name}. Click 'Parse WCR PDF' to extract."
        parse_wcr_btn.enable()

    async def parse_wcr_now() -> None:
        tmp_path = cache.get("wcr_pdf_path")
        name = cache.get("wcr_pdf_name") or "uploaded.pdf"
        if not tmp_path:
            ui.notify("Upload a WCR PDF first.", type="warning")
            return
        mode = mode_select.value or "rules+llm"
        pages_val = pages_select.value or "5"
        max_pages = None if pages_val == "all" else int(pages_val)
        mine_events = bool(mine_events_checkbox.value)

        parse_wcr_btn.disable()
        events_note = " + DDR event mining" if mine_events else ""
        wcr_status.text = (
            f"Parsing {name} — mode={mode}, "
            f"pages={'all' if max_pages is None else max_pages}{events_note}…"
        )
        try:
            data = await asyncio.to_thread(
                parse_wcr_pdf,
                tmp_path,
                use_llm=None,
                mode=mode,
                max_pages=max_pages,
                mine_ddr_events=mine_events,
            )
        except Exception as exc:
            log.exception("wcr.parse_failed")
            ui.notify(f"WCR parse failed: {exc}", type="negative")
            wcr_status.text = "Parse failed."
            parse_wcr_btn.enable()
            return

        cache["wcr_data"] = data
        wcr_status.text = f"Parsed {name}: {data.well_name or '(unnamed)'}  API {data.api or '—'}"
        _render_wcr_metadata(wcr_meta_card, data)
        wcr_meta_card.visible = True
        if data.ddrs:
            _render_ddr_card(ddr_card, data)
            ddr_card.visible = True
        else:
            ddr_card.visible = False

        await _try_db_survey_lookup()
        _refresh_generate_button()
        parse_wcr_btn.enable()

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
        ready = bool(cache.get("wcr_data")) and cache.get("surveys") is not None
        if ready:
            generate_btn.enable()
        else:
            generate_btn.disable()

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
                md_changed = md_val is not None and not _close(md_val, w.get("orig_md"), 0.5)
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
            )
        except Exception as exc:  # pragma: no cover
            ui.notify(f"WCR generation failed: {exc}", type="negative")
            raise
        rel = Path(path).name
        legacy_status.text = f"Saved {rel}"
        ui.notify(f"WCR generated: {rel}", type="positive")

    def refresh() -> None:
        # Legacy section options.
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
        for ddr in data.ddrs:
            # LLM-generated summary surfaced above the events expansion so
            # the user sees the narrative without having to expand.
            if ddr.summary:
                with ui.row().classes("items-baseline gap-2 mt-2"):
                    ui.label(f"{ddr.job_category or 'DDR'} summary").classes(
                        "text-xs font-semibold text-gray-600"
                    )
                    ui.label("(LLM-generated)").classes("text-xs text-gray-400")
                ui.label(ddr.summary).classes(
                    "text-sm text-gray-800 p-2 rounded bg-blue-50 border border-blue-200"
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
