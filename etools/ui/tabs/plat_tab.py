"""Plat Searcher — ad-hoc TRS lookup. Independent of any loaded well."""

from __future__ import annotations

from typing import Callable

import pandas as pd
from nicegui import ui

from etools.core.coordinates import parse_coord_pair
from etools.repositories import PlatRepository


def render_plat_tab() -> Callable[[], None]:
    repo = PlatRepository()

    with ui.column().classes("p-4 gap-3 w-full"):
        ui.label("Plat Searcher").classes("text-2xl font-semibold")
        ui.label(
            "Enter a section's Township-Range-Section identifier or a UTM "
            "easting/northing to look up its plat polygon and adjacent sections."
        ).classes("text-sm text-gray-600")

        with ui.row().classes("gap-2 items-end flex-wrap"):
            section_input = ui.input(
                "Section (1-36)",
                placeholder="14",
            ).props("dense outlined").classes("w-32")
            twp_input = ui.input("Township", placeholder="2S").props("dense outlined").classes("w-28")
            rng_input = ui.input("Range", placeholder="5W").props("dense outlined").classes("w-28")
            mer_input = ui.select(
                {"S": "Salt Lake (S)", "U": "Uintah (U)"}, value="U"
            ).props("dense outlined").classes("w-44")
            ui.button("Search", icon="search", on_click=lambda: search_by_trs())
            ui.label("·").classes("text-gray-400 mx-2")
            easting_input = ui.input("Easting (m)").props("dense outlined").classes("w-36")
            northing_input = ui.input("Northing (m)").props("dense outlined").classes("w-36")
            ui.button("Search by UTM", icon="my_location", on_click=lambda: search_by_utm())

        ui.separator()
        status = ui.label("").classes("text-sm text-gray-500")

        with ui.tabs().classes("w-full") as sub_tabs:
            tab_sections = ui.tab("Sections", icon="grid_on")
            tab_adjacent = ui.tab("Adjacency", icon="hub")
            tab_distance = ui.tab("Distance Checker", icon="straighten")

        with ui.tab_panels(sub_tabs, value=tab_sections).classes("w-full"):
            with ui.tab_panel(tab_sections):
                section_grid = ui.aggrid(
                    {
                        "columnDefs": [],
                        "rowData": [],
                        "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
                    }
                ).classes("w-full").style("height: 500px")
            with ui.tab_panel(tab_adjacent):
                adjacency_grid = ui.aggrid(
                    {
                        "columnDefs": [],
                        "rowData": [],
                        "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
                    }
                ).classes("w-full").style("height: 500px")
            with ui.tab_panel(tab_distance):
                _render_distance_checker()

    def render_bundle(bundle) -> None:
        if bundle.sections.empty:
            status.text = "No sections matched."
            section_grid.options["rowData"] = []
            adjacency_grid.options["rowData"] = []
            section_grid.update()
            adjacency_grid.update()
            return

        df = pd.DataFrame(
            {
                "Conc": bundle.sections["Conc"],
                "Label": bundle.sections["label"],
                "Centroid X (m)": bundle.sections.geometry.centroid.x.round(1),
                "Centroid Y (m)": bundle.sections.geometry.centroid.y.round(1),
                "Area (acres)": (bundle.sections.geometry.area / 4046.86).round(1),
                "Vertices": bundle.sections.geometry.apply(
                    lambda g: len(g.exterior.coords) if g.geom_type == "Polygon" else 0
                ),
            }
        )
        section_grid.options["columnDefs"] = [{"field": c, "headerName": c} for c in df.columns]
        section_grid.options["rowData"] = df.to_dict(orient="records")
        section_grid.update()

        adj = bundle.adjacent.copy()
        if not adj.empty:
            adj.columns = ["Section (Conc2)", "Adjacent (Conc2)"]
        adjacency_grid.options["columnDefs"] = [{"field": c, "headerName": c} for c in adj.columns]
        adjacency_grid.options["rowData"] = adj.to_dict(orient="records")
        adjacency_grid.update()

        status.text = f"{len(df)} section(s) · {len(bundle.adjacent)} adjacency rows"

    def search_by_trs() -> None:
        try:
            section = int(section_input.value)
            twp = _parse_int(twp_input.value)
            rng = _parse_int(rng_input.value)
        except (TypeError, ValueError):
            ui.notify("Section/Township/Range must be numeric.", type="warning")
            return
        twp_dir = (twp_input.value or "").strip().upper()[-1] if twp_input.value else "S"
        rng_dir = (rng_input.value or "").strip().upper()[-1] if rng_input.value else "W"
        if twp_dir not in ("N", "S"):
            twp_dir = "S"
        if rng_dir not in ("E", "W"):
            rng_dir = "W"
        meridian = (mer_input.value or "U")[0]
        conc = f"{section:02d}{twp:02d}{twp_dir}{rng:02d}{rng_dir}{meridian}"
        bundle = repo.fetch_for_point(easting=0, northing=0, buffer_m=0)  # dummy seed
        # Re-query specifically by Conc.
        full_df = repo._fetch_concs([conc])  # type: ignore[attr-defined]
        if full_df.empty:
            ui.notify(f"No plat data for Conc={conc}", type="warning")
            return
        bundle = bundle.__class__(
            sections=PlatRepository._build_sections(full_df),  # type: ignore[attr-defined]
            adjacent=repo._fetch_adjacent([conc]),  # type: ignore[attr-defined]
        )
        render_bundle(bundle)

    def search_by_utm() -> None:
        try:
            e = float(easting_input.value)
            n = float(northing_input.value)
        except (TypeError, ValueError):
            ui.notify("Easting and Northing must be numeric.", type="warning")
            return
        bundle = repo.fetch_for_point(easting=e, northing=n, buffer_m=2000)
        render_bundle(bundle)

    def refresh() -> None:
        pass

    return refresh


def _parse_int(value: str | None) -> int:
    if value is None:
        raise ValueError("missing")
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        raise ValueError("non-numeric")
    return int(digits)


# ---------------------------------------------------------------------------
# Distance checker
# ---------------------------------------------------------------------------

_COORD_HINT = "555200, 4458447 (UTM m) · 40.2701, -110.3502 · 40 16 12.4 N, 110 21 5.6 W"


def _render_distance_checker() -> None:
    ui.label(
        "Perpendicular distance from a check point to the line segment A–B. "
        "Each field takes UTM metres, decimal lat/lon, or deg min sec."
    ).classes("text-sm text-gray-600")
    a_input = ui.input("Segment point A", placeholder=_COORD_HINT).props(
        "dense outlined"
    ).classes("w-[34rem] font-mono")
    b_input = ui.input("Segment point B", placeholder=_COORD_HINT).props(
        "dense outlined"
    ).classes("w-[34rem] font-mono")
    c_input = ui.input("Check point", placeholder=_COORD_HINT).props(
        "dense outlined"
    ).classes("w-[34rem] font-mono")
    result = ui.label("").classes("text-base font-medium mt-2")

    def calculate() -> None:
        from shapely.geometry import LineString, Point

        try:
            a = parse_coord_pair(a_input.value)
            b = parse_coord_pair(b_input.value)
            c = parse_coord_pair(c_input.value)
        except ValueError as exc:
            ui.notify(f"Coordinate parse failed: {exc}", type="warning")
            return
        meters = LineString([a, b]).distance(Point(c))
        feet = meters * 3.28084
        result.text = f"Distance: {feet:,.1f} ft  ({meters:,.1f} m)"

    ui.button("Calculate", icon="straighten", on_click=calculate).props("color=primary")
