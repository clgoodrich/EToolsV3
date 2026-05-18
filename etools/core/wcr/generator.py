"""WCR Excel writer.

Output schema (matches ``tests/South_Moon_5-31-32-C4-3H_4301353996_WCR.xlsx``):

    Row 1 :  WellName | <value>
    Row 2 :  API | <value>
    Row 3 :  Operator | <value>
    Row 4 :  WellType | <value>
    Row 5 :  SpudDate | <value>
    Row 6 :  RotaryRigDate | <value>
    Row 7 :  TDReachedDate | <value>
    Row 8 :  CompletedOrAbandonedDate | <value>
    Row 9 :  (header) MeasuredDepth | TVD | Easting | Northing | FNL | FSL |
             FEL | FWL | Section | Township | Township_Direction | Range |
             Range_Direction | Baseline
    Rows 10-14 : SHL | Control_Point | Frac_Start | Frac_End | BHL

All numbers are written as numbers (not strings).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook

from etools.logging_setup import get_logger
from etools.models import WCRLocationRow, WCRWellInfo

log = get_logger(__name__)


_INFO_LABELS: tuple[tuple[str, str], ...] = (
    ("WellName", "well_name"),
    ("API", "api_well_no"),
    ("Operator", "operator"),
    ("WellType", "well_type"),
    ("SpudDate", "spud_date"),
    ("RotaryRigDate", "rotary_date"),
    ("TDReachedDate", "td_date"),
    ("CompletedOrAbandonedDate", "completion_date"),
)

_FOOTAGE_HEADERS: tuple[str, ...] = (
    "",
    "MeasuredDepth",
    "TVD",
    "Easting",
    "Northing",
    "FNL",
    "FSL",
    "FEL",
    "FWL",
    "Section",
    "Township",
    "Township_Direction",
    "Range",
    "Range_Direction",
    "Baseline",
)

_LOCATION_ORDER: tuple[str, ...] = (
    "SHL",
    "Control_Point",
    "Frac_Start",
    "Frac_End",
    "BHL",
)


def generate_wcr_excel(
    *,
    info: WCRWellInfo,
    location_rows: Iterable[WCRLocationRow],
    output_path: str | Path,
) -> Path:
    """Write the WCR workbook to ``output_path``. Overwrites if it exists."""
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet"

    _write_info(ws, info)
    _write_headers(ws)

    by_name = {row.name: row for row in location_rows}
    for offset, name in enumerate(_LOCATION_ORDER):
        row = by_name.get(name)
        r = 10 + offset
        ws.cell(row=r, column=1, value=name)
        if row is None:
            continue
        _write_location(ws, row, r)

    wb.save(out_path)
    log.info("wcr.excel.saved", path=str(out_path))
    return out_path


# ---------------------------------------------------------------------------
# Section writers
# ---------------------------------------------------------------------------


def _write_info(ws, info: WCRWellInfo) -> None:
    api = (info.api_well_no or "")[:10]
    for r, (label, attr) in enumerate(_INFO_LABELS, start=1):
        ws.cell(row=r, column=1, value=label)
        value = api if attr == "api_well_no" else getattr(info, attr, None)
        ws.cell(row=r, column=2, value=_serialize(value))


def _write_headers(ws) -> None:
    for col, label in enumerate(_FOOTAGE_HEADERS, start=1):
        if label:  # leave column A header blank to match the reference output
            ws.cell(row=9, column=col, value=label)


def _write_location(ws, row: WCRLocationRow, r: int) -> None:
    ws.cell(row=r, column=2, value=_round(row.measured_depth, 0))
    ws.cell(row=r, column=3, value=_round(row.tvd, 2))
    ws.cell(row=r, column=4, value=_round(row.easting, 0))
    ws.cell(row=r, column=5, value=_round(row.northing, 0))
    ws.cell(row=r, column=6, value=_round(row.fnl, 2))
    ws.cell(row=r, column=7, value=_round(row.fsl, 2))
    ws.cell(row=r, column=8, value=_round(row.fel, 2))
    ws.cell(row=r, column=9, value=_round(row.fwl, 2))
    ws.cell(row=r, column=10, value=row.section)
    ws.cell(row=r, column=11, value=row.township)
    ws.cell(row=r, column=12, value=row.township_dir)
    ws.cell(row=r, column=13, value=row.range)
    ws.cell(row=r, column=14, value=row.range_dir)
    ws.cell(row=r, column=15, value=row.baseline)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _serialize(value):
    """Render dates as ``YYYY-MM-DD`` to match the reference output, pass everything else through."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def _round(value, ndigits: int):
    if value is None:
        return None
    try:
        rounded = round(float(value), ndigits)
        # Excel prefers integer when ndigits == 0
        return int(rounded) if ndigits == 0 else rounded
    except (TypeError, ValueError):
        return None
