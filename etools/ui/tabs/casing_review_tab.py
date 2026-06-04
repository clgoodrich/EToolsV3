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
from etools.core.pdf.apd_parser import parse_apd_pdf
from etools.core.pdf.parser import parse_survey_pdf
from etools.logging_setup import get_logger
from etools.models import APDPdfData
from etools.repositories import SurveyRepository
from etools.services import CasingReviewService
from etools.ui.promote import promote_apd_to_active
from etools.ui.state import AppState

log = get_logger(__name__)


# JS executed on every plat-SVG render. Idempotently defines:
#   * etoolsSetSegHover(key, on) — toggles hover highlight on a segment
#     line + its matching cell card.
#   * etoolsWireSegHover() — attaches mouseenter/leave to every new
#     line.seg-line and every new .seg-cell.
#   * etoolsWirePlatPanZoom() — attaches wheel-zoom + click-drag-pan +
#     double-click-reset to every new svg.plat-svg.
#   * __etoolsWireAll() — runs both wiring functions.
#
# The script is invoked via ui.run_javascript after each ui.html(svg)
# insert; setTimeout(...,0) ensures Vue has flushed the DOM update first.
_PLAT_RUNTIME_JS = r"""
(function(){
  if (window.__etoolsPlatRuntimeReady) return;
  window.__etoolsPlatRuntimeReady = true;

  window.etoolsSetSegHover = function(key, on) {
    try {
      var cell = document.getElementById('seg-cell-' + key);
      if (cell) cell.classList.toggle('seg-cell-hover', on);
      document.querySelectorAll('line.seg-line[data-seg="' + key + '"]').forEach(function(ln){
        ln.classList.toggle('seg-line-hover', on);
      });
    } catch (e) {}
  };

  window.etoolsWireSegHover = function() {
    document.querySelectorAll('line.seg-line').forEach(function(el){
      if (el.__wired) return;
      el.__wired = true;
      var key = el.getAttribute('data-seg');
      el.addEventListener('mouseenter', function(){ etoolsSetSegHover(key, true); });
      el.addEventListener('mouseleave', function(){ etoolsSetSegHover(key, false); });
    });
    document.querySelectorAll('.seg-cell').forEach(function(el){
      if (el.__wired) return;
      el.__wired = true;
      var id = el.id || '';
      var key = id.indexOf('seg-cell-') === 0 ? id.slice(9) : '';
      if (!key) return;
      el.addEventListener('mouseenter', function(){ etoolsSetSegHover(key, true); });
      el.addEventListener('mouseleave', function(){ etoolsSetSegHover(key, false); });
    });
  };

  window.etoolsWirePlatPanZoom = function() {
    document.querySelectorAll('svg.plat-svg').forEach(function(svg){
      if (svg.__panzoomWired) return;
      svg.__panzoomWired = true;
      var vbAttr = (svg.getAttribute('viewBox') || '').trim().split(/\s+/).map(Number);
      if (vbAttr.length !== 4 || vbAttr.some(isNaN)) return;
      var st  = {x:vbAttr[0], y:vbAttr[1], w:vbAttr[2], h:vbAttr[3]};
      var initX = st.x, initY = st.y, initW = st.w, initH = st.h;
      function apply(){
        svg.setAttribute('viewBox', st.x+' '+st.y+' '+st.w+' '+st.h);
      }
      svg.addEventListener('wheel', function(e){
        e.preventDefault();
        var r = svg.getBoundingClientRect();
        if (!r.width || !r.height) return;
        var mx = (e.clientX - r.left) / r.width;
        var my = (e.clientY - r.top)  / r.height;
        var f  = e.deltaY > 0 ? 1.15 : (1/1.15);
        var nw = st.w * f, nh = st.h * f;
        if (nw > initW * 50 || nw < initW * 0.02) return;
        st.x = st.x + (st.w - nw) * mx;
        st.y = st.y + (st.h - nh) * my;
        st.w = nw; st.h = nh;
        apply();
      }, {passive:false});
      var drag = false, sx=0, sy=0, ox=0, oy=0;
      svg.addEventListener('mousedown', function(e){
        if (e.button !== 0) return;
        drag = true;
        sx = e.clientX; sy = e.clientY;
        ox = st.x; oy = st.y;
        svg.style.cursor = 'grabbing';
        e.preventDefault();
      });
      window.addEventListener('mousemove', function(e){
        if (!drag) return;
        var r = svg.getBoundingClientRect();
        if (!r.width || !r.height) return;
        var dx = (e.clientX - sx) * (st.w / r.width);
        var dy = (e.clientY - sy) * (st.h / r.height);
        st.x = ox - dx; st.y = oy - dy;
        apply();
      });
      window.addEventListener('mouseup', function(){
        if (!drag) return;
        drag = false;
        svg.style.cursor = '';
      });
      svg.addEventListener('dblclick', function(e){
        e.preventDefault();
        st.x = initX; st.y = initY; st.w = initW; st.h = initH;
        apply();
      });
    });
  };

  window.__etoolsWireAll = function(){
    window.etoolsWireSegHover();
    window.etoolsWirePlatPanZoom();
  };

  // Catch-all: any future DOM insertion also gets wired automatically.
  try {
    var mo = new MutationObserver(function(){ window.__etoolsWireAll(); });
    mo.observe(document.body, {childList:true, subtree:true});
  } catch (e) {}
})();
"""


def render_casing_review_tab(state: AppState) -> Callable[[], None]:
    svc = CasingReviewService()
    engine = CasingDesignEngine()
    survey_repo = SurveyRepository()

    # Inject the segment-hover + pan/zoom CSS via add_head_html (this
    # part is purely declarative and always runs at page load). The
    # imperative JS that wires events lives in ``_install_plat_runtime``
    # which is called via ui.run_javascript on every render so it always
    # runs AFTER the SVG is in the DOM, regardless of add_head_html's
    # quirks inside @page handlers.
    ui.add_head_html(
        """
        <style>
          .seg-line { vector-effect: non-scaling-stroke;
                      stroke: #475569; stroke-width: 1.4;
                      transition: stroke .08s, stroke-width .08s;
                      cursor: pointer; }
          .seg-line-hover { stroke: #f59e0b !important;
                            stroke-width: 5 !important; }
          .seg-cell-hover .q-card { box-shadow: 0 0 0 2px #f59e0b !important;
                                    background: #fffbeb !important;
                                    transition: box-shadow .08s; }
          .seg-cell { transition: box-shadow .08s; }
          svg.plat-svg { cursor: grab; touch-action: none; }
          svg.plat-svg:active { cursor: grabbing; }
        </style>
        """
    )

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
    #
    # Two-zone design:
    #   * Sticky control panel at the top with everything the user needs to
    #     act on (upload + parse + survey + frac + promote + generate buttons
    #     + status badges) — always visible, never collapsed.
    #   * Stack of collapsible expansions below for the heavy work areas
    #     (Parsed APD / Inputs / Design / Sections / WBD / Output). The
    #     ones that aren't immediately load-bearing (parsed APD dump, the
    #     editable inputs detail, the Plotly WBD) default to collapsed so
    #     the page stays scannable.
    # ----------------------------------------------------------------------
    with ui.column().classes("p-4 gap-3 w-full"):
        ui.label("Casing Review").classes("text-xl font-semibold")

        # Empty-state shown until an APD is loaded on the Load Well tab.
        cache["empty_state"] = ui.card().classes(
            "w-full bg-slate-50 border border-dashed border-slate-300 p-6"
        )
        with cache["empty_state"]:
            ui.label("No APD loaded").classes("text-sm font-semibold text-slate-700")
            ui.label(
                "Go to the Load Well tab → From APD PDF to upload and parse "
                "an APD application. You'll be routed back here automatically."
            ).classes("text-xs text-slate-600")

        # --- COMPACT ACTION BAR (visible once APD is parsed) ----------
        cache["action_bar"] = ui.card().classes(
            "w-full bg-slate-50 border border-slate-200"
        )
        cache["action_bar"].visible = False
        with cache["action_bar"]:
            with ui.row().classes("gap-3 items-center w-full"):
                cache["source_label"] = ui.label("").classes(
                    "text-xs text-slate-600 font-mono"
                )
                ui.space()
                cache["survey_status"] = ui.label("").classes(
                    "text-xs px-2 py-1 rounded bg-slate-200 text-slate-700"
                )
                ui.label("Frac:").classes("text-xs text-slate-600 ml-2")
                cache["frac_input"] = (
                    ui.input(value="1.00")
                    .props("dense outlined suffix=psi/ft")
                    .classes("w-28")
                    .on("blur", lambda _: _on_frac_change())
                    .on("keydown.enter", lambda _: _on_frac_change())
                )
                cache["promote_btn"] = ui.button(
                    "Use as active well",
                    icon="upgrade",
                    on_click=lambda: promote_to_primary(),
                ).props("color=secondary dense")
                cache["promote_btn"].tooltip(
                    "Push this APD + survey into shared state so Survey, "
                    "Map & Viz, and Clearance tabs populate with this well."
                )
                cache["gen_btn"] = ui.button(
                    "Generate Excel",
                    icon="description",
                    on_click=lambda: generate(),
                ).props("color=primary dense")
            # Survey-PDF upload only appears when no DB survey was found.
            cache["survey_upload_row"] = ui.row().classes("gap-2 items-center mt-1")
            with cache["survey_upload_row"]:
                survey_upload = ui.upload(
                    label="Survey PDF (optional)",
                    auto_upload=True,
                    multiple=False,
                    on_upload=lambda e: handle_survey_upload(e),
                    on_rejected=lambda e: ui.notify(
                        f"Upload rejected: {e}", type="negative"
                    ),
                ).classes("max-w-xs").props("accept=.pdf flat dense")
            cache["survey_upload_row"].visible = False
            cache["gen_status"] = ui.label("").classes("text-xs text-slate-500")

        # Legacy aliases the existing handlers still reach for.
        cache["apd_status"] = cache["source_label"]
        cache["mode_select"] = None  # not used here anymore
        cache["parse_btn"] = None    # not used here anymore

        # --- SUB-TABS (one tab per work area) -------------------------
        # Whole tabs widget hidden until an APD is parsed.
        cache["tabs_wrap"] = ui.element("div").classes("w-full")
        cache["tabs_wrap"].visible = False
        with cache["tabs_wrap"]:
            with ui.tabs().classes("w-full") as cr_tabs:
                cache["meta_tab"] = ui.tab("Parsed APD", icon="description")
                cache["inputs_tab"] = ui.tab("Casing inputs", icon="edit_note")
                cache["design_tab"] = ui.tab("Computed design", icon="calculate")
                cache["sections_tab"] = ui.tab("Sections", icon="grid_on")
                cache["wbd_tab"] = ui.tab("WBD", icon="view_in_ar")
                cache["result_tab"] = ui.tab("Output", icon="folder_open")
            with ui.tab_panels(cr_tabs, value=cache["meta_tab"]).classes("w-full"):
                with ui.tab_panel(cache["meta_tab"]) as p:
                    cache["meta_card"] = p
                with ui.tab_panel(cache["inputs_tab"]) as p:
                    cache["inputs_card"] = p
                with ui.tab_panel(cache["design_tab"]) as p:
                    cache["design_card"] = p
                with ui.tab_panel(cache["sections_tab"]) as p:
                    cache["sections_card"] = p
                with ui.tab_panel(cache["wbd_tab"]) as p:
                    cache["wbd_card"] = p
                with ui.tab_panel(cache["result_tab"]) as p:
                    cache["result_card"] = p
        # Each tab button is hidden until its content has been rendered.
        for k in ("meta_tab", "inputs_tab", "design_tab",
                  "sections_tab", "wbd_tab", "result_tab"):
            cache[k].visible = False

    # ----------------------------------------------------------------------
    # If state already carries APD data (e.g. user navigated away and back,
    # or a WebSocket reconnect re-ran the page render), immediately rebuild
    # the dynamic cards. This means the tab is populated without needing
    # fire_refresh to fire — important because fire_refresh's heavy work
    # in other tabs can be deferred / delayed.
    # ----------------------------------------------------------------------
    # Initial-render restore from state happens at the end, AFTER
    # _rebuild_from_state and friends are defined further down in this
    # function. See the call right before `return refresh` below.

    # ----------------------------------------------------------------------
    # Event handlers — they write to ``state`` (not cache) so reconnects
    # preserve everything. Upload + parse moved to the Load Well tab.
    # ----------------------------------------------------------------------
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
        # Manual 'Use as active well'. Shares one implementation with the
        # Load Well tab's auto-promote; ``silent=False`` so the user gets
        # the "can't geolocate" explanation when it applies.
        await promote_apd_to_active(state, silent=False)

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
        # Drive the SHL/BHL Section sheets from the exact section traversal
        # the on-screen sub-tabs show, so every crossing (incl. BHL Section
        # 2 and any dynamic 4+) is filled — not just the 3 named APD rows.
        from etools.core.casing_review.sections import build_section_traversal

        crossings = build_section_traversal(data.locations, _clearance_points(state))
        section_locations = [c.to_location_row() for c in crossings]
        try:
            result = svc.generate(
                apd_data=data,
                survey=state.casing_survey_df,
                frac_gradient_override_psi_per_ft=frac,
                section_locations=section_locations or None,
            )
        except Exception as exc:
            log.exception("casing_review.generate_failed")
            ui.notify(f"Generation failed: {exc}", type="negative")
            return
        state.casing_last_output_path = result.output_path
        out = result.output_path
        cache["gen_status"].text = f"Saved {out.name}"
        _render_result(cache["result_card"], out, _serve_output_file(out))
        cache["result_tab"].visible = True
        ui.notify(f"Casing Review generated: {out.name}", type="positive")

    # ----------------------------------------------------------------------
    # Render helpers — all read from ``state`` so reconnects come up clean.
    # ----------------------------------------------------------------------
    def _hide_dynamic_cards() -> None:
        if cache.get("tabs_wrap") is not None:
            cache["tabs_wrap"].visible = False
        for k in ("meta_tab", "inputs_tab", "design_tab",
                  "sections_tab", "wbd_tab", "result_tab"):
            t = cache.get(k)
            if t is not None:
                t.visible = False

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
            cache["action_bar"].visible = False
            cache["empty_state"].visible = True
            return

        cache["empty_state"].visible = False
        cache["action_bar"].visible = True
        cache["source_label"].text = (
            f"{state.apd_pdf_name or 'APD'} · "
            f"{data.well_name or '(unnamed)'} · API {data.api or '—'} · "
            f"{len(data.casing)} strings"
        )
        cache["tabs_wrap"].visible = True
        _render_meta(cache["meta_card"], data)
        cache["meta_tab"].visible = True

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
            cache["result_tab"].visible = True

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

        # Inputs card is rendered once per full rebuild. Edits cascade
        # only to the design table + WBD (via _recompute_downstream) so
        # the input widget that fired the blur event isn't destroyed
        # mid-event by re-rendering its own parent.
        def _recompute_downstream() -> None:
            d = state.apd_data
            if d is None:
                return
            wt = (
                welltrack_from_dataframe(state.casing_survey_df)
                if state.casing_survey_df is not None
                else None
            )
            new_design = engine.build(d, welltrack=wt)
            _apply_string_overrides(new_design, state.casing_overrides)
            _render_design(cache["design_card"], new_design)
            _render_wbd(cache["wbd_card"], new_design, d)

        _render_inputs(
            cache["inputs_card"], data, state,
            on_change=_recompute_downstream,
        )
        cache["inputs_tab"].visible = True

        _render_design(cache["design_card"], design)
        cache["design_tab"].visible = True

        _render_sections(cache["sections_card"], data, state)
        cache["sections_tab"].visible = True

        _render_wbd(cache["wbd_card"], design, data)
        cache["wbd_tab"].visible = True

    def _lazy_design_render() -> None:
        """Used to defer the heavy design rebuild via ui.timer to keep the
        page-render path from blocking. Now that page renders are fast
        (<50 ms) and fire_refresh yields to the event loop between tab
        callbacks, we just call the rebuild inline. ui.timer indirection
        risks RuntimeError if its slot gets deleted by a reconnect."""
        if state.apd_data is None:
            return
        _rebuild_design_and_wbd()

    def refresh() -> None:
        """Fired by ``fire_refresh()`` after global state changes (Clear All,
        post_load completion, page reconnect). Rebuilds the full tab UI
        from ``state``."""
        _rebuild_from_state(defer_heavy=False)

    # If the persistent_state already carries APD data (reconnect with
    # previously-promoted well), restore the dynamic cards now.
    if state.apd_data is not None:
        _rebuild_from_state(defer_heavy=False)

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


def _render_sections(card: ui.card, data: APDPdfData, state: AppState) -> None:
    """SHL + BHL section sub-tabs — one tab per PLSS section the well crosses.

    Tab list comes from the trajectory's actual section traversal (the
    clearance result's Conc column, in MD order). First section = SHL
    Section, then BHL Section 1, 2, 3, …

    Each sub-tab carries the per-location coord switcher + the 3x3
    segment grid with each input pre-populated from the Grid Numbers DB.
    """
    card.clear()
    panels = _build_section_panels(data, state)

    with card:
        ui.label("Section sheets — SHL / BHL").classes("text-sm font-semibold")
        ui.label(
            "One sub-tab per section the well crosses (in MD order — SHL "
            "first, then BHL 1, 2, 3…). Each of the 16 boundary-segment "
            "inputs comes pre-populated from the Grid Numbers DB; type "
            "to override, blank to revert to the default. Overrides reshape "
            "the polygon drawn on Map & Viz."
        ).classes("text-xs text-gray-600 mb-2")

        if not panels:
            ui.label(
                "No sections detected yet — parse + promote the APD so "
                "the clearance step can identify which PLSS sections the "
                "well crosses."
            ).classes("text-xs text-amber-700 bg-amber-50 p-2 rounded")
            return

        with ui.tabs().classes("w-full").props("dense inline-label") as tabs:
            for sheet_name, _conc, _loc, _label in panels:
                ui.tab(sheet_name)
        first_name = panels[0][0]
        with ui.tab_panels(tabs, value=first_name).classes("w-full"):
            for sheet_name, conc, loc_point, display_label in panels:
                with ui.tab_panel(sheet_name):
                    _render_section_panel(
                        sheet_name, display_label, loc_point, conc, data, state
                    )


def _clearance_points(state: AppState):
    """The processed-survey points DataFrame from any loaded citing, or None.

    The section list is the same shape across citings, so the first one is
    representative.
    """
    if not state.clearances:
        return None
    cr = next(iter(state.clearances.values()))
    return getattr(cr, "points", None)


def _build_section_panels(
    data: APDPdfData, state: AppState
) -> list[tuple[str, str, dict, str]]:
    """Return [(sheet_name, conc, location_point, display_label), …] in MD order.

    Thin adapter over :func:`build_section_traversal` (the single source of
    truth shared with the Excel generator) into the tuple shape the panel
    renderer expects. ``location_point`` is a dict carrying
    ``fnl/fsl/fel/fwl``.
    """
    from etools.core.casing_review.sections import build_section_traversal

    crossings = build_section_traversal(data.locations, _clearance_points(state))
    panels: list[tuple[str, str, dict, str]] = []
    for idx, c in enumerate(crossings):
        sheet_name = "SHL Section" if idx == 0 else f"BHL Section {idx}"
        loc_point = {"fnl": c.fnl, "fsl": c.fsl, "fel": c.fel, "fwl": c.fwl}
        panels.append((sheet_name, c.conc, loc_point, c.label))
    return panels


def _render_section_panel(
    sheet_name: str,
    display_label: str,
    location_point: dict,
    conc: str,
    data: APDPdfData,
    state: AppState,
) -> None:
    from etools.core.casing_review.sections import (
        PLSSKey,
        build_section_definition,
    )

    ui.label(display_label).classes("text-base font-semibold")

    try:
        plss = PLSSKey.from_conc(conc)
    except ValueError:
        ui.label(f"Bad Conc code: {conc!r}").classes(
            "text-xs text-red-700 bg-red-50 p-2 rounded"
        )
        return

    sd = state.section_definitions.get(conc)
    if sd is None:
        # Lazy-build on demand so the panel works even before a promote.
        try:
            from etools.core.casing_review.grid_corners import GridCornerCatalog
            from etools.repositories import PlatRepository
            cat = GridCornerCatalog()
            repo = PlatRepository()
            base = repo._fetch_concs([conc])  # noqa: SLF001
            gdf = repo._build_sections(base) if not base.empty else None  # noqa: SLF001
            poly = gdf.iloc[0].geometry if gdf is not None and not gdf.empty else None
            sd = build_section_definition(plss=plss, catalog=cat, plat_polygon=poly)
            state.section_definitions[conc] = sd
        except Exception as exc:
            ui.label(f"Could not build SectionDefinition: {exc}").classes(
                "text-xs text-red-700 bg-red-50 p-2 rounded"
            )
            return

    # ----------------------------------------------------------------------
    # Per-location coordinate switcher (top of panel)
    # ----------------------------------------------------------------------
    fnl = location_point.get("fnl")
    fsl = location_point.get("fsl")
    fel = location_point.get("fel")
    fwl = location_point.get("fwl")
    initial_ns = "FNL" if fnl is not None else ("FSL" if fsl is not None else "FSL")
    initial_ew = "FEL" if fel is not None else ("FWL" if fwl is not None else "FWL")
    initial_ns_val = fnl if fnl is not None else (fsl if fsl is not None else 0.0)
    initial_ew_val = fel if fel is not None else (fwl if fwl is not None else 0.0)

    refs: dict = {}  # element refs for cross-syncing

    def _compute_from_footages() -> None:
        try:
            ns = refs["ns_dir"].value
            ew = refs["ew_dir"].value
            nv = float(refs["ns_val"].value or 0)
            ev = float(refs["ew_val"].value or 0)
            kwargs = {("fnl" if ns == "FNL" else "fsl"): nv,
                      ("fel" if ew == "FEL" else "fwl"): ev}
            r = sd.footages_to_latlon(**kwargs)
            _push_other_frames(r, skip="footages")
        except Exception as exc:
            log.warning("section_panel.footage_sync.failed", error=str(exc))

    def _compute_from_latlon() -> None:
        try:
            lat = float(refs["lat"].value)
            lon = float(refs["lon"].value)
            r = sd.latlon_to_footages(lat, lon)
            _push_other_frames(r, skip="latlon")
        except (ValueError, TypeError):
            pass

    def _compute_from_utm() -> None:
        try:
            e = float(refs["utm_e"].value)
            n = float(refs["utm_n"].value)
            r = sd.utm_to_footages(e, n)
            _push_other_frames(r, skip="utm")
        except (ValueError, TypeError):
            pass

    def _push_other_frames(r, *, skip: str) -> None:
        if skip != "footages":
            ns = refs["ns_dir"].value
            ew = refs["ew_dir"].value
            refs["ns_val"].value = f"{(r.fnl if ns == 'FNL' else r.fsl):.2f}"
            refs["ew_val"].value = f"{(r.fel if ew == 'FEL' else r.fwl):.2f}"
        if skip != "utm":
            refs["utm_e"].value = f"{r.utm_easting:.3f}"
            refs["utm_n"].value = f"{r.utm_northing:.3f}"
        if skip != "latlon":
            refs["lat"].value = f"{r.lat:.6f}"
            refs["lon"].value = f"{r.lon:.6f}"

    plat_holder: dict = {}

    def _refresh_plat() -> None:
        if plat_holder.get("container") is None:
            return
        _render_plat_svg(plat_holder["container"], sd, state)

    # ------------------------------------------------------------------
    # Top: 2-column row.
    #   LEFT  — 3x3 section-geometry grid (16 cells + plat preview)
    #   RIGHT — this panel's location (footages / lat-lon / UTM /
    #           north-reference), pinned to a fixed-width side card.
    # ------------------------------------------------------------------
    with ui.row().classes("w-full gap-3 flex-nowrap items-start mt-2"):
        # ---- LEFT: section geometry ----
        with ui.column().classes("gap-1 shrink-0"):
            with ui.row().classes("w-full items-baseline gap-3"):
                ui.label(f"PLSS {plss.conc}").classes(
                    "text-xs font-mono text-gray-700"
                )
                ui.label(
                    f"Sec {plss.section} T{plss.township}"
                    f"{'N' if plss.township_dir==1 else 'S'} "
                    f"R{plss.range_}{'E' if plss.range_dir==1 else 'W'} "
                    f"{'SaltLake' if plss.baseline==1 else 'Uintah'}"
                ).classes("text-xs text-gray-500")
            with ui.element("div").style(
                "display: grid; "
                "grid-template-columns: 170px repeat(4, 170px) 170px; "
                "grid-template-rows: auto repeat(4, auto) auto; "
                "gap: 4px;"
            ):
                for col, key in enumerate(
                    ["North-Left2", "North-Left1", "North-Right1", "North-Right2"],
                    start=2,
                ):
                    with ui.element("div").style(f"grid-column: {col}; grid-row: 1;"):
                        _render_segment_cell(sd, key, state, _refresh_plat)
                for row, key in enumerate(
                    ["West-Up2", "West-Up1", "West-Down1", "West-Down2"],
                    start=2,
                ):
                    with ui.element("div").style(f"grid-column: 1; grid-row: {row};"):
                        _render_segment_cell(sd, key, state, _refresh_plat)
                for row, key in enumerate(
                    ["East-Up2", "East-Up1", "East-Down1", "East-Down2"],
                    start=2,
                ):
                    with ui.element("div").style(f"grid-column: 6; grid-row: {row};"):
                        _render_segment_cell(sd, key, state, _refresh_plat)
                for col, key in enumerate(
                    ["South-Left2", "South-Left1", "South-Right1", "South-Right2"],
                    start=2,
                ):
                    with ui.element("div").style(f"grid-column: {col}; grid-row: 6;"):
                        _render_segment_cell(sd, key, state, _refresh_plat)
                with ui.element("div").style(
                    "grid-column: 2 / span 4; grid-row: 2 / span 4; "
                    "display: flex; align-items: center; justify-content: center;"
                ):
                    plat_holder["container"] = ui.element("div").style(
                        "width: 100%; height: 100%; "
                        "border: 1px solid #cbd5e1; border-radius: 6px; "
                        "background: white; padding: 4px; "
                        "display: flex; flex-direction: column;"
                    )
                    _render_plat_svg(plat_holder["container"], sd, state)

        # ---- RIGHT: coord switcher (top) + APD locations (below), stacked ----
        with ui.column().classes("gap-2 shrink-0").style("width: 340px;"):
            with ui.card().classes("w-full p-3 gap-1"):
                ui.label(display_label).classes(
                    "text-sm font-semibold text-gray-700"
                )
                ui.label(
                    "Footages / lat-lon / UTM auto-sync; edit any one."
                ).classes("text-xs text-gray-500 mb-1")

                with ui.row().classes("gap-2 items-center no-wrap w-full"):
                    refs["ns_dir"] = ui.toggle(
                        {"FNL": "FNL", "FSL": "FSL"},
                        value=initial_ns,
                        on_change=lambda _: _compute_from_footages(),
                    ).props("dense")
                    refs["ns_val"] = (
                        ui.input(value=f"{initial_ns_val:.2f}")
                        .props("dense outlined hide-bottom-space suffix=ft")
                        .classes("flex-1 min-w-0")
                        .on("blur", lambda _: _compute_from_footages())
                        .on("keydown.enter", lambda _: _compute_from_footages())
                    )
                with ui.row().classes("gap-2 items-center no-wrap w-full"):
                    refs["ew_dir"] = ui.toggle(
                        {"FEL": "FEL", "FWL": "FWL"},
                        value=initial_ew,
                        on_change=lambda _: _compute_from_footages(),
                    ).props("dense")
                    refs["ew_val"] = (
                        ui.input(value=f"{initial_ew_val:.2f}")
                        .props("dense outlined hide-bottom-space suffix=ft")
                        .classes("flex-1 min-w-0")
                        .on("blur", lambda _: _compute_from_footages())
                        .on("keydown.enter", lambda _: _compute_from_footages())
                    )

                with ui.row().classes("gap-2 no-wrap w-full"):
                    refs["lat"] = (
                        ui.input(value="")
                        .props('dense outlined hide-bottom-space stack-label label="Lat"')
                        .classes("flex-1 min-w-0")
                        .on("blur", lambda _: _compute_from_latlon())
                        .on("keydown.enter", lambda _: _compute_from_latlon())
                    )
                    refs["lon"] = (
                        ui.input(value="")
                        .props('dense outlined hide-bottom-space stack-label label="Lon"')
                        .classes("flex-1 min-w-0")
                        .on("blur", lambda _: _compute_from_latlon())
                        .on("keydown.enter", lambda _: _compute_from_latlon())
                    )

                with ui.row().classes("gap-2 no-wrap w-full"):
                    refs["utm_e"] = (
                        ui.input(value="")
                        .props('dense outlined hide-bottom-space stack-label label="UTM E"')
                        .classes("flex-1 min-w-0")
                        .on("blur", lambda _: _compute_from_utm())
                        .on("keydown.enter", lambda _: _compute_from_utm())
                    )
                    refs["utm_n"] = (
                        ui.input(value="")
                        .props('dense outlined hide-bottom-space stack-label label="UTM N"')
                        .classes("flex-1 min-w-0")
                        .on("blur", lambda _: _compute_from_utm())
                        .on("keydown.enter", lambda _: _compute_from_utm())
                    )

                with ui.row().classes("gap-2 items-center"):
                    ui.label("North ref:").classes("text-xs text-gray-500")
                    ui.toggle(
                        {"T": "True", "G": "Grid", "M": "Magnetic"},
                        value=sd.north_ref_choice,
                        on_change=lambda e: setattr(sd, "north_ref_choice", e.value),
                    ).props("dense")
                    ui.label("Z12 N").classes("text-xs text-gray-500 ml-auto")

            # Extracted APD well locations — stacked under the switcher.
            if data.locations:
                with ui.card().classes(
                    "w-full bg-amber-50 border border-amber-200 p-2 gap-1"
                ):
                    ui.label("Extracted APD well locations").classes(
                        "text-sm font-semibold text-amber-900"
                    )
                    for L in data.locations:
                        ns = (f"{int(L.fnl)} FNL" if L.fnl
                              else f"{int(L.fsl)} FSL" if L.fsl else "—")
                        ew = (f"{int(L.fel)} FEL" if L.fel
                              else f"{int(L.fwl)} FWL" if L.fwl else "—")
                        with ui.column().classes(
                            "gap-0 px-2 py-1 bg-white/60 rounded border "
                            "border-amber-200 w-full"
                        ):
                            ui.label(L.name).classes(
                                "text-xs font-semibold text-amber-900"
                            )
                            ui.label(f"{ns} · {ew}").classes(
                                "text-xs text-amber-800 font-mono"
                            )
                            ui.label(
                                f"Sec {L.section or '—'} "
                                f"T{L.township or '?'}{L.township_dir or ''} "
                                f"R{L.range or '?'}{L.range_dir or ''} "
                                f"{L.meridian or '—'}"
                            ).classes("text-xs text-amber-700 font-mono")

    # Seed lat/lon + UTM from the initial footages.
    if (fnl is not None or fsl is not None) and (fel is not None or fwl is not None):
        _compute_from_footages()


def _render_segment_cell(
    sd, seg_key: str, state: AppState, on_geometry_change
) -> None:
    """One editable *cell* for a Grid Numbers boundary segment, laid out
    vertically (label on top, then dist/deg/min/sec/align stacked, then
    a small reset button). Sized for the perimeter frame layout.

    Pre-populated with the *effective* value (override if set, else the
    Grid Numbers DB default). On any edit fires ``state.viz_refresh()``
    AND the local ``on_geometry_change`` so the center plat redraws.
    """
    from etools.core.casing_review.sections import SegmentData

    default = sd.segments.get(seg_key, SegmentData())

    def _effective(field: str):
        ov = sd.segment_overrides.get(seg_key)
        if ov is not None:
            v = getattr(ov, field)
            if v is not None:
                return v
        return getattr(default, field)

    def _fmt(value, kind: str) -> str:
        if value is None:
            return ""
        if kind == "float":
            return f"{value:.2f}"
        return str(int(value))

    def _fire_viz_refresh() -> None:
        cb = getattr(state, "viz_refresh", None)
        if cb is not None:
            try:
                cb()
            except Exception as exc:
                log.warning("section_panel.viz_refresh.failed", error=str(exc))
        if on_geometry_change is not None:
            try:
                on_geometry_change()
            except Exception as exc:
                log.warning("section_panel.plat_refresh.failed", error=str(exc))

    def _apply():
        new_dist = _parse_optional(refs["dist"].value, cast=float)
        new_deg = _parse_optional(refs["deg"].value, cast=int)
        new_min = _parse_optional(refs["min"].value, cast=int)
        new_sec = _parse_optional(refs["sec"].value, cast=int)
        new_align = _parse_optional(refs["dir"].value, cast=int)

        def _diff(new, base):
            if new is None:
                return None
            if base is not None and abs(float(new) - float(base)) < 1e-6:
                return None
            return new

        ov = SegmentData(
            length_ft=_diff(new_dist, default.length_ft),
            degrees=_diff(new_deg, default.degrees),
            minutes=_diff(new_min, default.minutes),
            seconds=_diff(new_sec, default.seconds),
            alignment=_diff(new_align, default.alignment),
            north_ref=default.north_ref,
        )
        if ov.is_blank():
            sd.segment_overrides.pop(seg_key, None)
        else:
            sd.segment_overrides[seg_key] = ov
        badge.text = "✎" if seg_key in sd.segment_overrides else ""
        _fire_viz_refresh()

    def _reset():
        sd.segment_overrides.pop(seg_key, None)
        refs["dist"].value = _fmt(default.length_ft, "float")
        refs["deg"].value = _fmt(default.degrees, "int")
        refs["min"].value = _fmt(default.minutes, "int")
        refs["sec"].value = _fmt(default.seconds, "int")
        refs["dir"].value = _fmt(default.alignment, "int")
        badge.text = ""
        _fire_viz_refresh()

    refs: dict = {}
    # Compact cell — wrapped in a plain div with a stable DOM id so the
    # plat SVG's segment hover handlers can highlight the matching cell.
    # Labels float inside each Quasar input (label= prop) so no external
    # label rows are needed; that's what keeps the cell short.
    dom_id = f"seg-cell-{seg_key}"
    with ui.element("div").props(f'id="{dom_id}"').classes(
        "seg-cell w-full h-full"
    ):
        with ui.card().classes("p-1 w-full h-full"):
            with ui.row().classes("items-center gap-1 w-full no-wrap"):
                ui.label(seg_key).classes(
                    "text-[11px] font-mono font-semibold text-gray-700 "
                    "flex-1 truncate leading-none"
                )
                badge = ui.label(
                    "✎" if seg_key in sd.segment_overrides else ""
                ).classes("text-xs text-amber-600 w-3")
                ui.button(icon="restart_alt", on_click=lambda _=None: _reset()).props(
                    "flat dense round size=xs color=grey"
                ).tooltip("Reset to Grid Numbers DB default")

            def _mk_input(*, value: str, label: str, tooltip: str | None = None,
                          width_cls: str = "w-full"):
                inp = (
                    ui.input(value=value)
                    .props(f'dense outlined hide-bottom-space stack-label label="{label}"')
                    .classes(width_cls)
                    .on("blur", lambda _: _apply())
                    .on("keydown.enter", lambda _: _apply())
                )
                if tooltip:
                    inp.tooltip(tooltip)
                return inp

            refs["dist"] = _mk_input(
                value=_fmt(_effective("length_ft"), "float"),
                label="Distance (ft)",
            )
            with ui.row().classes("gap-1 w-full no-wrap"):
                refs["deg"] = _mk_input(
                    value=_fmt(_effective("degrees"), "int"),
                    label="Deg",
                    width_cls="flex-1 min-w-0",
                )
                refs["min"] = _mk_input(
                    value=_fmt(_effective("minutes"), "int"),
                    label="Min",
                    width_cls="flex-1 min-w-0",
                )
                refs["sec"] = _mk_input(
                    value=_fmt(_effective("seconds"), "int"),
                    label="Sec",
                    width_cls="flex-1 min-w-0",
                )
                refs["dir"] = _mk_input(
                    value=_fmt(_effective("alignment"), "int"),
                    label="Align",
                    tooltip="Quadrant: 1=NE 2=NW 3=SW 4=SE",
                    width_cls="flex-1 min-w-0",
                )


def _render_plat_svg(container, sd, state: AppState | None = None) -> None:
    """Render the section as an inline SVG.

    What's drawn:
      * Fill polygon from the *walked* 16-segment boundary (so the
        polygon visibly opens when override lengths break closure).
      * 16 visible boundary segments (one per Grid Numbers cell) with
        short-code labels, each backed by a fat transparent hover hit
        zone so the segment is easy to mouse onto.
      * 8 corner dots (NW_SC, N_QC, NE_SC, E_QC, SE_SC, S_QC, SW_SC,
        W_QC) marking segment endpoints / quarter corners.
      * Red dashed line from walked endpoint → anchor when the walk
        does NOT close back to the start (override-driven mismatch).
      * The well's surface→bottom trajectory clipped to this view, when
        a processed survey is available on ``state``.
      * N / S / E / W compass labels.

    Hovering any segment line highlights both the segment and the
    matching ``#seg-cell-<KEY>`` card via JS installed in
    ``render_casing_review_tab`` head.
    """
    container.clear()
    try:
        walked = sd.walk_segment_endpoints()  # 16 segments
    except Exception as exc:
        with container:
            ui.label(f"Plat preview unavailable: {exc}").classes(
                "text-xs text-gray-500 p-2"
            )
        return
    if not walked:
        return

    # Build the open polyline (start + each segment end). Closure check
    # vs the original anchor: anything more than ~1 ft off is an "open
    # polygon" — visibly indicate it.
    anchor = walked[0][1]
    ring_pts = [anchor] + [seg[2] for seg in walked]
    end_pt = ring_pts[-1]
    closure_err = ((end_pt[0] - anchor[0]) ** 2 + (end_pt[1] - anchor[1]) ** 2) ** 0.5
    is_closed = closure_err < 1.0  # meters

    # ---- view box ----
    all_xs = [p[0] for p in ring_pts]
    all_ys = [p[1] for p in ring_pts]
    # Include wellpath bounds (if any) so it's not clipped.
    well_xy = _wellpath_xy_for_section(sd, state)
    if well_xy:
        all_xs += [x for x, _ in well_xy]
        all_ys += [y for _, y in well_xy]
    min_x, max_x = min(all_xs), max(all_xs)
    min_y, max_y = min(all_ys), max(all_ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    pad = 0.07 * max(span_x, span_y)
    vb_x, vb_y = min_x - pad, min_y - pad
    vb_w, vb_h = span_x + 2 * pad, span_y + 2 * pad

    def _flip(y: float) -> float:
        return (vb_y + vb_h) - (y - vb_y)

    # ---- polygon fill (from the walked ring; may be slightly open) ----
    fill_pts = " ".join(f"{x:.2f},{_flip(y):.2f}" for x, y in ring_pts)

    seg_elems = []
    hit_elems = []
    for key, (x1, y1), (x2, y2) in walked:
        # 1. Visible segment line (thin, neutral colour).
        seg_elems.append(
            f'<line class="seg-line" data-seg="{key}" '
            f'x1="{x1:.2f}" y1="{_flip(y1):.2f}" '
            f'x2="{x2:.2f}" y2="{_flip(y2):.2f}"/>'
        )
        # 2. Fat transparent hit zone *over* the visible line so the
        # mouseover hit area is generous even for thin walked lines.
        hit_elems.append(
            f'<line class="seg-line" data-seg="{key}" '
            f'x1="{x1:.2f}" y1="{_flip(y1):.2f}" '
            f'x2="{x2:.2f}" y2="{_flip(y2):.2f}" '
            f'style="stroke:transparent !important; stroke-width:18px !important;'
            f'pointer-events:stroke; vector-effect:non-scaling-stroke;">'
            f'<title>{key}</title></line>'
        )

    # ---- uniform segment endpoint dots (17 total — start + 16 ends) ----
    dot_r = max(vb_w, vb_h) * 0.011
    # SHL/BHL wellpath markers — a touch larger so they read above the
    # segment-endpoint dots.
    qc_r = max(vb_w, vb_h) * 0.014
    dot_elems = []
    for x, y in ring_pts:
        dot_elems.append(
            f'<circle cx="{x:.2f}" cy="{_flip(y):.2f}" r="{dot_r:.3f}" '
            f'fill="#0f172a" stroke="white" stroke-width="0.5" '
            f'style="vector-effect:non-scaling-stroke;"/>'
        )

    # ---- non-closure indicator ----
    closure_elem = ""
    if not is_closed:
        closure_elem = (
            f'<line x1="{end_pt[0]:.2f}" y1="{_flip(end_pt[1]):.2f}" '
            f'x2="{anchor[0]:.2f}" y2="{_flip(anchor[1]):.2f}" '
            f'stroke="#dc2626" stroke-width="2" stroke-dasharray="6,4" '
            f'style="vector-effect:non-scaling-stroke;">'
            f'<title>Walk gap: {closure_err * 3.28084:.1f} ft</title></line>'
        )

    # ---- wellpath ----
    well_elem = ""
    if well_xy and len(well_xy) >= 2:
        wp = " ".join(f"{x:.2f},{_flip(y):.2f}" for x, y in well_xy)
        sx, sy = well_xy[0]
        ex, ey = well_xy[-1]
        well_elem = (
            f'<polyline points="{wp}" fill="none" stroke="#16a34a" '
            f'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" '
            f'style="vector-effect:non-scaling-stroke;"/>'
            f'<circle cx="{sx:.2f}" cy="{_flip(sy):.2f}" r="{qc_r:.3f}" '
            f'fill="#16a34a" stroke="white" stroke-width="0.5" '
            f'style="vector-effect:non-scaling-stroke;">'
            f'<title>SHL</title></circle>'
            f'<circle cx="{ex:.2f}" cy="{_flip(ey):.2f}" r="{qc_r:.3f}" '
            f'fill="#dc2626" stroke="white" stroke-width="0.5" '
            f'style="vector-effect:non-scaling-stroke;">'
            f'<title>BHL</title></circle>'
        )

    # ---- compass labels ----
    n_y = vb_y + pad * 0.45
    s_y = vb_y + vb_h - pad * 0.15
    e_x = vb_x + vb_w - pad * 0.15
    w_x = vb_x + pad * 0.45
    cf = max(vb_w, vb_h) * 0.04

    svg = f"""
    <svg class="plat-svg" viewBox="{vb_x} {vb_y} {vb_w} {vb_h}"
         preserveAspectRatio="xMidYMid meet"
         style="width:100%; height:100%; display:block;
                user-select:none; -webkit-user-select:none;">
      <polygon points="{fill_pts}"
               fill="rgba(56,189,248,0.18)" stroke="none"/>
      {''.join(seg_elems)}
      {closure_elem}
      {''.join(dot_elems)}
      {well_elem}
      {''.join(hit_elems)}
      <text x="{(vb_x + vb_w / 2):.2f}" y="{n_y:.2f}"
            text-anchor="middle" font-size="{cf:.2f}"
            fill="#1e293b" font-weight="700">N</text>
      <text x="{(vb_x + vb_w / 2):.2f}" y="{s_y:.2f}"
            text-anchor="middle" font-size="{cf:.2f}"
            fill="#1e293b" font-weight="700">S</text>
      <text x="{e_x:.2f}" y="{(vb_y + vb_h / 2):.2f}"
            text-anchor="end" dominant-baseline="middle"
            font-size="{cf:.2f}" fill="#1e293b" font-weight="700">E</text>
      <text x="{w_x:.2f}" y="{(vb_y + vb_h / 2):.2f}"
            text-anchor="start" dominant-baseline="middle"
            font-size="{cf:.2f}" fill="#1e293b" font-weight="700">W</text>
    </svg>
    """
    closure_ft = closure_err * 3.28084
    if is_closed:
        closure_text = f"Closure: ✓ closed ({closure_ft:.2f} ft)"
        closure_cls = "text-xs text-emerald-700 font-medium"
    else:
        closure_text = f"Closure gap: {closure_ft:,.2f} ft"
        closure_cls = "text-xs text-red-700 font-semibold"

    with container:
        ui.html(svg).style("flex:1 1 auto; min-height:0;")
        ui.label(closure_text).classes(
            f"{closure_cls} mt-1 text-center w-full"
        )
        # Defer wiring to after the DOM is updated. The setTimeout(...,0)
        # gives Vue one tick to insert the SVG before we query for it.
        ui.run_javascript(_PLAT_RUNTIME_JS + "setTimeout(__etoolsWireAll, 0);")


def _wellpath_xy_for_section(sd, state) -> list[tuple[float, float]]:
    """Return (easting, northing) points in UTM-m for the well trajectory.

    Tries ``state.processed`` first (full processed survey from
    SurveyService); falls back to ``state.clearances`` (which already
    carries easting/northing columns) so the wellpath shows up even when
    the user has parsed an APD but not yet promoted it.
    """
    if state is None:
        return []
    try:
        # ---- preferred: state.processed (full processed survey) ----
        if getattr(state, "processed", None):
            from etools.models import SurveyFrame
            result = (
                state.processed.get("AsDrilled")
                or state.processed.get("Planned")
                or next(iter(state.processed.values()))
            )
            if result is not None:
                proc = (
                    result.frames.get(SurveyFrame.TRUE)
                    or next(iter(result.frames.values()))
                )
                df = proc.points
                if "easting" in df.columns and "northing" in df.columns and len(df) > 1:
                    step = max(1, len(df) // 600)
                    return [
                        (float(r.easting), float(r.northing))
                        for r in df.iloc[::step].itertuples()
                    ]
        # ---- fallback: state.clearances (post-clearance trajectory) ----
        if getattr(state, "clearances", None):
            cr = (
                state.clearances.get("AsDrilled")
                or state.clearances.get("Planned")
                or next(iter(state.clearances.values()))
            )
            df = getattr(cr, "points", None)
            if df is not None and "easting" in df.columns and "northing" in df.columns and len(df) > 1:
                step = max(1, len(df) // 600)
                return [
                    (float(r.easting), float(r.northing))
                    for r in df.iloc[::step].itertuples()
                ]
    except Exception as exc:
        log.warning("section_panel.wellpath.failed", error=str(exc))
    return []


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
    *,
    on_change,
) -> None:
    """Editable per-string inputs — one row per APD casing string, including
    Conductor. Edits mutate ``data.casing[*]`` and ``state.casing_overrides``,
    then trigger ``on_change`` which rebuilds the design table + WBD."""
    from etools.core.casing_review.engine import _TAG_TO_LABEL  # type: ignore

    card.clear()
    overrides = state.casing_overrides

    with card:
        ui.label("Casing string inputs (editable)").classes("text-sm font-semibold")
        ui.label(
            "Edit any cell — design table and WBD recompute when you tab away. "
            "Conductor is shown for reference but is not part of the engineering "
            "design (no washout / internal-gradient knobs)."
        ).classes("text-xs text-gray-600 mb-2")

        for apd in data.casing:
            mapping = _TAG_TO_LABEL.get(apd.tag)
            label_text = mapping[0] if mapping else apd.tag
            design_idx = mapping[1] if mapping else -1

            with ui.row().classes(
                "items-center gap-1 mt-1 flex-wrap p-2 rounded bg-slate-50"
            ):
                ui.label(label_text).classes("font-semibold w-24 text-xs")

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

                base_fields = [
                    ("hole",     apd.hole_size_in,       "hole_size_in",       False, float, "w-16"),
                    ("csg",      apd.casing_size_in,     "casing_size_in",     False, float, "w-16"),
                    ("set MD",   apd.length_bottom_ft,   "length_bottom_ft",   False, float, "w-20"),
                    ("wt",       apd.weight_ppf,         "weight_ppf",         False, float, "w-14"),
                    ("grade",    apd.grade,              "grade",              False, str,   "w-20"),
                    ("collar",   apd.collar,             "collar",             False, str,   "w-16"),
                    ("MW",       apd.max_mud_weight_ppg, "max_mud_weight_ppg", False, float, "w-14"),
                ]
                # Design-only override knobs only apply to engineered strings.
                # Pre-populate with the engine's defaults so the user sees the
                # value the engine will actually use (surface = 10%/0.12, deeper
                # = 4%/0.22) instead of a blank box.
                if design_idx >= 0:
                    ov = overrides.get(design_idx, {})
                    is_surface = design_idx == 0
                    washout_default = 10.0 if is_surface else 4.0
                    grad_default = 0.12 if is_surface else 0.22
                    washout_val = ov.get("hole_washout_pct", washout_default)
                    grad_val = ov.get("internal_gradient_psi_per_ft", grad_default)
                    base_fields += [
                        ("washout%", washout_val, "hole_washout_pct",            True, float, "w-16"),
                        ("int grad", grad_val,    "internal_gradient_psi_per_ft", True, float, "w-16"),
                    ]
                base_fields += [
                    ("lead sx",  apd.cement_lead_sacks,  "cement_lead_sacks",  False, int,   "w-16"),
                    ("lead yld", apd.cement_lead_yield,  "cement_lead_yield",  False, float, "w-16"),
                    ("tail sx",  apd.cement_tail_sacks,  "cement_tail_sacks",  False, int,   "w-16"),
                    ("tail yld", apd.cement_tail_yield,  "cement_tail_yield",  False, float, "w-16"),
                ]

                for label, value, attr, ovr, cast, width in base_fields:
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
