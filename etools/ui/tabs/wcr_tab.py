"""WCR tab — preview info/casing/perforations and generate the Excel report."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd
from nicegui import app, ui

from etools.config import settings
from etools.services import WCRService
from etools.ui.state import AppState


def render_wcr_tab(state: AppState) -> Callable[[], None]:
    wcr_service = WCRService()
    cache: dict = {"bundle": None, "api": None, "lateral": None}

    with ui.column().classes("p-4 gap-3 w-full"):
        header_label = ui.label("Calculate clearances first.").classes("text-gray-500 italic")

        controls = ui.row().classes("gap-3 items-center")
        with controls:
            ui.label("Citing:").classes("text-sm")
            citing_select = (
                ui.select(options=[], on_change=lambda _: rerender())
                .props("dense outlined")
                .classes("w-44")
            )
            generate_btn = ui.button(
                "Generate WCR Excel", icon="description", on_click=lambda: generate()
            ).props("color=primary")
            status = ui.label("").classes("text-sm text-gray-500 ml-2")
        controls.set_visibility(False)

        ui.separator()

        # Well info card
        info_card = ui.card().classes("w-full")
        # Casing table
        ui.label("Casing & Cement").classes("text-sm font-semibold mt-2")
        casing_grid = ui.aggrid(
            {
                "columnDefs": [],
                "rowData": [],
                "defaultColDef": {"resizable": True, "sortable": True},
            }
        ).classes("w-full").style("height: 380px")
        # Perforation/formation tops
        ui.label("Perforations & Formation Tops").classes("text-sm font-semibold mt-2")
        perf_grid = ui.aggrid(
            {
                "columnDefs": [],
                "rowData": [],
                "defaultColDef": {"resizable": True, "sortable": True},
            }
        ).classes("w-full").style("height: 280px")

    def load_wcr_bundle() -> None:
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

    def rerender() -> None:
        if state.primary is None:
            controls.set_visibility(False)
            header_label.visible = True
            return
        load_wcr_bundle()
        bundle = cache.get("bundle")
        if bundle is None or bundle.info is None:
            header_label.text = "No WCR data found for this well."
            header_label.visible = True
            controls.set_visibility(False)
            return
        header_label.visible = False
        controls.set_visibility(True)

        # Info card
        info = bundle.info
        info_card.clear()
        with info_card:
            with ui.grid(columns=4).classes("gap-x-6 gap-y-1 text-sm"):
                pairs = [
                    ("Well", info.well_name),
                    ("Operator", info.operator),
                    ("API / Lateral", f"{info.api_well_no[:10]} / {info.api_well_no[10:]}"),
                    ("Type", info.well_type),
                    ("Status", info.well_status),
                    ("Slant", info.slant),
                    ("Spud", _fmt_date(info.spud_date)),
                    ("Rotary", _fmt_date(info.rotary_date)),
                    ("TD reached", _fmt_date(info.td_date)),
                    ("Completed", _fmt_date(info.completion_date)),
                    ("Proposed MD/TVD (ft)", f"{info.proposed_md_ft or '—'} / {info.proposed_tvd_ft or '—'}"),
                    ("Elevation (ft)", info.elevation_ft),
                ]
                for label, value in pairs:
                    ui.label(label).classes("text-gray-500")
                    ui.label(str(value) if value not in (None, "") else "—")

        # Casing
        casing_df = bundle.casing
        casing_grid.options["columnDefs"] = _columns_for(casing_df)
        casing_grid.options["rowData"] = (
            casing_df.where(casing_df.notna(), None).astype(object).to_dict(orient="records") if not casing_df.empty else []
        )
        casing_grid.update()

        # Perfs + formations combined
        perf_df = bundle.perforations
        perf_grid.options["columnDefs"] = _columns_for(perf_df)
        perf_grid.options["rowData"] = (
            perf_df.where(perf_df.notna(), None).astype(object).to_dict(orient="records") if not perf_df.empty else []
        )
        perf_grid.update()

    def generate() -> None:
        if not state.clearances:
            ui.notify("Calculate clearances first.", type="warning")
            return
        citing = citing_select.value or next(iter(state.clearances), None)
        if citing not in state.clearances:
            ui.notify("No clearance data for selected citing.", type="warning")
            return
        clearance = state.clearances[citing]
        load_wcr_bundle()
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

        # Make file downloadable + show notification with link.
        rel = Path(path).name
        download_url = _serve_output_file(path)
        status.text = f"Saved {rel}"
        ui.notify(f"WCR generated: {rel}", type="positive")
        with ui.dialog() as dlg, ui.card():
            ui.label("WCR Excel ready").classes("text-lg font-semibold")
            ui.label(str(path)).classes("text-xs text-gray-600 break-all")
            with ui.row():
                ui.button("Open folder", on_click=lambda: ui.run_javascript(
                    f"window.open('{download_url}', '_blank')"
                ))
                ui.button("Download", icon="download", on_click=lambda: ui.download(str(path)))
                ui.button("Close", on_click=dlg.close)
        dlg.open()

    def refresh() -> None:
        if state.primary is None:
            header_label.text = "Load a well first."
            header_label.visible = True
            controls.set_visibility(False)
            return
        # Populate citing select from available clearance results.
        if state.clearances:
            opts = sorted(state.clearances.keys())
            citing_select.options = opts
            if not citing_select.value or citing_select.value not in opts:
                citing_select.value = opts[0]
            citing_select.update()
        cache["bundle"] = None  # invalidate so we reload for the new well
        rerender()

    return refresh


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _serve_output_file(path: Path) -> str:
    """Mount the output dir on the FastAPI side so users can hit it directly."""
    out_dir = Path(settings.output_dir).resolve()
    mount_path = "/output"
    # NiceGUI's underlying FastAPI app — only mount once per process.
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


def _columns_for(df: pd.DataFrame) -> list[dict]:
    cols: list[dict] = []
    for col in df.columns:
        spec = {"field": col, "headerName": col}
        if any(t in col.lower() for t in ("md", "depth", "top", "bottom", "diam", "weight", "tvd")):
            spec["valueFormatter"] = {
                "function": "params.value === null || params.value === undefined ? '' : "
                "(typeof params.value === 'number' ? params.value.toFixed(2) : params.value)"
            }
        cols.append(spec)
    return cols
