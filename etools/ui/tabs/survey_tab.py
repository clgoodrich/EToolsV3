"""Survey tab — citing/frame controls, raw + processed grids, KOP/landing markers."""

from __future__ import annotations

from typing import Callable

import pandas as pd
from nicegui import ui

from etools.core.coordinates import dms_to_decimal, utm_to_latlon
from etools.logging_setup import get_logger
from etools.models import SurveyFrame
from etools.services import SurveyService
from etools.ui.state import AppState

log = get_logger(__name__)

_FRAME_LABELS = {SurveyFrame.TRUE: "True North", SurveyFrame.GRID: "Grid North"}


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

        # --- Tools: interpolate at an arbitrary MD; reprocess with a new SHL ---
        tools_row = ui.row().classes("gap-2 items-center flex-wrap")
        with tools_row:
            interp_md_input = ui.input("MD (ft)", placeholder="7765").props(
                "dense outlined"
            ).classes("w-32")
            ui.button("Interpolate", icon="vertical_align_center", on_click=lambda: interpolate()).props(
                "outline"
            ).tooltip("Interpolate the processed survey at this measured depth")
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
                "Re-run survey processing with the surface hole moved here. Takes decimal "
                "lat/lon, deg min sec, or UTM 12N metres. Recalculate clearances afterwards."
            )
        tools_row.set_visibility(False)

        grid = ui.aggrid(
            {
                "columnDefs": [],
                "rowData": [],
                "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
            }
        ).classes("w-full").style("height: 600px")
        grid.visible = False

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

        # KOP/landing markers come from processed data only.
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

    def interpolate() -> None:
        result = state.processed.get(citing_select.value)
        if result is None:
            ui.notify("Process the survey first.", type="warning")
            return
        try:
            md = float(interp_md_input.value)
        except (TypeError, ValueError):
            ui.notify("MD must be numeric.", type="warning")
            return
        from etools.core.survey.processor import interpolate_at_md

        points = result.frames[selected_frame["value"]].points
        try:
            s = interpolate_at_md(points, md)
        except Exception as exc:
            ui.notify(f"Interpolation failed: {exc}", type="negative")
            return
        parts = [f"MD {md:,.0f}"]
        for key, label, digits in (
            ("inclination", "Inc", 2),
            ("azimuth", "Azi", 2),
            ("tvd", "TVD", 1),
            ("easting", "E", 1),
            ("northing", "N", 1),
            ("lat", "Lat", 5),
            ("lon", "Lon", 5),
        ):
            if key in s and s[key] is not None:
                parts.append(f"{label} {s[key]:,.{digits}f}")
        interp_result.text = " · ".join(parts)

    def reprocess_shl() -> None:
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
        new_headers = [
            h.model_copy(update={"surface_lat": lat, "surface_lon": lon})
            for h in state.headers
        ]
        with ui.dialog() as wait_dialog, ui.card():
            ui.label(f"Reprocessing with SHL at {lat:.5f}, {lon:.5f}…")
            ui.spinner(size="lg")
        wait_dialog.open()
        try:
            results = survey_service.process(new_headers, state.surveys)
        except Exception as exc:  # pragma: no cover
            wait_dialog.close()
            ui.notify(f"Reprocessing failed: {exc}", type="negative")
            raise
        wait_dialog.close()
        state.processed = results
        state.clearances = {}
        ui.notify(
            f"Reprocessed {len(results)} survey(s) from SHL {lat:.5f}, {lon:.5f}. "
            "Clearances were cleared — recalculate them on the Clearance tab.",
            type="positive",
            multi_line=True,
        )
        rerender()

    def process() -> None:
        if not state.surveys or not state.headers:
            ui.notify("Load a well first.", type="warning")
            return
        with ui.dialog() as wait_dialog, ui.card():
            ui.label("Processing survey…")
            ui.spinner(size="lg")
        wait_dialog.open()
        try:
            results = survey_service.process(state.headers, state.surveys)
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
            kop_card.classes("hidden")
            grid.visible = False
            return
        header_label.visible = False
        controls.set_visibility(True)
        tools_row.set_visibility(True)
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


def _numeric_formatter(col: str):
    name = col.lower()
    # Latitude / longitude get 5 decimal places (≈1 metre precision); every
    # other numeric column rounds to 2 decimals.
    is_lat_lon = "lat" in name or "lon" in name
    numeric_hint = is_lat_lon or any(
        token in name
        for token in (
            "depth",
            "north",
            "east",
            "azimuth",
            "incl",
            " x",
            "_x",
            " y",
            "_y",
            "dogleg",
            "section",
            "tvd",
            "dls",
            "offset",
        )
    )
    if not numeric_hint:
        return None
    digits = 5 if is_lat_lon else 2
    return {
        "function": (
            "params.value === null || params.value === undefined ? '' : "
            f"(typeof params.value === 'number' ? params.value.toFixed({digits}) : params.value)"
        )
    }
