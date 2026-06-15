"""Survey tab — citing/frame controls, raw + processed grids, KOP/landing markers.

Survey editing: MD / inclination / azimuth cells are editable in the grid,
stations can be added at an interpolated MD or deleted, the SHL and the
convergence angle can be overridden. Every edit mutates the raw survey
(``state.surveys``) or an override field and re-runs ``state.post_load`` —
the same pipeline a fresh load uses — so TVD, KOP, clearances, the map,
and the WCR all cascade from the edited values. "Restore original survey"
reverts everything.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd
from nicegui import ui

from etools.core.coordinates import dms_to_decimal, utm_to_latlon
from etools.core.survey import lookup_magnetic_field
from etools.core.survey.edits import (
    delete_station,
    displayed_to_native_azimuth,
    insert_station,
    interpolate_raw_station,
    update_station,
)
from etools.logging_setup import get_logger
from etools.models import SurveyFrame
from etools.services import SurveyService
from etools.ui.state import AppState

log = get_logger(__name__)

_FRAME_LABELS = {SurveyFrame.TRUE: "True North", SurveyFrame.GRID: "Grid North"}

_MD_FIELDS = ("measured_depth", "MeasuredDepth")
_INC_FIELDS = ("inclination", "Inclination")
_AZI_FIELDS = ("azimuth", "Azimuth")
_EDITABLE_FIELDS = set(_MD_FIELDS) | set(_INC_FIELDS) | set(_AZI_FIELDS)


def render_survey_tab(state: AppState) -> Callable[[], None]:
    """Returns a refresh callback the parent invokes after a well loads."""
    survey_service = SurveyService()
    selected_frame: dict[str, SurveyFrame] = {"value": SurveyFrame.TRUE}

    with ui.column().classes("p-4 gap-3 w-full"):
        header_label = ui.label("Load a well first.").classes("text-gray-500 italic")

        controls = ui.row().classes("gap-3 items-center")
        with controls:
            ui.label("Citing:").classes("text-sm")
            citing_select = (
                ui.select(options=[], on_change=lambda _: rerender())
                .props("dense outlined")
                .classes("w-44")
            )
            ui.label("Frame:").classes("text-sm")

            def _on_frame_change(e) -> None:
                try:
                    log.info("survey.frame.change", new_value=e.value)
                    selected_frame["value"] = SurveyFrame(e.value)
                    rerender()
                except Exception as exc:
                    log.exception("survey.frame.change.failed", error=str(exc))
                    ui.notify(
                        f"Failed to switch frame: {exc}",
                        type="negative",
                        multi_line=True,
                        timeout=8000,
                    )

            frame_toggle = ui.toggle(
                {SurveyFrame.TRUE.value: "True", SurveyFrame.GRID.value: "Grid"},
                value=SurveyFrame.TRUE.value,
                on_change=_on_frame_change,
            ).props("dense")
            ui.button(
                "Process Survey", icon="memory", on_click=lambda: process()
            ).props("color=primary")
            point_count = ui.label("").classes("text-sm text-gray-500 ml-4")
        controls.set_visibility(False)

        kop_card = ui.row().classes("gap-4 hidden")
        with kop_card:
            kop_md_label = ui.label("KOP: —").classes("text-sm")
            landing_md_label = ui.label("Landing: —").classes("text-sm")
            method_label = ui.label("").classes("text-xs text-gray-500")

        # --- Edit tools. Every action below cascades through post_load. ---
        tools_row = ui.row().classes("gap-2 items-center flex-wrap")
        with tools_row:
            interp_md_input = ui.input("MD (ft)", placeholder="7765").props(
                "dense outlined"
            ).classes("w-32")
            ui.button(
                "Interpolate + Add", icon="add_circle", on_click=lambda: interpolate()
            ).props("outline").tooltip(
                "Interpolate INC/AZI at this MD and insert the station into the survey"
            )
            interp_result = ui.label("").classes("text-sm font-mono")
            ui.label("·").classes("text-gray-400 mx-2")
            shl_lat_input = ui.input(
                "New SHL — Lat / Easting", placeholder="40.2701 or 555200"
            ).props("dense outlined").classes("w-48 font-mono")
            shl_lon_input = ui.input(
                "New SHL — Lon / Northing", placeholder="-110.3502 or 4458447"
            ).props("dense outlined").classes("w-48 font-mono")
            ui.button(
                "Reprocess with new SHL", icon="edit_location_alt", on_click=lambda: reprocess_shl()
            ).props("outline").tooltip(
                "Re-run the whole pipeline with the surface hole moved here. Takes "
                "decimal lat/lon, deg min sec, or UTM 12N metres."
            )
        tools_row.set_visibility(False)

        edit_row = ui.row().classes("gap-2 items-center flex-wrap")
        with edit_row:
            conv_input = ui.input("Convergence (°)").props("dense outlined").classes(
                "w-36 font-mono"
            ).tooltip(
                "Grid convergence angle used for the True ↔ Grid azimuth conversion. "
                "Apply an override to re-run the pipeline with your value."
            )
            ui.button("Apply convergence", icon="explore", on_click=lambda: apply_convergence()).props(
                "outline"
            )
            ui.label("·").classes("text-gray-400 mx-2")
            ui.button(
                "Delete selected station", icon="delete", on_click=lambda: delete_selected()
            ).props("outline color=negative")
            ui.button(
                "Restore original survey", icon="restore", on_click=lambda: restore_original()
            ).props("outline").tooltip(
                "Revert all station edits and clear the SHL / convergence overrides"
            )
            edit_note = ui.label("").classes("text-xs text-amber-700")
        edit_row.set_visibility(False)

        ui.label(
            "Tip: MD, inclination, and azimuth cells are editable — double-click a "
            "cell, type, press Enter. Changes reprocess the survey and cascade "
            "through clearances, the map, and the WCR."
        ).classes("text-xs text-gray-400")

        grid = ui.aggrid(
            {
                "columnDefs": [],
                "rowData": [],
                "rowSelection": "single",
                "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
            }
        ).classes("w-full").style("height: 600px")
        grid.visible = False
        grid.on("cellValueChanged", lambda e: on_cell_edit(e))

    def current_dataframe() -> tuple[pd.DataFrame | None, str]:
        """Returns (dataframe, source_label)."""
        citing = citing_select.value
        if not citing:
            return None, ""
        # Prefer processed data when available.
        result = state.processed.get(citing)
        if result is not None:
            ps = result.frames[selected_frame["value"]]
            return ps.points, f"processed · {_FRAME_LABELS[selected_frame['value']]}"
        return state.surveys.get(citing), "raw"

    # ------------------------------------------------------------------
    # Edit helpers — every mutation funnels through _cascade.
    # ------------------------------------------------------------------

    def _snapshot_original(citing: str) -> None:
        if citing not in state.surveys_original and citing in state.surveys:
            state.surveys_original[citing] = state.surveys[citing].copy()

    async def _cascade(note: str) -> None:
        if state.post_load is None:
            ui.notify("Pipeline unavailable — reload the page.", type="negative")
            return
        ui.notify(note, type="positive")
        await state.post_load(switch_to_survey=False)

    def _edit_state_note() -> str:
        bits = []
        if state.surveys_original:
            bits.append(f"{len(state.surveys_original)} survey(s) edited")
        if state.shl_override is not None:
            bits.append("SHL overridden")
        if state.convergence_override is not None:
            bits.append(f"convergence overridden ({state.convergence_override:.4f}°)")
        return " · ".join(bits)

    async def interpolate() -> None:
        citing = citing_select.value
        raw = state.surveys.get(citing)
        if raw is None or raw.empty:
            ui.notify("Load a well first.", type="warning")
            return
        try:
            md = float(interp_md_input.value)
        except (TypeError, ValueError):
            ui.notify("MD must be numeric.", type="warning")
            return
        station = interpolate_raw_station(raw, md)
        _snapshot_original(citing)
        state.surveys[citing] = insert_station(raw, md)
        interp_result.text = (
            f"added MD {md:,.1f} · Inc {station['Inclination']:.2f}° "
            f"· Azi {station['Azimuth']:.2f}°"
        )
        await _cascade(f"Station added at MD {md:,.1f} ft")

    async def on_cell_edit(e) -> None:
        args = e.args or {}
        col = args.get("colId") or (args.get("colDef") or {}).get("field")
        data = args.get("data") or {}
        citing = citing_select.value
        raw = state.surveys.get(citing)
        if raw is None or col not in _EDITABLE_FIELDS:
            rerender()
            return
        try:
            new_value = float(args.get("newValue"))
        except (TypeError, ValueError):
            ui.notify("Value must be numeric.", type="warning")
            rerender()  # revert the cell display
            return

        md_key = next((f for f in _MD_FIELDS if f in data), None)
        try:
            if col in _MD_FIELDS:
                old_md = float(args.get("oldValue"))
            else:
                old_md = float(data.get(md_key))
        except (TypeError, ValueError):
            ui.notify("Could not identify the station's MD.", type="negative")
            rerender()
            return

        kwargs: dict[str, float] = {}
        if col in _MD_FIELDS:
            kwargs["md"] = new_value
        elif col in _INC_FIELDS:
            kwargs["inclination"] = new_value
        else:
            # Azimuth typed in the displayed frame → convert to the raw
            # survey's native north reference before storing.
            sr = state.processed.get(citing)
            if sr is not None and col == "azimuth":
                ps = sr.frames[SurveyFrame.TRUE]
                declination = 0.0
                native = (sr.header.north_reference or "true").lower()
                if (
                    native.startswith("m")
                    and sr.header.surface_lat is not None
                    and sr.header.surface_lon is not None
                ):
                    declination = lookup_magnetic_field(
                        sr.header.surface_lat,
                        sr.header.surface_lon,
                        altitude_m=(ps.elevation or 0.0) * 0.3048,
                    ).declination
                new_value = displayed_to_native_azimuth(
                    new_value,
                    displayed_frame=selected_frame["value"].value,
                    native_ref=sr.header.north_reference,
                    convergence=ps.convergence_angle or 0.0,
                    declination=declination,
                )
            kwargs["azimuth"] = new_value

        _snapshot_original(citing)
        try:
            state.surveys[citing] = update_station(raw, old_md, **kwargs)
        except ValueError as exc:
            ui.notify(
                f"{exc} — this row isn't an original survey station.",
                type="warning",
            )
            rerender()
            return
        await _cascade(f"Station at MD {old_md:,.0f} ft updated")

    async def delete_selected() -> None:
        citing = citing_select.value
        raw = state.surveys.get(citing)
        if raw is None or raw.empty:
            ui.notify("Load a well first.", type="warning")
            return
        rows = await grid.get_selected_rows()
        if not rows:
            ui.notify("Select a row in the grid first.", type="warning")
            return
        data = rows[0]
        md_key = next((f for f in _MD_FIELDS if f in data), None)
        if md_key is None:
            ui.notify("Selected row has no MD column.", type="negative")
            return
        md = float(data[md_key])
        _snapshot_original(citing)
        try:
            state.surveys[citing] = delete_station(raw, md)
        except ValueError as exc:
            ui.notify(f"{exc} — this row isn't an original survey station.", type="warning")
            return
        await _cascade(f"Deleted station at MD {md:,.0f} ft")

    async def restore_original() -> None:
        had_edits = bool(state.surveys_original)
        had_overrides = state.shl_override is not None or state.convergence_override is not None
        if not had_edits and not had_overrides:
            ui.notify("No survey edits to undo.", type="info")
            return
        for citing, df in state.surveys_original.items():
            state.surveys[citing] = df.copy()
        state.surveys_original = {}
        state.shl_override = None
        state.convergence_override = None
        shl_lat_input.value = ""
        shl_lon_input.value = ""
        interp_result.text = ""
        await _cascade("Restored original survey")

    async def apply_convergence() -> None:
        try:
            state.convergence_override = float(conv_input.value)
        except (TypeError, ValueError):
            ui.notify("Convergence must be numeric (degrees).", type="warning")
            return
        await _cascade(f"Convergence set to {state.convergence_override:.4f}°")

    async def reprocess_shl() -> None:
        if not state.surveys or not state.headers:
            ui.notify("Load a well first.", type="warning")
            return
        try:
            a = dms_to_decimal(shl_lat_input.value or "")
            b = dms_to_decimal(shl_lon_input.value or "")
        except ValueError as exc:
            ui.notify(f"Coordinate parse failed: {exc}", type="warning")
            return
        # Lat/lon detected by magnitude; bigger numbers are UTM 12N metres.
        if abs(a) <= 90 and abs(b) <= 180:
            lat, lon = a, b
        else:
            lat, lon = utm_to_latlon(a, b, 12, "N")
        state.shl_override = (lat, lon)
        await _cascade(f"SHL moved to {lat:.5f}, {lon:.5f}")

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def rerender() -> None:
        try:
            _rerender_impl()
        except Exception as exc:
            log.exception("survey.rerender.failed", error=str(exc))
            try:
                ui.notify(
                    f"Survey grid render failed: {exc}",
                    type="negative",
                    multi_line=True,
                    timeout=8000,
                )
            except Exception:
                pass

    def _rerender_impl() -> None:
        df, source = current_dataframe()
        if df is None or df.empty:
            grid.visible = False
            point_count.text = ""
            return
        log.info(
            "survey.rerender",
            citing=citing_select.value,
            frame=selected_frame["value"].value,
            rows=len(df),
            cols=list(df.columns),
            dtypes={c: str(df[c].dtype) for c in df.columns},
        )
        # Display-only rounding: lat/lon → 5 dp, all other numeric → 2 dp.
        # We round in Python (so the WS payload is small + clean) AND ship
        # a JS valueFormatter as a safety net for floats whose JSON repr
        # leaks past 2 dp (e.g. 9258.07000000001).
        cols = [c for c in df.columns if c != "shp_pt"]
        display_df = df.drop(columns=[c for c in ("shp_pt",) if c in df.columns]).copy()
        col_defs = []
        for col in cols:
            spec: dict = {"field": col, "headerName": col}
            if col in _EDITABLE_FIELDS:
                spec["editable"] = True
                spec["cellClass"] = "font-medium"
            if pd.api.types.is_numeric_dtype(display_df[col]):
                cl = col.lower()
                digits = 5 if ("lat" in cl or "lon" in cl) else 2
                display_df[col] = display_df[col].round(digits)
                # ES5-safe JS expression — no arrow fn, no nullish coalescing.
                spec[":valueFormatter"] = (
                    "function(p) { "
                    "if (p.value === null || p.value === undefined) return ''; "
                    "if (typeof p.value !== 'number' || isNaN(p.value)) return p.value; "
                    f"return p.value.toFixed({digits}); "
                    "}"
                )
            col_defs.append(spec)
        grid.options["columnDefs"] = col_defs
        grid.options["rowData"] = (
            display_df.where(display_df.notna(), None).to_dict(orient="records")
        )
        grid.update()
        grid.visible = True
        md_col = next(
            (c for c in ("measured_depth", "MeasuredDepth") if c in df.columns),
            None,
        )
        if md_col:
            point_count.text = (
                f"{len(df)} pts · MD {df[md_col].min():.1f}→{df[md_col].max():.1f} ft · {source}"
            )
        else:
            point_count.text = f"{len(df)} pts · {source}"

        edit_note.text = _edit_state_note()

        # KOP/landing markers + convergence come from processed data only.
        result = state.processed.get(citing_select.value)
        if result is None:
            kop_card.classes("hidden")
            kop_card.classes(remove="flex")
        else:
            kop_card.classes(remove="hidden")
            kop_md_label.text = (
                f"KOP: {result.kop.md:.1f} ft" if result.kop.md is not None else "KOP: —"
            )
            landing_md_label.text = (
                f"Landing: {result.landing_md:.1f} ft" if result.landing_md else "Landing: —"
            )
            method_label.text = (
                f"({result.kop.method}, conf {result.kop.confidence:.0%})"
                if result.kop.md is not None
                else ""
            )
            conv = result.frames[SurveyFrame.TRUE].convergence_angle
            if conv is not None:
                conv_input.value = f"{conv:.4f}"

    def process() -> None:
        if not state.surveys or not state.headers:
            ui.notify("Load a well first.", type="warning")
            return
        with ui.dialog() as wait_dialog, ui.card():
            ui.label("Processing survey…")
            ui.spinner(size="lg")
        wait_dialog.open()
        try:
            results = survey_service.process(
                state.headers,
                state.surveys,
                surface_override=state.shl_override,
                convergence_override=state.convergence_override,
            )
        except Exception as exc:  # pragma: no cover
            wait_dialog.close()
            ui.notify(f"Processing failed: {exc}", type="negative")
            raise
        wait_dialog.close()
        state.processed = results
        ui.notify(
            f"Processed {len(results)} survey(s) · "
            + ", ".join(f"{k} (KOP {r.kop.md or '—'} ft)" for k, r in results.items()),
            type="positive",
        )
        rerender()

    def refresh() -> None:
        if not state.surveys or state.primary is None:
            header_label.text = "Load a well first."
            header_label.visible = True
            controls.set_visibility(False)
            tools_row.set_visibility(False)
            edit_row.set_visibility(False)
            kop_card.classes("hidden")
            grid.visible = False
            return
        header_label.visible = False
        controls.set_visibility(True)
        tools_row.set_visibility(True)
        edit_row.set_visibility(True)
        options = sorted(state.surveys.keys())
        citing_select.options = options
        citing_select.value = state.selected_citing or options[0]
        citing_select.update()

        # Default the Frame toggle to whatever the source declared.
        # Header.north_reference is one of "true", "grid", "magnetic" (or None).
        # Magnetic source data is converted to true during processing, so we
        # show that in the True frame as well.
        nr = (state.primary.north_reference or "").lower() if state.primary else ""
        default_frame = SurveyFrame.GRID if nr == "grid" else SurveyFrame.TRUE
        if selected_frame["value"] != default_frame:
            selected_frame["value"] = default_frame
            frame_toggle.value = default_frame.value
            frame_toggle.update()
            log.info(
                "survey.frame.default",
                north_reference=nr or None,
                default_frame=default_frame.value,
            )

        rerender()

    return refresh
