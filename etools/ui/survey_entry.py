""""Type / paste survey" dialog: a spreadsheet-style MD / Inc / Azi table.

For wells whose PDFs don't carry the survey. Rows are typed into the grid
(Enter moves down, like Excel) or pasted from Excel with Ctrl+V. Pasted
blocks are parsed server-side (``core.survey.manual``) and go below the last
filled row. "Use this survey" validates the rows and hands the caller a frame
in the same shape the PDF readers produce, so it is processed identically.

Built once inside a tab's layout; ``build_survey_entry`` returns the
function that opens it.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import pandas as pd
from nicegui import ui

from etools.core.survey.manual import build_manual_survey, parse_pasted_rows
from etools.logging_setup import get_logger

log = get_logger(__name__)

_BLANK_ROWS = 12
_COLS = ("md", "inc", "azi")

# Multi-cell pastes become rows; a single value pasted into a cell editor is
# left to the browser.
_PASTE_JS = """(e) => {
  const t = (e.clipboardData || window.clipboardData).getData('text') || '';
  if (!/[\\t\\n]/.test(t.trim())) return;
  e.preventDefault();
  e.stopPropagation();
  emit(t);
}"""


def _blank(n: int, start: int) -> list[dict]:
    return [{"n": start + i, "md": None, "inc": None, "azi": None} for i in range(n)]


def _filled(row: dict) -> bool:
    return any(row.get(c) not in (None, "") for c in _COLS)


def build_survey_entry(
    on_apply: Callable[[pd.DataFrame], Awaitable[None] | None],
) -> Callable[..., None]:
    """Build the dialog; returns ``open(initial=None)``.

    ``on_apply`` receives the validated survey frame (``MeasuredDepth`` /
    ``Inclination`` / ``Azimuth``, ``attrs["north_reference"]``).
    """
    rows: list[dict] = []

    with ui.dialog() as dlg, ui.card().classes("w-[640px] max-w-full gap-3 p-5") as card:
        with ui.row().classes("w-full items-start no-wrap"):
            with ui.column().classes("gap-0"):
                ui.label("Type or paste a survey").classes("text-lg font-semibold")
                ui.label(
                    "Copy the MD, inclination and azimuth columns in Excel, click the "
                    "table and press Ctrl+V — or type into the cells (Enter moves down)."
                ).classes("text-xs text-gray-500")
            ui.space()
            ui.button(icon="close", on_click=dlg.close).props("flat round dense")

        with ui.row().classes("items-center gap-2"):
            ui.label("Azimuths are referenced to").classes("text-sm text-gray-600")
            ref_toggle = ui.toggle(
                {"true": "True north", "grid": "Grid north"}, value="grid"
            ).props("dense no-caps unelevated toggle-color=primary")

        grid = ui.aggrid(
            {
                "columnDefs": [
                    {
                        "field": "n", "headerName": "#", "width": 56,
                        "editable": False, "type": None,
                        "cellClass": "text-gray-400",
                    },
                    {"field": "md", "headerName": "MD (ft)"},
                    {"field": "inc", "headerName": "Inclination (°)"},
                    {"field": "azi", "headerName": "Azimuth (°)"},
                ],
                # Not ``flex``: NiceGUI sets an autoSizeStrategy, and AG Grid
                # never finishes its first render with both (blank table).
                "autoSizeStrategy": {"type": "fitGridWidth"},
                "defaultColDef": {
                    "editable": True, "sortable": False,
                    "suppressMovable": True, "type": "rightAligned",
                },
                "rowData": [],
                "rowHeight": 32,
                "headerHeight": 36,
                "enterNavigatesVertically": True,
                "enterNavigatesVerticallyAfterEdit": True,
                "stopEditingWhenCellsLoseFocus": True,
                "undoRedoCellEditing": True,
            }
        ).classes("w-full").style("height: 340px")

        error = ui.label("").classes("text-sm text-red-700")
        with ui.row().classes("w-full items-center gap-2"):
            ui.button("Add 10 rows", icon="playlist_add", on_click=lambda: _add(10)).props(
                "flat dense no-caps"
            )
            ui.button("Clear", icon="backspace", on_click=lambda: _reset([])).props(
                "flat dense no-caps color=grey-8"
            )
            count = ui.label("").classes("text-xs text-gray-500 ml-2")
            ui.space()
            ui.button("Cancel", on_click=dlg.close).props("flat no-caps")
            ui.button("Use this survey", icon="check", on_click=lambda: _apply()).props(
                "color=primary no-caps unelevated"
            )

    def _show() -> None:
        grid.options["rowData"] = rows
        grid.update()
        n = sum(_filled(r) for r in rows)
        count.text = f"{n} station{'s' if n != 1 else ''}" if n else ""

    def _reset(values: list[tuple]) -> None:
        rows.clear()
        rows.extend(
            {"n": i, "md": md, "inc": inc, "azi": azi}
            for i, (md, inc, azi) in enumerate(values, start=1)
        )
        rows.extend(_blank(max(_BLANK_ROWS - len(rows), 5), len(rows) + 1))
        error.text = ""
        _show()

    def _add(n: int) -> None:
        rows.extend(_blank(n, len(rows) + 1))
        _show()

    def _on_edit(e) -> None:
        args = e.args or {}
        n = (args.get("data") or {}).get("n")
        col = args.get("colId")
        if not n or col not in _COLS or n > len(rows):
            return
        value = args.get("newValue")
        rows[n - 1][col] = None if value in ("", None) else value
        if n == len(rows):  # typing into the last row: keep room below it
            rows.extend(_blank(5, len(rows) + 1))
            _show()
        else:
            count.text = f"{sum(_filled(r) for r in rows)} stations"
        error.text = ""

    def _on_paste(e) -> None:
        pasted = parse_pasted_rows(e.args if isinstance(e.args, str) else "")
        if not pasted:
            ui.notify(
                "Couldn't find MD / inclination / azimuth numbers in what was pasted.",
                type="warning",
            )
            return
        last = max((i for i, r in enumerate(rows) if _filled(r)), default=-1)
        kept = [(r["md"], r["inc"], r["azi"]) for r in rows[: last + 1]]
        _reset(kept + pasted)
        ui.notify(f"Pasted {len(pasted)} stations.", type="positive")

    async def _apply() -> None:
        try:
            df = build_manual_survey(
                [(r["md"], r["inc"], r["azi"]) for r in rows], ref_toggle.value
            )
        except ValueError as exc:
            error.text = str(exc)
            return
        dlg.close()
        log.info("survey_entry.apply", stations=len(df), north_reference=ref_toggle.value)
        result = on_apply(df)
        if result is not None:
            await result

    grid.on("cellValueChanged", _on_edit)
    card.on("paste", _on_paste, js_handler=_PASTE_JS)

    def open_entry(initial: pd.DataFrame | None = None) -> None:
        values: list[tuple] = []
        if initial is not None and not initial.empty and {
            "MeasuredDepth", "Inclination", "Azimuth"
        } <= set(initial.columns):
            values = [
                (float(a), float(b), float(c))
                for a, b, c in initial[["MeasuredDepth", "Inclination", "Azimuth"]]
                .itertuples(index=False)
            ]
            nref = (initial.attrs.get("north_reference") or "").lower()
            if nref in ("true", "grid"):
                ref_toggle.value = nref
        _reset(values)
        dlg.open()

    return open_entry
