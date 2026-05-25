"""Casing Review tab — APD PDF → engineered Casing Review Excel.

Architecture rule: **all persistent data lives on ``state`` (AppState).**
The tab's local ``cache`` dict only holds live UI element references for
the CURRENT render. When the WebSocket drops (e.g. during heavy refresh
work) and the page reconnects, ``render_casing_review_tab`` runs fresh
and rebuilds its UI from ``state.apd_data`` / ``state.casing_survey_df``
/ ``state.casing_overrides``. This is the same pattern Survey / Map &
Viz / Clearance tabs use — they pull from state on every refresh, so
reconnects look seamless.

User flow:

    Step 1  Upload APD PDF
    Step 2  Parse it (rules / rules+LLM / LLM)  → state.apd_data
    Step 3  Survey source: DB lookup OR upload PDF  → state.casing_survey_df
    Step 4  Frac gradient input
    Step 5  Promote to active well  → fires post_load orchestration
    Step 6  Edit casing inputs inline — recomputes design + WBD in place
    Step 7  Generate Casing Review Excel
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Callable

from nicegui import app, events, ui

from etools.config import settings
from etools.core.casing_review.domain import CasingDesign
from etools.core.casing_review.engine import (
    CasingDesignEngine,
    welltrack_from_dataframe,
)
from etools.core.casing_review.promote import (
    normalize_survey_dataframe,
    well_header_from_apd,
)
from etools.core.pdf.apd_parser import parse_apd_pdf
from etools.core.pdf.parser import parse_survey_pdf
from etools.logging_setup import get_logger
from etools.models import APDPdfData
from etools.repositories import SurveyRepository
from etools.services import CasingReviewService
from etools.ui.state import AppState

log = get_logger(__name__)


def render_casing_review_tab(state: AppState) -> Callable[[], None]:
    svc = CasingReviewService()
    engine = CasingDesignEngine()
    survey_repo = SurveyRepository()

    # ``cache`` ONLY holds element refs for the current render. Persistent
    # data goes on ``state``. Anything stored here is gone after reconnect.
    cache: dict = {
        "meta_card": None,
        "inputs_card": None,
        "design_card": None,
        "design_table": None,
        "wbd_card": None,
        "result_card": None,
        "apd_status": None,
        "survey_status": None,
        "survey_upload_row": None,
        "gen_status": None,
        "frac_input": None,
        "parse_btn": None,
        "promote_btn": None,
        "gen_btn": None,
        "mode_select": None,
    }

    # ----------------------------------------------------------------------
    # Top-level layout — built once per render
    # ----------------------------------------------------------------------
    with ui.column().classes("p-4 gap-3 w-full"):
        ui.label("Generate Casing Review Excel").classes("text-xl font-semibold")

        # Step 1
        ui.label("Step 1 — APD PDF").classes("text-sm font-semibold mt-2")
        with ui.row().classes("gap-3 items-center w-full"):
            apd_upload = ui.upload(
                label="Drop APD application PDF here",
                auto_upload=True,
                multiple=False,
                on_upload=lambda e: handle_apd_upload(e),
                on_rejected=lambda e: ui.notify(f"Upload rejected: {e}", type="negative"),
            ).classes("max-w-md").props("accept=.pdf")
            cache["apd_status"] = ui.label("No APD uploaded.").classes(
                "text-xs text-gray-600"
            )

        with ui.row().classes("gap-3 items-center w-full mt-1"):
            ui.label("Mode:").classes("text-sm")
            cache["mode_select"] = (
                ui.select(
                    options={
                        "rules": "Rules only",
                        "rules+llm": "Rules + LLM backfill",
                        "llm": "LLM only",
                    },
                    value="rules+llm",
                )
                .props("dense outlined")
                .classes("w-72")
            )
            cache["parse_btn"] = ui.button(
                "Parse APD PDF",
                icon="play_arrow",
                on_click=lambda: parse_now(),
            ).props("color=primary")
            cache["parse_btn"].disable()

        cache["meta_card"] = ui.card().classes("w-full")
        cache["meta_card"].visible = False

        # Step 2 — survey source
        ui.label("Step 2 — Survey source").classes("text-sm font-semibold mt-2")
        cache["survey_status"] = ui.label("Upload an APD first.").classes(
            "text-sm px-3 py-2 rounded bg-slate-100 text-slate-700"
        )
        cache["survey_upload_row"] = ui.row().classes("gap-3 items-center w-full")
        with cache["survey_upload_row"]:
            survey_upload = ui.upload(
                label="Drop directional survey PDF here",
                auto_upload=True,
                multiple=False,
                on_upload=lambda e: handle_survey_upload(e),
                on_rejected=lambda e: ui.notify(f"Upload rejected: {e}", type="negative"),
            ).classes("max-w-md").props("accept=.pdf")
        cache["survey_upload_row"].visible = False

        # Step 3
        ui.label("Step 3 — Frac gradient @ production shoe").classes(
            "text-sm font-semibold mt-2"
        )
        with ui.row().classes("gap-3 items-center"):
            ui.label("psi/ft:").classes("text-sm")
            cache["frac_input"] = (
                ui.input(value="1.00")
                .props("dense outlined")
                .classes("w-28")
                .on("blur", lambda _: _on_frac_change())
                .on("keydown.enter", lambda _: _on_frac_change())
            )
            ui.label(
                "Auto-detected from page 2; conservative default 1.0 if not found."
            ).classes("text-xs text-gray-500")

        cache["inputs_card"] = ui.card().classes("w-full")
        cache["inputs_card"].visible = False
        cache["design_card"] = ui.card().classes("w-full")
        cache["design_card"].visible = False
        cache["wbd_card"] = ui.card().classes("w-full")
        cache["wbd_card"].visible = False

        # Step 4 — promote + generate
        ui.label("Step 4 — Promote / generate").classes("text-sm font-semibold mt-2")
        with ui.row().classes("gap-3 items-center"):
            cache["promote_btn"] = ui.button(
                "Use as active well",
                icon="upgrade",
                on_click=lambda: promote_to_primary(),
            ).props("color=secondary")
            cache["promote_btn"].disable()
            cache["promote_btn"].tooltip(
                "Pushes the APD + survey into shared state so Survey, "
                "Map & Viz, and Clearance tabs populate with this well."
            )
            cache["gen_btn"] = ui.button(
                "Generate Casing Review Excel",
                icon="description",
                on_click=lambda: generate(),
            ).props("color=primary")
            cache["gen_btn"].disable()
            cache["gen_status"] = ui.label("").classes("text-sm text-gray-500 ml-2")

        cache["result_card"] = ui.card().classes("w-full mt-2")
        cache["result_card"].visible = False

    # ----------------------------------------------------------------------
    # If state already carries APD data (e.g. user navigated away and back,
    # or a WebSocket reconnect re-ran the page render), immediately rebuild
    # the dynamic cards. This means the tab is populated without needing
    # fire_refresh to fire — important because fire_refresh's heavy work
    # in other tabs can be deferred / delayed.
    # ----------------------------------------------------------------------
    if state.apd_data is not None:
        # Use a microtask so we return from render_casing_review_tab first
        # (NiceGUI needs the static UI to be fully mounted before we add
        # the dynamic cards' content).
        ui.timer(0.05, lambda: _rebuild_from_state(defer_heavy=False), once=True)

    # ----------------------------------------------------------------------
    # Event handlers — they write to ``state`` (not cache) so reconnects
    # preserve everything.
    # ----------------------------------------------------------------------
    async def handle_apd_upload(e: events.UploadEventArguments) -> None:
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
        state.casing_survey_df = None
        state.casing_survey_label = None
        state.casing_overrides = {}
        state.casing_last_output_path = None
        try:
            apd_upload.reset()
        except Exception:
            pass
        _hide_dynamic_cards()
        cache["promote_btn"].disable()
        cache["gen_btn"].disable()
        cache["apd_status"].text = f"Loaded {name}. Click 'Parse APD PDF' to extract."
        cache["parse_btn"].enable()

    async def parse_now() -> None:
        tmp_path = state.apd_pdf_path
        if not tmp_path:
            ui.notify("Upload an APD PDF first.", type="warning")
            return
        mode = cache["mode_select"].value or "rules+llm"
        cache["parse_btn"].disable()
        cache["apd_status"].text = f"Parsing {state.apd_pdf_name} (mode={mode})…"
        try:
            data = await asyncio.to_thread(parse_apd_pdf, tmp_path, mode=mode)
        except Exception as exc:
            log.exception("casing_review.parse_failed")
            ui.notify(f"Parse failed: {exc}", type="negative")
            cache["apd_status"].text = "Parse failed."
            cache["parse_btn"].enable()
            return
        state.apd_data = data
        # Seed frac gradient from PDF if we don't have an explicit user override.
        if state.casing_frac_gradient_psi_per_ft is None and data.frac_gradient_psi_per_ft is not None:
            state.casing_frac_gradient_psi_per_ft = data.frac_gradient_psi_per_ft
        await _try_db_survey()
        _rebuild_from_state()
        cache["parse_btn"].enable()

    async def _try_db_survey() -> None:
        data = state.apd_data
        if data is None or not data.api:
            return
        api10 = data.api[:10]
        try:
            results = await asyncio.to_thread(
                survey_repo.get_points_by_api_lateral, api10, "0000"
            )
        except Exception as exc:
            log.warning("casing_review.db_lookup_failed", error=str(exc))
            return
        chosen = next(
            (c for c in ("AsDrilled", "Planned") if c in results and not results[c].empty),
            None,
        )
        if chosen is None:
            return
        state.casing_survey_df = results[chosen]
        state.casing_survey_label = f"DB / {chosen} ({len(results[chosen])} stations)"

    async def handle_survey_upload(e: events.UploadEventArguments) -> None:
        upload = getattr(e, "file", None) or getattr(e, "content", None)
        name = getattr(upload, "name", None) or getattr(e, "name", "uploaded.pdf")
        cache["survey_status"].text = f"Parsing {name}…"
        try:
            tmp_path = await _save_upload(upload, name)
        except Exception as exc:
            ui.notify(f"Upload failed: {exc}", type="negative")
            return
        try:
            survey_upload.reset()
        except Exception:
            pass
        try:
            parsed = await asyncio.to_thread(parse_survey_pdf, tmp_path)
        except Exception as exc:
            ui.notify(f"Survey parse failed: {exc}", type="negative")
            return
        if parsed.surveys is None or parsed.surveys.empty:
            cache["survey_status"].text = "No MD/INC/AZI rows found."
            return
        state.casing_survey_df = parsed.surveys
        state.casing_survey_label = f"PDF / {name} ({len(parsed.surveys)} stations)"
        _rebuild_from_state()

    def _on_frac_change() -> None:
        try:
            state.casing_frac_gradient_psi_per_ft = float(
                (cache["frac_input"].value or "1.0").strip()
            )
        except (ValueError, TypeError):
            state.casing_frac_gradient_psi_per_ft = 1.0
        _rebuild_design_and_wbd()

    async def promote_to_primary() -> None:
        data = state.apd_data
        if data is None:
            ui.notify("Parse an APD PDF first.", type="warning")
            return
        try:
            header = well_header_from_apd(data)
        except Exception as exc:
            log.exception("casing_review.promote.header_failed")
            ui.notify(f"Could not build well header: {exc}", type="negative")
            return
        if header.surface_lat is None:
            ui.notify(
                "APD has no PLSS section we can geolocate. Upload a survey PDF "
                "or load the well from the DB.",
                type="warning",
                multi_line=True,
                timeout=8000,
            )
            return
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
        if state.post_load is None:
            ui.notify("Post-load orchestrator not registered.", type="warning")
            return
        try:
            await state.post_load(switch_to_survey=False)
        except Exception as exc:
            log.exception("casing_review.promote.post_load_failed")
            ui.notify(f"Promote post-load failed: {exc}", type="negative")
            return
        ui.notify(
            f"Promoted {header.well_name or header.api} — other tabs populated.",
            type="positive",
            multi_line=True,
        )

    def generate() -> None:
        data = state.apd_data
        if data is None:
            ui.notify("Parse an APD PDF first.", type="warning")
            return
        try:
            frac = float((cache["frac_input"].value or "1.0").strip())
        except ValueError:
            ui.notify("Frac gradient must be a number.", type="warning")
            return
        try:
            result = svc.generate(
                apd_data=data,
                survey=state.casing_survey_df,
                frac_gradient_override_psi_per_ft=frac,
            )
        except Exception as exc:
            log.exception("casing_review.generate_failed")
            ui.notify(f"Generation failed: {exc}", type="negative")
            return
        state.casing_last_output_path = result.output_path
        out = result.output_path
        cache["gen_status"].text = f"Saved {out.name}"
        _render_result(cache["result_card"], out, _serve_output_file(out))
        cache["result_card"].visible = True
        ui.notify(f"Casing Review generated: {out.name}", type="positive")

    # ----------------------------------------------------------------------
    # Render helpers — all read from ``state`` so reconnects come up clean.
    # ----------------------------------------------------------------------
    def _hide_dynamic_cards() -> None:
        for k in ("meta_card", "inputs_card", "design_card", "wbd_card", "result_card"):
            card = cache.get(k)
            if card is not None:
                card.visible = False

    def _rebuild_from_state(*, defer_heavy: bool = False) -> None:
        """Restore the tab UI from ``state``. Idempotent.

        ``defer_heavy`` schedules the expensive design + WBD rebuild via
        a timer so it doesn't run inline with page-render / refresh
        callbacks. Use True from refresh() (called by fire_refresh),
        False from direct user actions (parse, edit) where the user is
        waiting on a result.
        """
        data = state.apd_data
        if data is None:
            _hide_dynamic_cards()
            cache["apd_status"].text = "No APD uploaded."
            cache["survey_status"].text = "Upload an APD first."
            cache["survey_status"].classes(
                replace="text-sm px-3 py-2 rounded bg-slate-100 text-slate-700"
            )
            cache["gen_status"].text = ""
            cache["promote_btn"].disable()
            cache["gen_btn"].disable()
            return

        cache["apd_status"].text = (
            f"Parsed {state.apd_pdf_name or 'APD'}: {data.well_name or '(unnamed)'} "
            f"API {data.api or '—'} — {len(data.casing)} strings"
        )
        _render_meta(cache["meta_card"], data)
        cache["meta_card"].visible = True

        if state.casing_survey_df is not None and not state.casing_survey_df.empty:
            cache["survey_status"].text = f"Using survey: {state.casing_survey_label}"
            cache["survey_status"].classes(
                replace="text-sm px-3 py-2 rounded bg-green-100 text-green-800"
            )
            cache["survey_upload_row"].visible = False
        else:
            cache["survey_status"].text = (
                "No directional survey loaded — TVDs use a synthetic vertical/"
                "lateral fallback. Upload a survey PDF below for precise values."
            )
            cache["survey_upload_row"].visible = True

        if state.casing_frac_gradient_psi_per_ft is not None:
            cache["frac_input"].value = f"{state.casing_frac_gradient_psi_per_ft:.4f}"

        cache["promote_btn"].enable()
        cache["gen_btn"].enable()

        if defer_heavy:
            _lazy_design_render()
        else:
            _rebuild_design_and_wbd()

        if state.casing_last_output_path is not None and state.casing_last_output_path.exists():
            cache["gen_status"].text = f"Saved {state.casing_last_output_path.name}"
            _render_result(
                cache["result_card"],
                state.casing_last_output_path,
                _serve_output_file(state.casing_last_output_path),
            )
            cache["result_card"].visible = True

    def _rebuild_design_and_wbd() -> None:
        """Recompute design from state + render inputs / design table / WBD.

        Heavy — rebuilds the Plotly WBD figure. Don't call this on every
        page reconnect; only on explicit user action (parse, edit input,
        change frac gradient, change survey). For the initial render of
        a reconnected page, use ``_lazy_design_render`` which defers via
        a timer so the websocket can settle first.
        """
        data = state.apd_data
        if data is None:
            return
        frac = state.casing_frac_gradient_psi_per_ft or 1.0
        data.frac_gradient_psi_per_ft = frac
        welltrack = (
            welltrack_from_dataframe(state.casing_survey_df)
            if state.casing_survey_df is not None
            else None
        )
        design = engine.build(data, welltrack=welltrack)
        _apply_string_overrides(design, state.casing_overrides)

        _render_inputs(
            cache["inputs_card"], data, state, design,
            on_change=_rebuild_design_and_wbd,
        )
        cache["inputs_card"].visible = True

        _render_design(cache["design_card"], design)
        cache["design_card"].visible = True

        _render_wbd(cache["wbd_card"], design, data)
        cache["wbd_card"].visible = True

    def _lazy_design_render() -> None:
        """Schedule the heavy design rebuild for AFTER the page is mounted
        and the websocket has had a chance to settle. Prevents heartbeat
        timeouts from triggering an infinite disconnect/reconnect loop on
        pages that come up with state already populated."""
        if state.apd_data is None:
            return
        ui.timer(0.6, _rebuild_design_and_wbd, once=True)

    def refresh() -> None:
        """Fired by ``fire_refresh()`` after global state changes (Clear All,
        post_load completion, page reconnect). Defers the heavy design +
        WBD rebuild via a timer so it doesn't pile onto the event loop
        with the other tabs' refresh work and cause a heartbeat timeout."""
        _rebuild_from_state(defer_heavy=True)

    return refresh


# ---------------------------------------------------------------------------
# Pure rendering helpers (no closure state)
# ---------------------------------------------------------------------------


def _render_meta(card: ui.card, data: APDPdfData) -> None:
    card.clear()
    with card:
        ui.label("Extracted APD data").classes("text-sm font-semibold")
        if data.form_type != "apd":
            ui.label(
                "⚠ Could not confidently identify this PDF as a DOGM Form 3 APD."
            ).classes("text-xs p-2 rounded bg-amber-100 text-amber-900")
        for w in data.warnings:
            ui.label(w).classes("text-xs p-2 rounded bg-amber-50 text-amber-800")
        pairs = [
            ("Well", data.well_name),
            ("API", data.api),
            ("Operator", data.operator),
            ("Field", data.field_name),
            ("County", data.county),
            ("Type", data.well_type),
            ("Slant", data.slant),
            ("Proposed MD (ft)", data.proposed_md_ft),
            ("Proposed TVD (ft)", data.proposed_tvd_ft),
            ("Ground elev (ft)", data.ground_elev_ft),
            (
                "Frac grad @ shoe (psi/ft)",
                f"{data.frac_gradient_psi_per_ft:.4f}"
                if data.frac_gradient_psi_per_ft is not None
                else "—",
            ),
        ]
        with ui.grid(columns=4).classes("gap-x-6 gap-y-1 text-sm"):
            for label, value in pairs:
                ui.label(label).classes("text-gray-500")
                ui.label(str(value) if value not in (None, "") else "—")

        if data.locations:
            ui.label("Section 20 — well locations").classes(
                "text-sm font-semibold mt-3 text-gray-700"
            )
            loc_cols = [
                {"name": "name", "label": "Position", "field": "name", "align": "left"},
                {"name": "ns", "label": "N/S", "field": "ns"},
                {"name": "ew", "label": "E/W", "field": "ew"},
                {"name": "qq", "label": "QQ", "field": "qq", "align": "left"},
                {"name": "sec", "label": "Sec", "field": "sec"},
                {"name": "twp", "label": "Twp", "field": "twp", "align": "left"},
                {"name": "rng", "label": "Rng", "field": "rng", "align": "left"},
                {"name": "mer", "label": "M", "field": "mer", "align": "left"},
            ]
            loc_rows = [
                {
                    "name": L.name,
                    "ns": (
                        f"{int(L.fnl)} FNL" if L.fnl
                        else f"{int(L.fsl)} FSL" if L.fsl else "—"
                    ),
                    "ew": (
                        f"{int(L.fel)} FEL" if L.fel
                        else f"{int(L.fwl)} FWL" if L.fwl else "—"
                    ),
                    "qq": L.qtr_qtr or "—",
                    "sec": L.section or "—",
                    "twp": f"{L.township or '?'} {L.township_dir or ''}",
                    "rng": f"{L.range or '?'} {L.range_dir or ''}",
                    "mer": L.meridian or "—",
                }
                for L in data.locations
            ]
            ui.table(columns=loc_cols, rows=loc_rows, row_key="name").classes(
                "w-full text-xs"
            ).props("dense flat bordered")

        if data.casing:
            ui.label("Hole, Casing & Cement Information").classes(
                "text-sm font-semibold mt-3 text-gray-700"
            )
            cs_cols = [
                {"name": "tag", "label": "Tag", "field": "tag", "align": "left"},
                {"name": "hole", "label": 'Hole"', "field": "hole"},
                {"name": "csg", "label": 'Csg"', "field": "csg"},
                {"name": "depth", "label": "Length (ft)", "field": "depth"},
                {"name": "wt", "label": "Wt", "field": "wt"},
                {"name": "grade", "label": "Grade", "field": "grade", "align": "left"},
                {"name": "collar", "label": "Collar", "field": "collar", "align": "left"},
                {"name": "mw", "label": "Max MW", "field": "mw"},
                {"name": "lead", "label": "Lead cement", "field": "lead", "align": "left"},
                {"name": "tail", "label": "Tail cement", "field": "tail", "align": "left"},
            ]
            cs_rows = [
                {
                    "tag": cs.tag,
                    "hole": cs.hole_size_in,
                    "csg": cs.casing_size_in,
                    "depth": f"{int(cs.length_top_ft or 0)}-{int(cs.length_bottom_ft or 0)}",
                    "wt": cs.weight_ppf,
                    "grade": cs.grade or "—",
                    "collar": cs.collar or "—",
                    "mw": cs.max_mud_weight_ppg,
                    "lead": (
                        f"{cs.cement_lead_type or '—'} · "
                        f"{cs.cement_lead_sacks or 0} sx @ {cs.cement_lead_yield or 0}"
                    ),
                    "tail": (
                        f"{cs.cement_tail_type or '—'} · "
                        f"{cs.cement_tail_sacks or 0} sx @ {cs.cement_tail_yield or 0}"
                    ),
                }
                for cs in data.casing
            ]
            ui.table(columns=cs_cols, rows=cs_rows, row_key="tag").classes(
                "w-full text-xs"
            ).props("dense flat bordered")


def _apply_string_overrides(design: CasingDesign, overrides: dict) -> None:
    for idx, knobs in overrides.items():
        if idx >= len(design.strings):
            continue
        s = design.strings[idx]
        for k, v in knobs.items():
            if v is None:
                continue
            setattr(s, k, v)
    design.finalize()


_DESIGN_COLS = [
    {"name": "label", "label": "String", "field": "label", "align": "left"},
    {"name": "od", "label": 'OD"', "field": "od"},
    {"name": "wt", "label": "Wt", "field": "wt"},
    {"name": "grade", "label": "Grade", "field": "grade", "align": "left"},
    {"name": "depth", "label": "Set MD", "field": "depth"},
    {"name": "tvd", "label": "TVD", "field": "tvd"},
    {"name": "masp", "label": "MASP psi", "field": "masp"},
    {"name": "burst", "label": "Burst psi", "field": "burst"},
    {"name": "burst_load", "label": "Burst load", "field": "burst_load"},
    {"name": "burst_df", "label": "Burst DF", "field": "burst_df"},
    {"name": "collapse", "label": "Coll psi", "field": "collapse"},
    {"name": "collapse_load", "label": "Coll load", "field": "collapse_load"},
    {"name": "collapse_df", "label": "Coll DF", "field": "collapse_df"},
    {"name": "tension_klbs", "label": "Joint klbs", "field": "tension_klbs"},
    {"name": "tension_df", "label": "Tens DF", "field": "tension_df"},
    {"name": "toc", "label": "TOC", "field": "toc"},
    {"name": "verdict", "label": "Status", "field": "verdict", "align": "left"},
]


def _design_rows(design: CasingDesign) -> list[dict]:
    rows = []
    for s in design.strings:
        verdict = s.design_passes()
        status = (
            "✓ All passes"
            if all(verdict.values())
            else "⚠ " + ", ".join(f"{k} fail" for k, ok in verdict.items() if not ok)
        )
        rows.append(
            {
                "label": s.label,
                "od": s.od_in,
                "wt": s.weight_ppf,
                "grade": f"{s.grade}/{s.collar or '—'}",
                "depth": _fmt(s.set_depth_md_ft, 0),
                "tvd": _fmt(s.set_depth_tvd_ft, 0),
                "masp": _fmt(s.masp_psi, 0),
                "burst": _fmt(s.burst_psi, 0),
                "burst_load": _fmt(s.burst_load_psi, 0),
                "burst_df": _fmt(s.burst_df, 2),
                "collapse": _fmt(s.collapse_psi, 0),
                "collapse_load": _fmt(s.collapse_load_psi, 0),
                "collapse_df": _fmt(s.collapse_df, 2),
                "tension_klbs": _fmt(s.joint_klbs, 0),
                "tension_df": _fmt(s.tension_df, 2),
                "toc": s.top_of_cement_ft
                if isinstance(s.top_of_cement_ft, str)
                else _fmt(s.top_of_cement_ft, 0),
                "verdict": status,
            }
        )
    return rows


def _render_design(card: ui.card, design: CasingDesign) -> None:
    card.clear()
    with card:
        ui.label("Computed casing design").classes("text-sm font-semibold")
        ui.label(
            "Pass/fail vs. minimum design factor (collapse 1.125, burst 1.0, "
            "tension by connection)."
        ).classes("text-xs text-gray-600 mb-2")
        ui.table(
            columns=_DESIGN_COLS, rows=_design_rows(design), row_key="label"
        ).classes("w-full text-xs").props("dense flat bordered")


def _render_wbd(card: ui.card, design: CasingDesign, data: APDPdfData) -> None:
    from etools.core.casing_review.wbd import FormationMark, render_wellbore_figure

    card.clear()
    formations = [
        FormationMark(name=f.name, tvd_ft=f.tvd_ft)
        for f in (data.formations or [])
        if f.tvd_ft is not None
    ]
    fig = render_wellbore_figure(design, formations=formations)
    fig.update_layout(autosize=False)
    with card:
        ui.label("Vertical Wellbore Diagram").classes("text-sm font-semibold")
        ui.plotly(fig).style("min-height: 700px;")


def _render_inputs(
    card: ui.card,
    data: APDPdfData,
    state: AppState,
    design: CasingDesign,
    *,
    on_change,
) -> None:
    """Editable per-string inputs. Edits mutate ``data.casing[*]`` and
    ``state.casing_overrides``, then trigger ``on_change``."""
    from etools.core.casing_review.engine import _TAG_TO_LABEL  # type: ignore

    card.clear()
    overrides = state.casing_overrides

    with card:
        ui.label("Casing string inputs (editable)").classes("text-sm font-semibold")
        ui.label(
            "Edit any cell — design table and WBD recompute when you tab away."
        ).classes("text-xs text-gray-600 mb-2")

        for design_idx, s in enumerate(design.strings):
            apd = _design_idx_to_apd(data, design_idx)
            if apd is None:
                continue
            with ui.row().classes(
                "items-center gap-1 mt-1 flex-wrap p-2 rounded bg-slate-50"
            ):
                ui.label(s.label).classes("font-semibold w-24 text-xs")

                def _on_apd(attr, apd_ref=apd, cast=float):
                    return lambda e: (
                        setattr(apd_ref, attr, _parse_optional(e.sender.value, cast=cast)),
                        on_change(),
                    )

                def _on_ovr(attr, idx=design_idx, cast=float):
                    return lambda e: (
                        overrides.setdefault(idx, {}).__setitem__(
                            attr, _parse_optional(e.sender.value, cast=cast)
                        ),
                        on_change(),
                    )

                for label, value, attr, ovr, cast, width in [
                    ("hole",     apd.hole_size_in,       "hole_size_in",       False, float, "w-16"),
                    ("csg",      apd.casing_size_in,     "casing_size_in",     False, float, "w-16"),
                    ("set MD",   apd.length_bottom_ft,   "length_bottom_ft",   False, float, "w-20"),
                    ("wt",       apd.weight_ppf,         "weight_ppf",         False, float, "w-14"),
                    ("grade",    apd.grade,              "grade",              False, str,   "w-20"),
                    ("collar",   apd.collar,             "collar",             False, str,   "w-16"),
                    ("MW",       apd.max_mud_weight_ppg, "max_mud_weight_ppg", False, float, "w-14"),
                    ("washout%", s.hole_washout_pct,     "hole_washout_pct",   True,  float, "w-16"),
                    ("int grad", s.internal_gradient_psi_per_ft, "internal_gradient_psi_per_ft", True, float, "w-16"),
                    ("lead sx",  apd.cement_lead_sacks,  "cement_lead_sacks",  False, int,   "w-16"),
                    ("lead yld", apd.cement_lead_yield,  "cement_lead_yield",  False, float, "w-16"),
                    ("tail sx",  apd.cement_tail_sacks,  "cement_tail_sacks",  False, int,   "w-16"),
                    ("tail yld", apd.cement_tail_yield,  "cement_tail_yield",  False, float, "w-16"),
                ]:
                    ui.label(label).classes("text-xs text-gray-500")
                    inp = (
                        ui.input(value=str(value) if value is not None else "")
                        .props("dense outlined")
                        .classes(width)
                    )
                    handler = _on_ovr(attr, cast=cast) if ovr else _on_apd(attr, cast=cast)
                    inp.on("blur", handler)
                    inp.on("keydown.enter", handler)


def _design_idx_to_apd(data: APDPdfData, design_idx: int):
    from etools.core.casing_review.engine import _TAG_TO_LABEL  # type: ignore

    for cs in data.casing:
        mapping = _TAG_TO_LABEL.get(cs.tag)
        if mapping is None:
            continue
        _, idx = mapping
        if idx == design_idx:
            return cs
    return None


def _parse_optional(raw, *, cast=float):
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        if cast is str:
            return s
        try:
            return cast(float(s.replace(",", ""))) if cast is int else cast(s.replace(",", ""))
        except (TypeError, ValueError):
            return None
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return None


def _render_result(card: ui.card, path: Path, download_url: str) -> None:
    card.clear()
    with card:
        with ui.row().classes("items-center gap-3 w-full"):
            ui.label("Generated Casing Review").classes("text-sm font-semibold flex-1")
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
                on_click=lambda: ui.download(str(path)),
            ).props("flat dense color=primary")
        ui.label(str(path)).classes("text-xs text-gray-500 break-all")


def _fmt(value, ndigits: int) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if ndigits == 0:
        return f"{int(round(v)):,}"
    return f"{v:,.{ndigits}f}"


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
