"""Clearance tab — FNL/FSL/FEL/FWL footage table + summary card."""

from __future__ import annotations

from typing import Callable

import pandas as pd
from nicegui import ui

from etools.models import SurveyFrame
from etools.services import ClearanceService
from etools.ui.state import AppState


def render_clearance_tab(state: AppState) -> Callable[[], None]:
    clearance_service = ClearanceService()

    with ui.column().classes("p-4 gap-3 w-full"):
        header_label = ui.label("Process the survey first.").classes("text-gray-500 italic")

        controls = ui.row().classes("gap-3 items-center")
        with controls:
            ui.label("Citing:").classes("text-sm")
            citing_select = (
                ui.select(options=[], on_change=lambda _: rerender())
                .props("dense outlined")
                .classes("w-44")
            )
            ui.button(
                "Calculate Clearances", icon="straighten", on_click=lambda: run()
            ).props("color=primary")
            status = ui.label("").classes("text-sm text-gray-500 ml-2")
        controls.set_visibility(False)

        ui.separator()
        ui.label("Summary footages (SHL · KOP · Landing · BHL)").classes("text-sm font-semibold")
        summary_grid = ui.aggrid(
            {
                "columnDefs": [],
                "rowData": [],
                "defaultColDef": {"resizable": True, "sortable": False},
            }
        ).classes("w-full").style("height: 220px")
        summary_grid.visible = False

        ui.separator()
        ui.label("All survey points").classes("text-sm font-semibold")
        full_grid = ui.aggrid(
            {
                "columnDefs": [],
                "rowData": [],
                "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
            }
        ).classes("w-full").style("height: 500px")
        full_grid.visible = False

    def run() -> None:
        if not state.processed:
            ui.notify("Process the survey first.", type="warning")
            return
        with ui.dialog() as wait, ui.card():
            ui.label("Calculating clearances…")
            ui.spinner(size="lg")
        wait.open()
        try:
            results = {}
            for citing, sr in state.processed.items():
                ps = sr.frames[SurveyFrame.TRUE]
                results[citing] = clearance_service.calculate(
                    ps, kop_md=sr.kop.md, landing_md=sr.landing_md
                )
        except Exception as exc:  # pragma: no cover
            wait.close()
            ui.notify(f"Clearance calc failed: {exc}", type="negative")
            raise
        wait.close()
        state.clearances = results
        ui.notify(
            "Clearances ready: " + ", ".join(f"{k} ({len(r.points)} pts)" for k, r in results.items()),
            type="positive",
        )
        rerender()

    def rerender() -> None:
        if not state.clearances:
            summary_grid.visible = False
            full_grid.visible = False
            status.text = ""
            return

        citing = citing_select.value
        result = state.clearances.get(citing)
        if result is None:
            summary_grid.visible = False
            full_grid.visible = False
            return

        # Summary
        summary_df = _round_for_display(result.summary)
        summary_grid.options["columnDefs"] = _columns_for(summary_df)
        summary_grid.options["rowData"] = summary_df.where(summary_df.notna(), None).to_dict(
            orient="records"
        )
        summary_grid.update()
        summary_grid.visible = not result.summary.empty

        # Full points (drop heavy columns)
        view_cols = [
            c
            for c in [
                "measured_depth",
                "inclination",
                "azimuth",
                "tvd",
                "Conc",
                "label",
                "FNL",
                "FSL",
                "FEL",
                "FWL",
            ]
            if c in result.points.columns
        ]
        full = _round_for_display(result.points[view_cols].copy())
        full_grid.options["columnDefs"] = _columns_for(full)
        full_grid.options["rowData"] = full.where(full.notna(), None).to_dict(orient="records")
        full_grid.update()
        full_grid.visible = True

        n_sec = result.points["Conc"].nunique()
        status.text = f"{len(full)} pts · {n_sec} section(s) crossed"

    def refresh() -> None:
        if not state.processed:
            header_label.text = "Process the survey first."
            header_label.visible = True
            controls.set_visibility(False)
            summary_grid.visible = False
            full_grid.visible = False
            return
        header_label.visible = False
        controls.set_visibility(True)
        opts = sorted(state.processed.keys())
        citing_select.options = opts
        if not citing_select.value or citing_select.value not in opts:
            citing_select.value = opts[0]
        citing_select.update()
        rerender()

    return refresh


_FORMATTED_HINTS = (
    "depth", "fnl", "fsl", "fel", "fwl",
    "azimuth", "tvd", "incl", "lat", "lon",
)


def _round_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with numeric columns rounded for display only.

    lat/lon → 5 decimal places, every other numeric column → 2.
    The caller's DataFrame is left untouched.
    """
    out = df.copy()
    for col in out.columns:
        if not pd.api.types.is_numeric_dtype(out[col]):
            continue
        cl = col.lower()
        digits = 5 if ("lat" in cl or "lon" in cl) else 2
        out[col] = out[col].round(digits)
    return out


def _columns_for(df: pd.DataFrame) -> list[dict]:
    cols: list[dict] = []
    for col in df.columns:
        spec: dict = {"field": col, "headerName": col}
        cl = col.lower()
        if pd.api.types.is_numeric_dtype(df[col]) or any(t in cl for t in _FORMATTED_HINTS):
            digits = 5 if ("lat" in cl or "lon" in cl) else 2
            # `:valueFormatter` colon-prefix tells NiceGUI to ship this as a JS
            # expression instead of a literal dict. ES5-safe (no arrow fn).
            spec[":valueFormatter"] = (
                "function(p) { "
                "if (p.value === null || p.value === undefined) return ''; "
                "if (typeof p.value !== 'number' || isNaN(p.value)) return p.value; "
                f"return p.value.toFixed({digits}); "
                "}"
            )
        cols.append(spec)
    return cols
