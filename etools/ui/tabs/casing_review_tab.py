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
from etools.core.casing_review.bope import BOPEOverrides, build_bope_review
from etools.core.casing_review.domain import CasingDesign
from etools.core.casing_review.engine import (
    CasingDesignEngine,
    _interpolate_tvd,
    welltrack_from_dataframe,
)
from etools.core.pdf.parser import parse_survey_pdf
from etools.logging_setup import get_logger
from etools.models import APDFormationTop, APDPdfData
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

  window.etoolsWireWellTips = function() {
    var tip = document.getElementById('etools-welltip');
    if (!tip) {
      tip = document.createElement('div');
      tip.id = 'etools-welltip';
      document.body.appendChild(tip);
    }
    document.querySelectorAll('circle.well-marker').forEach(function(el){
      if (el.__tipWired) return;
      el.__tipWired = true;
      var label = el.getAttribute('data-welltip') || '';
      function move(e){
        tip.style.left = (e.clientX + 14) + 'px';
        tip.style.top  = (e.clientY + 14) + 'px';
      }
      el.addEventListener('mouseenter', function(e){
        tip.textContent = label;
        tip.style.display = 'block';
        move(e);
      });
      el.addEventListener('mousemove', move);
      el.addEventListener('mouseleave', function(){ tip.style.display = 'none'; });
    });
  };

  window.__etoolsWireAll = function(){
    window.etoolsWireSegHover();
    window.etoolsWirePlatPanZoom();
    window.etoolsWireWellTips();
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
          #etools-welltip { position: fixed; z-index: 99999;
                            pointer-events: none; display: none;
                            background: #0f172a; color: #fff;
                            padding: 2px 8px; border-radius: 4px;
                            font-size: 12px; font-weight: 600;
                            white-space: nowrap;
                            box-shadow: 0 2px 6px rgba(0,0,0,.35); }
          /* BOPE tab — ui.html() strips inline <style>, so the BOPE review's
             styling lives here in the page head. */
          .bope-wrap { font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
            font-size: 12.5px; color: #1e293b; }
          .bope-title { font-weight: 800; font-size: 16px; letter-spacing: .03em;
            color: #0f172a; margin-bottom: 6px; }
          table.bope { border-collapse: separate; border-spacing: 0; width: auto;
            border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;
            box-shadow: 0 1px 2px rgba(15,23,42,.05); margin-bottom: 2px; }
          table.bope th, table.bope td { padding: 1px 8px; text-align: right;
            white-space: nowrap; border-bottom: 1px solid #eef2f7; line-height: 1.45; }
          table.bope tr:last-child td { border-bottom: none; }
          table.bope th { background: #0f172a; color: #fff; font-weight: 600;
            text-align: center; }
          table.bope th.h-item, table.bope th.h-f { text-align: left; }
          table.bope td.corner { background: #0f172a; }
          table.bope td.lbl { text-align: left; font-weight: 700; color: #0f172a;
            background: #f8fafc; }
          table.bope tr:nth-child(even) td { background: #fbfcfe; }
          table.bope tr:nth-child(even) td.lbl { background: #eef2f7; }
          table.bope td.f { text-align: left; color: #94a3b8; font-size: 11px;
            font-style: italic; }
          table.bope td.v { font-weight: 600; font-variant-numeric: tabular-nums; }
          table.bope td.chk { text-align: center; }
          .bope-red { color: #dc2626; font-weight: 800; }
          .bope-ovr { color: #b45309; font-weight: 800; }
          .opmax { display: inline-block; margin: 6px 0 2px; padding: 5px 11px;
            background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px;
            color: #1e3a8a; font-weight: 500; }
          .calc { width: fit-content; margin-top: 8px; border: 1px solid #e2e8f0;
            border-radius: 9px; overflow: hidden;
            box-shadow: 0 1px 3px rgba(15,23,42,.06); }
          .calchdr { background: linear-gradient(90deg,#1e293b,#334155); color: #fff;
            font-weight: 700; padding: 4px 12px; display: flex;
            justify-content: space-between; align-items: center; }
          .calcsz { font-weight: 500; font-size: 11.5px; color: #cbd5e1; }
          .calc table.bope { border: none; border-radius: 0; box-shadow: none; margin: 0; }
          .calcnote { font-size: 10.5px; color: #94a3b8; padding: 3px 12px;
            background: #f8fafc; }
          .pill { display: inline-block; padding: 1px 10px; border-radius: 999px;
            font-weight: 700; font-size: 11px; }
          .pill.yes { background: #dcfce7; color: #15803d; }
          .pill.no { background: #fee2e2; color: #b91c1c; }
          /* Printing a single tab is handled in _print_region(): it clones the
             target into an isolated iframe and prints that, so no page-level
             @media print rules are needed here. The .print-header carries the
             well name / API etc.; it is hidden on screen and revealed only
             inside the print iframe (see _print_region). */
          .print-header { display: none; }
        </style>
        """
    )

    # ``cache`` ONLY holds element refs for the current render. Persistent
    # data goes on ``state``. Anything stored here is gone after reconnect.
    cache: dict = {
        "meta_card": None,
        "inputs_card": None,
        "bope_card": None,
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
                cache["bope_tab"] = ui.tab("BOPE", icon="gpp_maybe")
                cache["design_tab"] = ui.tab("Computed design", icon="calculate")
                cache["sections_tab"] = ui.tab("Sections", icon="grid_on")
                cache["wbd_tab"] = ui.tab("WBD", icon="view_in_ar")
                cache["formations_tab"] = ui.tab("Formations", icon="layers")
                cache["result_tab"] = ui.tab("Output", icon="folder_open")
            with ui.tab_panels(cr_tabs, value=cache["meta_tab"]).classes("w-full"):
                with ui.tab_panel(cache["meta_tab"]) as p:
                    cache["meta_card"] = p
                with ui.tab_panel(cache["inputs_tab"]) as p:
                    cache["inputs_card"] = p
                with ui.tab_panel(cache["bope_tab"]) as p:
                    _print_button("print-target-bope", "BOPE")
                    cache["bope_card"] = ui.column().classes(
                        "w-full gap-0 print-target-bope"
                    )
                with ui.tab_panel(cache["design_tab"]) as p:
                    cache["design_card"] = p
                with ui.tab_panel(cache["sections_tab"]) as p:
                    cache["sections_card"] = p
                with ui.tab_panel(cache["wbd_tab"]) as p:
                    _print_button("print-target-wbd", "WBD")
                    cache["wbd_card"] = ui.column().classes(
                        "w-full gap-0 print-target-wbd"
                    )
                with ui.tab_panel(cache["formations_tab"]) as p:
                    cache["formations_card"] = p
                with ui.tab_panel(cache["result_tab"]) as p:
                    cache["result_card"] = p
        # Each tab button is hidden until its content has been rendered.
        for k in ("meta_tab", "inputs_tab", "bope_tab", "design_tab",
                  "sections_tab", "wbd_tab", "formations_tab", "result_tab"):
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

    async def generate() -> None:
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
        # Defensive: any failure here falls back to legacy section fill
        # (None) rather than aborting the whole generation silently.
        section_locations = None
        dx_survey_locations = None
        dx_survey_footages = None
        try:
            from etools.core.casing_review.sections import (
                apd_summary_footages,
                build_section_traversal,
                survey_kop_footages,
            )

            crossings = build_section_traversal(
                data.locations, _clearance_points(state)
            )
            section_locations = [c.to_location_row() for c in crossings] or None
            # Survey path offsets that drive the BHL sheets' native
            # section-detection — without them the BHL bearing grids stay
            # blank no matter what section sheets we write.
            dx_survey_locations = _dx_survey_locations(state)
            # The native walk that fills the Prod-Interval / Total-Depth
            # "Section Line Footages" is unreliable (blanks the FINAL footages
            # on cross-township wells). Write the APD-stated footages directly
            # so the bottom-hole footages always show and match the permit.
            footages = list(apd_summary_footages(data.locations) or [None, None, None])
            # Contingency: when the APD prints no "Location At Kickoff Point",
            # the KOP slot is empty — compute the K.O. Point footages from the
            # survey station at the (back-projected) kickoff MD instead.
            if footages and footages[0] is None:
                cp = _clearance_points(state)
                kop_md = None
                if state.processed:
                    sr = next(iter(state.processed.values()))
                    kop_md = getattr(getattr(sr, "kop", None), "md", None)
                if cp is not None and kop_md is not None:
                    footages[0] = survey_kop_footages(cp, kop_md)
            dx_survey_footages = footages if any(footages) else None
        except Exception:
            log.exception("casing_review.section_traversal_failed")
            ui.notify(
                "Could not build section traversal — generating with the "
                "basic 3-section layout.",
                type="warning",
            )
        # The Excel write (openpyxl serialising this large template) takes
        # ~20s. Run it off the UI thread so the app stays responsive and
        # show a spinner — otherwise the whole page freezes and looks broken.
        cache["gen_btn"].props("loading")
        cache["gen_status"].text = "Generating Casing Review… (saving the workbook takes ~20s)"
        try:
            result = await asyncio.to_thread(
                svc.generate,
                apd_data=data,
                survey=state.casing_survey_df,
                frac_gradient_override_psi_per_ft=frac,
                section_locations=section_locations or None,
                dx_survey_locations=dx_survey_locations or None,
                dx_survey_footages=dx_survey_footages or None,
                bope_overrides=_bope_overrides_from_state(state),
            )
        except Exception as exc:
            log.exception("casing_review.generate_failed")
            ui.notify(f"Generation failed: {exc}", type="negative")
            cache["gen_status"].text = "Generation failed — see logs."
            return
        finally:
            cache["gen_btn"].props(remove="loading")
        state.casing_last_output_path = result.output_path
        out = result.output_path
        cache["gen_status"].text = f"Saved {out.name}"
        _render_result(cache["result_card"], out, _serve_output_file(out))
        cache["result_tab"].visible = True
        ui.notify(f"Casing Review generated: {out.name} — opening…", type="positive")
        # Hand the finished workbook straight to Excel so the user doesn't
        # have to go find it. Fire-and-forget; the result card still offers
        # Open / Download if the shell launch doesn't take.
        _open_in_default_app(out)

    # ----------------------------------------------------------------------
    # Render helpers — all read from ``state`` so reconnects come up clean.
    # ----------------------------------------------------------------------
    def _hide_dynamic_cards() -> None:
        if cache.get("tabs_wrap") is not None:
            cache["tabs_wrap"].visible = False
        for k in ("meta_tab", "inputs_tab", "bope_tab", "design_tab",
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
        try:
            welltrack = (
                welltrack_from_dataframe(state.casing_survey_df)
                if state.casing_survey_df is not None
                else None
            )
            design = engine.build(data, welltrack=welltrack)
        except Exception as exc:
            log.exception("casing_review.design_build_failed", error=str(exc))
            card = cache.get("design_card")
            if card is not None:
                card.clear()
                with card:
                    ui.label(
                        f"Couldn't build the casing design: {type(exc).__name__}: {exc}"
                    ).classes("text-xs text-red-700 bg-red-50 p-2 rounded")
                if cache.get("design_tab") is not None:
                    cache["design_tab"].visible = True
            return
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
            _render_bope(cache["bope_card"], new_design, d, state)
            _render_design(cache["design_card"], new_design)
            _render_wbd(cache["wbd_card"], new_design, d)

        # Render each card in isolation: a failure in one (bad survey data,
        # a template edge case, …) must not blank the whole tab. The failing
        # card shows its error inline and the others still populate.
        def _safe(card_key: str, tab_key: str, render):
            card = cache.get(card_key)
            if card is None:
                return
            try:
                render(card)
            except Exception as exc:  # pragma: no cover - defensive UI guard
                log.exception("casing_review.render_failed", card=card_key, error=str(exc))
                try:
                    card.clear()
                    with card:
                        ui.label(
                            f"Couldn't render this section: {type(exc).__name__}: {exc}"
                        ).classes("text-xs text-red-700 bg-red-50 p-2 rounded")
                except Exception:
                    pass
            tab = cache.get(tab_key)
            if tab is not None:
                tab.visible = True

        _safe("inputs_card", "inputs_tab",
              lambda c: _render_inputs(c, data, state, on_change=_recompute_downstream))
        _safe("bope_card", "bope_tab", lambda c: _render_bope(c, design, data, state))
        _safe("design_card", "design_tab", lambda c: _render_design(c, design))
        _safe("sections_card", "sections_tab", lambda c: _render_sections(c, data, state))
        _safe("wbd_card", "wbd_tab", lambda c: _render_wbd(c, design, data))
        # Formations only affect the WBD's dashed markers — never the casing
        # design — so an edit re-renders just that one card, and a failure
        # there is swallowed rather than allowed to break the tab.
        def _formations_changed() -> None:
            try:
                _render_wbd(cache["wbd_card"], design, data)
            except Exception as exc:  # pragma: no cover - defensive UI guard
                log.exception("casing_review.wbd_refresh_failed", error=str(exc))

        _safe(
            "formations_card", "formations_tab",
            lambda c: _render_formations(c, data, state, on_change=_formations_changed),
        )

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


def _print_button(target_class: str, label: str) -> None:
    """A 'Print <label>' button that prints just its tab's content, like a
    screenshot. Placed OUTSIDE the print-target container (marked ``no-print``)
    so the button itself never appears in the output."""
    ui.button(
        f"Print {label}", icon="print",
        on_click=lambda: _print_region(target_class),
    ).props("outline size=sm").classes("no-print mb-2")


def _print_header(data: APDPdfData | None, title: str) -> None:
    """A well-identification banner (well name, API, operator, …) placed at the
    top of a printable card. Hidden on screen via ``.print-header``; the print
    iframe (see ``_print_region``) reveals it so every printout is labeled with
    which well it belongs to."""
    well = (getattr(data, "well_name", None) or "—") if data is not None else "—"
    api = (getattr(data, "api", None) or "—") if data is not None else "—"
    meta_bits = []
    if data is not None:
        for val in (
            getattr(data, "operator", None),
            getattr(data, "field_name", None),
            getattr(data, "county", None) and f"{data.county} County",
        ):
            if val:
                meta_bits.append(str(val))
    sub = "  ·  ".join(meta_bits)
    html = (
        "<div class='print-header' style=\"font-family:system-ui,-apple-system,"
        "'Segoe UI',sans-serif;margin:0 0 12px;padding:0 0 8px;"
        "border-bottom:2px solid #0f172a;\">"
        f"<div style='font-size:18px;font-weight:800;color:#0f172a'>{_esc(well)}</div>"
        f"<div style='font-size:12.5px;color:#334155;margin-top:2px'>"
        f"API {_esc(api)}" + (f"  ·  {_esc(sub)}" if sub else "") + "</div>"
        f"<div style='font-size:11px;color:#64748b;font-weight:600;"
        f"letter-spacing:.04em;margin-top:3px'>{_esc(title.upper())}</div>"
        "</div>"
    )
    ui.html(html)


def _esc(value) -> str:
    """Minimal HTML-escape for values interpolated into a print header."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _print_region(target_class: str) -> None:
    """Print just the element carrying ``target_class``, like a screenshot.

    The earlier ``@media print`` + ``visibility:hidden`` trick is unreliable
    inside NiceGUI's Quasar layout: positioned / ``overflow``-clipped /
    ``transform``ed ancestors clip the absolutely-positioned region, and a
    Plotly SVG (the WBD) does not reflow under print media — so nothing (or a
    blank page) came out.

    Instead we clone the target's markup plus every page stylesheet into a
    hidden, isolated iframe and print *that*. The iframe is its own document
    with no Quasar ancestors, so what you see is exactly what prints. Works
    for both the styled BOPE HTML and the rendered Plotly SVG."""
    js = (
        "(function(){"
        f"var el=document.querySelector('.{target_class}');"
        "if(!el){return;}"
        # Carry over <style> blocks + linked stylesheets so the clone is styled.
        "var head='';"
        "document.querySelectorAll('style, link[rel=\"stylesheet\"]')"
        ".forEach(function(n){head+=n.outerHTML;});"
        "var f=document.createElement('iframe');"
        "f.setAttribute('aria-hidden','true');"
        "f.style.cssText='position:fixed;right:0;bottom:0;width:0;height:0;border:0;';"
        "document.body.appendChild(f);"
        "var doc=f.contentWindow.document;"
        "doc.open();"
        "doc.write('<!DOCTYPE html><html><head>'+head+"
        "'<style>@page{margin:12mm;}body{margin:0;}"
        ".no-print{display:none!important;}.modebar{display:none!important;}"
        ".print-header{display:block!important;}</style>"
        "</head><body>'+el.outerHTML+'</body></html>');"
        "doc.close();"
        "var printed=false;"
        "function go(){"
        "if(printed){return;}printed=true;"
        "try{f.contentWindow.focus();f.contentWindow.print();}catch(e){}"
        "setTimeout(function(){f.remove();},1000);}"
        # Print once the clone has settled; fall back if onload already fired.
        "f.onload=function(){setTimeout(go,200);};"
        "setTimeout(go,500);"
        "})();"
    )
    ui.run_javascript(js)


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


def _formation_md_cap(data: APDPdfData, welltrack) -> tuple[float, str] | None:
    """Upper bound for a hand-entered formation MD: 110% of the survey's final
    MD, falling back to 110% of the APD's proposed MD when no survey is
    loaded. ``None`` when neither is known (no bound can be enforced)."""
    if welltrack:
        return welltrack[-1].md_ft * 1.10, "the survey's final MD"
    if data.proposed_md_ft:
        return data.proposed_md_ft * 1.10, "the APD's proposed MD"
    return None


def _validate_formation_md(
    md_val: float, data: APDPdfData, welltrack
) -> str | None:
    """Return an error message for an out-of-range formation MD, else None."""
    if md_val < 0:
        return "Top MD can't be negative."
    cap = _formation_md_cap(data, welltrack)
    if cap is not None and md_val > cap[0]:
        return (
            f"Top MD can't exceed 110% of {cap[1]} ({cap[0]:,.0f} ft)."
        )
    return None


def _render_formations(
    card: ui.card,
    data: APDPdfData,
    state: AppState | None = None,
    *,
    on_change: Callable[[], None] | None = None,
) -> None:
    """Formation tops extracted from the APD (Section 6 / page-2 table),
    shown as a standalone tab and editable by hand.

    Rows always stay sorted by Top MD. Editing a row's Top MD recomputes its
    Top TVD by interpolating along the loaded directional survey (left manual
    when no survey is loaded). Entered MDs are bounded: no negatives, and no
    deeper than 110% of the survey's final MD. The list drives the dashed
    markers on the WBD figure.
    """
    card.clear()

    def _welltrack():
        if state is None or state.casing_survey_df is None:
            return []
        try:
            return welltrack_from_dataframe(state.casing_survey_df)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            log.exception("casing_review.formations_welltrack_failed", error=str(exc))
            return []

    def _changed() -> None:
        data.formations.sort(
            key=lambda f: f.md_ft if f.md_ft is not None else float("inf")
        )
        body.refresh()
        if on_change is not None:
            on_change()

    with card:
        ui.label("Formation tops").classes("text-sm font-semibold")
        ui.label(
            "Geological formation tops parsed from the APD, or added by hand "
            "below. Rows sort by Top MD automatically; editing Top MD "
            "recomputes Top TVD from the loaded survey. These also appear as "
            "dashed markers on the Vertical Wellbore Diagram."
        ).classes("text-xs text-gray-600 mb-2")

        @ui.refreshable
        def body() -> None:
            wt = _welltrack()
            ui.label(f"{len(data.formations)} formation top(s)").classes(
                "text-sm font-semibold mt-1 text-gray-700"
            )
            cap = _formation_md_cap(data, wt)
            if not wt:
                ui.label(
                    "No directional survey loaded — Top TVD won't "
                    "auto-recalculate from Top MD. Enter it by hand if needed."
                ).classes("text-xs text-amber-800 bg-amber-50 p-1 rounded mb-1")
            if cap is not None:
                ui.label(
                    f"Top MD must be between 0 and {cap[0]:,.0f} ft "
                    f"(110% of {cap[1]})."
                ).classes("text-xs text-gray-500 mb-1")

            if not data.formations:
                ui.label(
                    "No formation tops yet — add one below."
                ).classes("text-xs p-2 rounded bg-slate-100 text-slate-700")
                return

            for i, f in enumerate(data.formations):
                with ui.row().classes(
                    "items-center gap-1 flex-wrap p-1 rounded"
                    + (" bg-slate-50" if i % 2 == 0 else "")
                ):
                    ui.label(f"{i + 1}").classes("w-6 text-xs text-gray-500")

                    def _name_handler(fm=f):
                        def handler(e) -> None:
                            val = (e.sender.value or "").strip()
                            if val and val != fm.name:
                                fm.name = val
                                _changed()
                        return handler

                    (
                        ui.input(value=f.name)
                        .props("dense outlined")
                        .classes("w-48")
                        .on("blur", _name_handler())
                        .on("keydown.enter", _name_handler())
                    )

                    def _md_handler(fm=f):
                        def handler(e) -> None:
                            val = _parse_optional(e.sender.value, cast=float)
                            if val is None or val == fm.md_ft:
                                return
                            track = _welltrack()
                            err = _validate_formation_md(val, data, track)
                            if err:
                                ui.notify(err, type="warning")
                                e.sender.value = (
                                    "" if fm.md_ft is None else f"{fm.md_ft:g}"
                                )
                                return
                            fm.md_ft = val
                            if track:
                                fm.tvd_ft = _interpolate_tvd(track, val)
                            _changed()
                        return handler

                    ui.label("MD").classes("text-xs text-gray-500")
                    (
                        ui.input(value="" if f.md_ft is None else f"{f.md_ft:g}")
                        .props("dense outlined suffix=ft")
                        .classes("w-28")
                        .on("blur", _md_handler())
                        .on("keydown.enter", _md_handler())
                    )

                    def _tvd_handler(fm=f):
                        def handler(e) -> None:
                            fm.tvd_ft = _parse_optional(e.sender.value, cast=float)
                            _changed()
                        return handler

                    ui.label("TVD").classes("text-xs text-gray-500")
                    (
                        ui.input(value="" if f.tvd_ft is None else f"{f.tvd_ft:g}")
                        .props("dense outlined suffix=ft")
                        .classes("w-28")
                        .on("blur", _tvd_handler())
                        .on("keydown.enter", _tvd_handler())
                    )

                    def _delete_handler(fm=f):
                        def handler() -> None:
                            if fm in data.formations:
                                data.formations.remove(fm)
                            _changed()
                        return handler

                    ui.button(icon="delete", on_click=_delete_handler()).props(
                        "flat dense round color=red size=sm"
                    )

        body()

        ui.separator().classes("my-2")
        ui.label("Add a formation top").classes("text-xs font-semibold text-gray-700")
        with ui.row().classes("items-center gap-1 flex-wrap"):
            name_in = (
                ui.input(placeholder="Formation name")
                .props("dense outlined")
                .classes("w-48")
            )
            md_in = (
                ui.input(placeholder="Top MD (ft)")
                .props("dense outlined suffix=ft")
                .classes("w-28")
            )

            def _add() -> None:
                nm = (name_in.value or "").strip()
                md_val = _parse_optional(md_in.value, cast=float)
                if not nm or md_val is None:
                    ui.notify("Enter a name and a Top MD.", type="warning")
                    return
                track = _welltrack()
                err = _validate_formation_md(md_val, data, track)
                if err:
                    ui.notify(err, type="warning")
                    return
                data.formations.append(
                    APDFormationTop(
                        name=nm,
                        md_ft=md_val,
                        tvd_ft=_interpolate_tvd(track, md_val) if track else None,
                    )
                )
                name_in.value = ""
                md_in.value = ""
                _changed()

            ui.button("Add", icon="add", on_click=_add).props("color=primary dense")


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


_BOPE_INPUT_ROWS = (
    ("Casing Size (\")", "od_in", 3),
    ("Setting Depth (TVD)", "setting_depth_tvd_ft", 0),
    ("Previous Shoe Setting Depth (TVD)", "prev_shoe_tvd_ft", 0),
    ("Max Mud Weight (ppg)", "mud_weight_ppg", 1),
    ("Casing Internal Yield (psi)", "internal_yield_psi", 0),
)


def _bope_num(v, nd: int) -> str:
    if v is None:
        return ""
    try:
        return f"{float(v):,.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def _yesno(flag) -> str:
    if flag is None:
        return ""
    return '<span class="pill yes">YES</span>' if flag else '<span class="pill no">NO</span>'


def _bope_html(review) -> str:
    rows = review.strings
    th = "".join(f"<th>{r.label}</th>" for r in rows)

    # ---- Header input block (one column per string) ----
    body = [f"<tr><td class=corner></td>{th}</tr>"]
    for label, attr, nd in _BOPE_INPUT_ROWS:
        cells = []
        for r in rows:
            txt = _bope_num(getattr(r, attr), nd)
            # User-edited previous-shoe depths get the override style.
            if attr == "prev_shoe_tvd_ft" and r.prev_shoe_overridden and txt:
                txt = f'<span class="bope-ovr">{txt} ✎</span>'
            cells.append(f"<td class=v>{txt}</td>")
        body.append(f"<tr><td class=lbl>{label}</td>{''.join(cells)}</tr>")
    # BOPE Proposed — user-edited values marked ✎, inferred shown bold red,
    # permit-stated plain.
    prop_cells = []
    for r in rows:
        txt = _bope_num(r.bope_proposed_psi, 0)
        if txt and r.bope_proposed_overridden:
            txt = f'<span class="bope-ovr">{txt} ✎</span>'
        elif txt and not r.bope_proposed_from_pdf:
            txt = f'<span class="bope-red">{txt}</span>'
        prop_cells.append(f"<td class=v>{txt}</td>")
    body.append(f"<tr><td class=lbl>BOPE Proposed (psi)</td>{''.join(prop_cells)}</tr>")
    hdr_table = f"<table class=bope>{''.join(body)}</table>"

    op = review.operators_max_anticipated_pressure_psi
    eq = review.equivalent_mud_weight_ppg
    op_line = ""
    if op is not None:
        eq_txt = f" &nbsp;·&nbsp; = {eq:,.1f} ppg equivalent" if eq is not None else ""
        ovr_txt = ' <span class="bope-ovr">✎</span>' if review.op_max_overridden else ""
        op_line = (
            f"<div class=opmax>Operators Max Anticipated Pressure&nbsp;&nbsp;"
            f"<b>{op:,.0f} psi</b>{ovr_txt}{eq_txt}</div>"
        )

    # ---- Per-string Calculations blocks ----
    calcs = []
    for r in rows:
        sz = _bope_num(r.od_in, 3)
        crows = [
            f'<tr><td class=lbl>Max BHP [psi]</td><td class=f>.052 · Setting Depth · MW</td>'
            f'<td class=v>{_bope_num(r.max_bhp_psi, 0)}</td><td class=chk></td></tr>',
            f'<tr><td class=lbl>MASP (Gas) [psi]</td><td class=f>Max BHP − 0.12 · Setting Depth</td>'
            f'<td class=v>{_bope_num(r.masp_gas_psi, 0)}</td><td class=chk>{_yesno(r.adequate_gas)}</td></tr>',
            f'<tr><td class=lbl>MASP (Gas/Mud) [psi]</td><td class=f>Max BHP − 0.22 · Setting Depth</td>'
            f'<td class=v>{_bope_num(r.masp_gas_mud_psi, 0)}</td><td class=chk>{_yesno(r.adequate_gas_mud)}</td></tr>',
            f'<tr><td class=lbl>Pressure At Previous Shoe</td>'
            f'<td class=f>Max BHP − 0.22 · (Setting Depth − Prev Shoe)</td>'
            f'<td class=v>{_bope_num(r.pressure_at_prev_shoe_psi, 0)}</td>'
            f'<td class=chk>{_yesno(r.hold_full_at_prev_shoe)}</td></tr>',
            f'<tr><td class=lbl>Required Casing/BOPE Test Pressure</td><td class=f>psi</td>'
            f'<td class=v>{_bope_num(r.required_test_pressure_psi, 0)}</td><td class=chk></td></tr>',
            f'<tr><td class=lbl>*Max Pressure Allowed @ Previous Casing Shoe</td>'
            f'<td class=f>psi · assumes 1 psi/ft frac gradient</td>'
            f'<td class=v>{_bope_num(r.max_pressure_allowed_prev_shoe_psi, 0)}</td><td class=chk></td></tr>',
        ]
        calcs.append(
            f"<div class=calc><div class=calchdr>{r.label}"
            f'<span class=calcsz>{sz}" casing</span></div>'
            f'<table class=bope>'
            f'<tr><th class=h-item>Calculation</th><th class=h-f>Formula</th>'
            f'<th class=h-v>Value</th><th class=h-chk>Check</th></tr>'
            f"{''.join(crows)}</table>"
            f'<div class=calcnote>Check column: "Adequate for drilling &amp; setting '
            f'casing at depth?" (MASP rows) and "Can full expected pressure be held '
            f'at previous shoe?" (Pressure At Previous Shoe).</div></div>'
        )

    # NOTE: the CSS for these classes lives in the page <head> (added via
    # ui.add_head_html in render_casing_review_tab) because ui.html() strips
    # inline <style> blocks. Don't add a <style> here — it won't render.
    return (
        f'<div class=bope-wrap><div class=bope-title>BOPE REVIEW</div>'
        f'{hdr_table}{op_line}{"".join(calcs)}</div>'
    )


def _bope_overrides_from_state(state: AppState | None) -> BOPEOverrides:
    """Build a ``BOPEOverrides`` from the loosely-typed dict on AppState."""
    raw = (getattr(state, "bope_overrides", None) or {}) if state is not None else {}
    return BOPEOverrides(
        prev_shoe_tvd_ft=dict(raw.get("prev_shoe", {})),
        bope_proposed_psi=dict(raw.get("proposed", {})),
        op_max_pressure_psi=raw.get("op_max"),
    )


def _render_bope(
    card: ui.card,
    design: CasingDesign,
    data: APDPdfData | None = None,
    state: AppState | None = None,
) -> None:
    card.clear()
    psi = getattr(data, "bope_system_psi", None) if data is not None else None
    # Defaults with NO overrides applied — these are the placeholder values
    # the editor shows so the user always sees what "blank" falls back to.
    base = build_bope_review(design, bope_system_psi=psi)

    with card:
        _print_header(data, "BOPE Review")
        # ---- Editable inputs (rendered once — edits only redraw the
        # results box below, so the input firing the event survives). ----
        if state is not None:
            _render_bope_editor(state, base, on_change=lambda: _redraw())

        results_box = ui.column().classes("w-full gap-0")

        def _redraw() -> None:
            review = build_bope_review(
                design,
                bope_system_psi=psi,
                overrides=_bope_overrides_from_state(state),
            )
            results_box.clear()
            with results_box:
                ui.html(_bope_html(review)).classes("w-full")
                legend = (
                    "BOPE Proposed shown in <b>bold red</b> is inferred (smallest "
                    "standard 2M/3M/5M/10M/15M rating above the gas MASP); plain "
                    "values come straight from the permit; "
                    '<span class="bope-ovr">✎</span> marks your edits.'
                )
                if psi is not None:
                    legend += f" Permit states a {psi:,.0f} psi BOP system."
                ui.html(
                    f'<div style="font-size:11px;color:#64748b;margin-top:6px">{legend}</div>'
                )

        _redraw()


def _render_bope_editor(state: AppState, base, *, on_change) -> None:
    """Per-string Previous-Shoe / BOPE-Proposed inputs + the Operators Max
    Anticipated Pressure input. Blank = use the computed value (shown as the
    placeholder). Edits land in ``state.bope_overrides`` and cascade through
    every recomputed BOPE number here and in the generated workbook."""
    ov = state.bope_overrides

    def _on_edit(group: str, idx: int | None = None):
        def handler(e) -> None:
            val = _parse_optional(e.sender.value, cast=float)
            if group == "op_max":
                if val is None:
                    ov.pop("op_max", None)
                else:
                    ov["op_max"] = val
            else:
                d = ov.setdefault(group, {})
                if val is None:
                    d.pop(idx, None)
                else:
                    d[idx] = val
                if not d:
                    ov.pop(group, None)
            on_change()
        return handler

    def _num_input(value, placeholder, handler, width: str = "w-28"):
        inp = (
            ui.input(value="" if value is None else f"{value:g}")
            .props(f'dense outlined placeholder="{placeholder}"')
            .classes(width)
        )
        inp.on("blur", handler)
        inp.on("keydown.enter", handler)

    ui.label("BOPE inputs (editable)").classes("text-sm font-semibold")
    ui.label(
        "Type to override the computed value; blank a box to revert. Every "
        "BOPE calculation below — and the BOPE sheet of the generated "
        "workbook — recomputes from what you enter."
    ).classes("text-xs text-gray-600 mb-1")

    for idx, r in enumerate(base.strings):
        with ui.row().classes("items-center gap-1 flex-wrap p-2 rounded bg-slate-50"):
            ui.label(r.label).classes("font-semibold w-24 text-xs")
            ui.label("prev shoe TVD (ft)").classes("text-xs text-gray-500")
            _num_input(
                ov.get("prev_shoe", {}).get(idx),
                _bope_num(r.prev_shoe_tvd_ft, 0),
                _on_edit("prev_shoe", idx),
            )
            ui.label("BOPE proposed (psi)").classes("text-xs text-gray-500")
            _num_input(
                ov.get("proposed", {}).get(idx),
                _bope_num(r.bope_proposed_psi, 0),
                _on_edit("proposed", idx),
            )
    with ui.row().classes("items-center gap-1 flex-wrap p-2 rounded bg-slate-50"):
        ui.label("Operators Max").classes("font-semibold w-24 text-xs")
        ui.label("anticipated pressure (psi)").classes("text-xs text-gray-500")
        _num_input(
            ov.get("op_max"),
            _bope_num(base.operators_max_anticipated_pressure_psi, 0),
            _on_edit("op_max"),
        )


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


def _dx_survey_locations(state: AppState):
    """KOP / Prod-Interval / Total-Depth path offsets for the DxSurvey block.

    Feeds :func:`dx_survey_path_offsets` the clearance points (which carry
    ``measured_depth`` / ``n_offset`` / ``e_offset``) plus the KOP / landing
    MDs detected during survey processing. Returns ``None`` when no survey
    is loaded so the writer falls back to the template defaults.
    """
    from etools.core.casing_review.sections import dx_survey_path_offsets

    points = _clearance_points(state)
    if points is None:
        return None
    kop_md = landing_md = None
    if state.processed:
        sr = next(iter(state.processed.values()))
        kop_md = getattr(getattr(sr, "kop", None), "md", None)
        landing_md = getattr(sr, "landing_md", None)
    # The APD's stated kickoff (when the permit prints "KOP: <md>' MD") is
    # authoritative — prefer it over the survey-detected KOP so the K.O. Point
    # row reflects the document, not a statistical estimate.
    doc_kop = getattr(state.apd_data, "kop_md_ft", None)
    if doc_kop is not None:
        kop_md = doc_kop
    rows = dx_survey_path_offsets(points, kop_md=kop_md, landing_md=landing_md)
    return rows or None


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
    dot_r = max(vb_w, vb_h) * 0.006
    # SHL/KOP/Landing/BHL wellpath markers — larger so they read clearly
    # above the small segment-endpoint dots.
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
        # Intermediate reference markers (KOP / Landing) along the path, each
        # with a hover <title> tooltip naming it. SHL/BHL are the endpoints.
        # ``data-welltip`` drives an instant JS tooltip (the native SVG
        # <title> has an un-tunable hover delay), wired by etoolsWireWellTips.
        marker_circles = ""
        for mx, my, label in _wellpath_markers(state):
            marker_circles += (
                f'<circle class="well-marker" cx="{mx:.2f}" cy="{_flip(my):.2f}" '
                f'r="{qc_r:.3f}" fill="#2563eb" stroke="white" stroke-width="0.5" '
                f'data-welltip="{label}" '
                f'style="vector-effect:non-scaling-stroke; cursor:pointer;"></circle>'
            )
        well_elem = (
            f'<polyline points="{wp}" fill="none" stroke="#16a34a" '
            f'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" '
            f'style="vector-effect:non-scaling-stroke; pointer-events:none;"/>'
            f'<circle class="well-marker" cx="{sx:.2f}" cy="{_flip(sy):.2f}" '
            f'r="{qc_r:.3f}" fill="#16a34a" stroke="white" stroke-width="0.5" '
            f'data-welltip="SHL (Surface)" '
            f'style="vector-effect:non-scaling-stroke; cursor:pointer;"></circle>'
            f'{marker_circles}'
            f'<circle class="well-marker" cx="{ex:.2f}" cy="{_flip(ey):.2f}" '
            f'r="{qc_r:.3f}" fill="#dc2626" stroke="white" stroke-width="0.5" '
            f'data-welltip="BHL (Total Depth)" '
            f'style="vector-effect:non-scaling-stroke; cursor:pointer;"></circle>'
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
      {''.join(hit_elems)}
      {well_elem}
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


def _wellpath_markers(state) -> list[tuple[float, float, str]]:
    """(easting, northing, label) for the named wellpath reference points to
    mark + label on the section graphic: K.O. Point and Prod. Interval
    (Landing). SHL and BHL are the trajectory endpoints, marked separately.

    Positions are interpolated from the processed survey at the KOP / landing
    MDs (preferring the APD's stated kickoff, to match the rest of the tool).
    Returns ``[]`` when there's no processed survey.
    """
    if state is None or not getattr(state, "processed", None):
        return []
    try:
        from etools.models import SurveyFrame

        result = (
            state.processed.get("AsDrilled")
            or state.processed.get("Planned")
            or next(iter(state.processed.values()))
        )
        if result is None:
            return []
        proc = (
            result.frames.get(SurveyFrame.TRUE)
            or next(iter(result.frames.values()))
        )
        df = proc.points
        if not {"easting", "northing", "measured_depth"} <= set(df.columns):
            return []
        kop_md = getattr(getattr(result, "kop", None), "md", None)
        doc_kop = getattr(getattr(state, "apd_data", None), "kop_md_ft", None)
        if doc_kop is not None:
            kop_md = doc_kop
        landing_md = getattr(result, "landing_md", None)
        out: list[tuple[float, float, str]] = []
        for md, label in ((kop_md, "K.O. Point"), (landing_md, "Prod. Interval")):
            if md is None:
                continue
            idx = (df["measured_depth"] - float(md)).abs().idxmin()
            row = df.loc[idx]
            out.append((float(row["easting"]), float(row["northing"]), label))
        return out
    except Exception as exc:
        log.warning("section_panel.markers.failed", error=str(exc))
        return []


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
        _print_header(data, "Vertical Wellbore Diagram")
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


def _open_in_default_app(path: Path) -> None:
    """Open ``path`` with the OS's default application (Excel for .xlsx).

    ETools runs as a local app — the server process is on the same machine as
    the browser — so launching the file server-side opens it on the user's own
    desktop. Mirrors ``etools.main._open_in_default_browser``: the Windows
    shell (``os.startfile``) respects the registered default handler.

    Best-effort and off the event loop: launching Excel can block for a
    moment, and a failure here must never break generation — the workbook is
    already saved and the Download button still works.
    """
    import os
    import subprocess
    import sys
    import threading

    def _go() -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # noqa: S606 — shell call to default handler
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:  # pragma: no cover - defensive, OS-dependent
            # Nested guard: logging itself can raise (e.g. UnicodeEncodeError
            # when the console codec can't render the message). Nothing here
            # is worth killing the thread — or spraying a traceback — over.
            try:
                log.exception("casing_review.open_output_failed", path=str(path))
            except Exception:
                pass

    threading.Thread(target=_go, daemon=True).start()


def _render_result(card: ui.card, path: Path, download_url: str) -> None:
    card.clear()
    with card:
        with ui.row().classes("items-center gap-3 w-full"):
            ui.label("Generated Casing Review").classes("text-sm font-semibold flex-1")
            ui.button(
                "Open in Excel",
                icon="open_in_new",
                on_click=lambda: _open_in_default_app(path),
            ).props("flat dense")
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
