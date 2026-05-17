"""Load Well tab — API + lateral entry, header summary card."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Union

from nicegui import ui

from etools.models import WellLookup
from etools.ui.state import AppState

LoadHandler = Callable[[WellLookup], Union[None, Awaitable[None]]]
PdfRouteHandler = Callable[[], None]


def render_load_tab(
    state: AppState,
    on_load: LoadHandler,
    on_route_to_pdf: PdfRouteHandler | None = None,
) -> Callable[[], None]:
    """Returns a refresh callback the parent invokes after a well loads."""

    with ui.column().classes("p-6 gap-4 w-full max-w-3xl"):
        ui.label("Load Well").classes("text-2xl font-semibold")
        ui.label(
            "Enter the 10-digit API number and a 4-character lateral identifier "
            "(default 0000). Pulls from DirectionalSurveyHeader."
        ).classes("text-sm text-gray-600")

        with ui.row().classes("gap-2 items-end"):
            api_input = ui.input(
                "API (10 digits)",
                value="4301354722",
                validation={"Must be 10 digits": lambda v: bool(v) and v.isdigit() and len(v) == 10},
            ).props("dense outlined").classes("w-56")
            lateral_input = ui.input(
                "Lateral",
                value="0000",
                validation={"Max 4 chars": lambda v: v is not None and len(v) <= 4},
            ).props("dense outlined").classes("w-32")

            async def submit() -> None:
                api = (api_input.value or "").strip()
                lateral = (lateral_input.value or "0000").strip() or "0000"
                try:
                    lookup = WellLookup(api=api, lateral=lateral)
                except ValueError as exc:
                    ui.notify(f"Invalid input: {exc}", type="warning")
                    return
                result = on_load(lookup)
                if asyncio.iscoroutine(result):
                    await result

            ui.button("Load Well", icon="download", on_click=submit).props("color=primary")

        with ui.row().classes("gap-2 items-center mt-1"):
            ui.label("Don't have an API number?").classes("text-sm text-gray-500")
            ui.button(
                "Load from PDF instead",
                icon="upload_file",
                on_click=lambda: (on_route_to_pdf and on_route_to_pdf()),
            ).props("flat dense color=primary")

        ui.separator()

        @ui.refreshable
        def summary() -> None:
            primary = state.primary
            if primary is None:
                ui.label("No well loaded.").classes("text-gray-500 italic")
                return

            with ui.card().classes("w-full"):
                ui.label(primary.well_name or "(unnamed)").classes("text-xl font-medium")
                ui.label(f"{primary.operator or '—'}").classes("text-sm text-gray-600")
                ui.separator().classes("my-2")
                with ui.grid(columns=4).classes("gap-x-6 gap-y-1 text-sm"):
                    rows = [
                        ("API / Lateral", f"{primary.api} / {primary.lateral}"),
                        ("Citing", primary.citing_type or "—"),
                        ("Survey Co.", primary.survey_company or "—"),
                        ("Survey Type", primary.survey_type or "—"),
                        ("Surface Lat", primary.surface_lat),
                        ("Surface Lon", primary.surface_lon),
                        ("Elevation", primary.surface_elevation),
                        ("North Ref", primary.north_reference or "—"),
                        ("Grid Conv.", primary.grid_convergence),
                        ("Grid Scale", primary.grid_scale_factor),
                        ("UTM Zone", primary.utm_zone or "—"),
                        ("PLSS", primary.plss_location or "—"),
                    ]
                    for label, value in rows:
                        ui.label(label).classes("text-gray-500")
                        ui.label(str(value) if value not in (None, "") else "—")

                if len(state.headers) > 1:
                    others = ", ".join(
                        f"{h.citing_type or '?'}({h.pkey})"
                        for h in state.headers if h.pkey != primary.pkey
                    )
                    ui.label(f"Other headers: {others}").classes("text-xs text-gray-500 mt-2")

                if state.surveys:
                    counts = " · ".join(f"{k}: {len(v)} pts" for k, v in state.surveys.items())
                    ui.label(f"Surveys → {counts}").classes("text-xs text-gray-500")

        summary()
        return summary.refresh
