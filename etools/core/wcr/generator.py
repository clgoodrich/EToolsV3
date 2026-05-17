"""WCR Excel writer.

Output layout matches the legacy ``Reay_*_WCR.xlsx`` reference:

    Row 1-8  : well info pairs (col A label, col B value)
               + perforation summary in cols E-G (header + values)
    Row 10   : survey-points header (measured_depth, tvd, easting, ...,
                Section/Township/Range/Direction/Baseline)
    Row 11+  : key footage points (SHL, KOP, Landing, BHL)
    blank    :
    "Feature" header row
    rows     : casing+cement (Hole, Conductor, Surface, Intermediate,
                Production, ...) sorted by feature + bottom MD
    blank    :
    "Formation" header row
    rows     : formation tops from vwDM_ConstructPerf (Zone Type = Formation Top)

Numeric cells are written as numbers (not strings) so the recipient can
re-sort or compute on them.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from etools.logging_setup import get_logger
from etools.models import WCRBundle, WCRWellInfo

log = get_logger(__name__)


_BOLD = Font(bold=True)
_HEADER_FILL = PatternFill(start_color="E5E7EB", end_color="E5E7EB", fill_type="solid")
_NUMBER_FMT = "0.00"


def generate_wcr_excel(
    *,
    wcr_bundle: WCRBundle,
    summary_footages: pd.DataFrame,
    output_dir: str | Path,
    overwrite: bool = True,
) -> Path:
    """Write the WCR file. Returns the resulting Path.

    ``summary_footages`` is the dataframe produced by
    ``ClearanceService.calculate(...).summary`` — already keyed by location
    (SHL / KOP / Landing / BHL).
    """
    if wcr_bundle.info is None:
        raise ValueError("Cannot generate WCR: no well info available.")

    info = wcr_bundle.info
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = (info.well_name or info.api_well_no).replace(" ", "_").replace("/", "-")
    out_path = out_dir / f"{safe_name}_{info.api_well_no[:10]}_WCR.xlsx"
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"{out_path} already exists; set overwrite=True to replace.")

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet"

    _write_well_info(ws, info)
    _write_perf_summary_inline(ws, wcr_bundle.perforations)
    _write_footage_table(ws, summary_footages, start_row=10)
    next_row = max(15, ws.max_row) + 1
    next_row = _write_casing_table(ws, wcr_bundle.casing, start_row=next_row)
    next_row = _write_formation_tops(ws, wcr_bundle.perforations, start_row=next_row + 1)

    _autosize_columns(ws)
    wb.save(out_path)
    log.info("wcr.excel.saved", path=str(out_path))
    return out_path


# ---------------------------------------------------------------------------
# Section writers
# ---------------------------------------------------------------------------


def _write_well_info(ws, info: WCRWellInfo) -> None:
    pairs: list[tuple[str, object]] = [
        ("WellName", info.well_name),
        ("API", info.api_well_no[:10]),
        ("Operator", info.operator),
        ("Lateral", info.api_well_no[10:] or "0000"),
        ("WellType", info.well_type),
        ("SpudDate", _fmt_date(info.spud_date)),
        ("RotaryRigDate", _fmt_date(info.rotary_date)),
        ("TDReachedDate", _fmt_date(info.td_date)),
        ("CompletedOrAbandonedDate", _fmt_date(info.completion_date)),
        ("ProposedTVD_ft", info.proposed_tvd_ft),
        ("ProposedMD_ft", info.proposed_md_ft),
        ("Elevation_ft", info.elevation_ft),
    ]
    for r, (label, value) in enumerate(pairs, start=1):
        a = ws.cell(row=r, column=1, value=label)
        a.font = _BOLD
        ws.cell(row=r, column=2, value=value)


def _write_perf_summary_inline(ws, perforations: pd.DataFrame) -> None:
    """Replicate the legacy 'Perf Top / Perf Bottom / Perf Date' block in cols E-G."""
    if perforations.empty:
        return
    perf_only = perforations[perforations["ZoneType"] == "Perforations"].copy()
    if perf_only.empty:
        return
    h1, h2, h3 = ws.cell(row=1, column=5, value="Perf Top"), ws.cell(row=1, column=6, value="Perf Bottom"), ws.cell(row=1, column=7, value="Perf Date")
    for c in (h1, h2, h3):
        c.font = _BOLD
    for i, (_, row) in enumerate(perf_only.iterrows(), start=2):
        ws.cell(row=i, column=5, value=_to_num(row.get("Top_MD")))
        ws.cell(row=i, column=6, value=_to_num(row.get("Bottom_MD")))
        ws.cell(row=i, column=7, value=row.get("PerfDate") or "")


def _write_footage_table(ws, footages: pd.DataFrame, *, start_row: int) -> int:
    if footages.empty:
        return start_row

    # Header row
    headers = ["", "measured_depth", "tvd", "azimuth", "FNL", "FSL", "FEL", "FWL", "Section/Label"]
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=start_row, column=i, value=h)
        c.font = _BOLD
        c.fill = _HEADER_FILL
    # Body
    for r_offset, (_, row) in enumerate(footages.iterrows(), start=1):
        r = start_row + r_offset
        ws.cell(row=r, column=1, value=str(row.get("location", "")))
        ws.cell(row=r, column=2, value=_to_num(row.get("measured_depth")))
        ws.cell(row=r, column=3, value=None)  # tvd not always in summary; left blank
        ws.cell(row=r, column=4, value=_to_num(row.get("azimuth")))
        ws.cell(row=r, column=5, value=_to_num(row.get("FNL")))
        ws.cell(row=r, column=6, value=_to_num(row.get("FSL")))
        ws.cell(row=r, column=7, value=_to_num(row.get("FEL")))
        ws.cell(row=r, column=8, value=_to_num(row.get("FWL")))
        ws.cell(row=r, column=9, value=row.get("label") or "")
        for c in range(2, 9):
            cell = ws.cell(row=r, column=c)
            if isinstance(cell.value, (int, float)):
                cell.number_format = _NUMBER_FMT
    return start_row + len(footages) + 1


def _write_casing_table(ws, casing: pd.DataFrame, *, start_row: int) -> int:
    if casing.empty:
        return start_row
    headers = [
        "Feature", "Top", "Bottom", "Diam", "Weight", "Grade",
        "Connection Type", "Cement Top", "Cement Bottom", "Cement Type",
        "Sacks", "Yield", "Cement Weight",
    ]
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=start_row, column=i, value=h)
        c.font = _BOLD
        c.fill = _HEADER_FILL

    cols_map = [
        "Feature", "Top_MD", "Bottom_MD", "Diameter", "Weight", "Grade",
        "ConnectionType", "CementTop", "CementBottom", "CementType",
        "Sacks", "Yield", "CementWeight",
    ]
    for r_offset, (_, row) in enumerate(casing.iterrows(), start=1):
        r = start_row + r_offset
        for i, col in enumerate(cols_map, start=1):
            value = row.get(col)
            ws.cell(row=r, column=i, value=_to_num(value) if i in (2, 3, 4, 5, 8, 9, 11, 12, 13) else value)
    return start_row + len(casing) + 1


def _write_formation_tops(ws, perforations: pd.DataFrame, *, start_row: int) -> int:
    if perforations.empty:
        return start_row
    formations = perforations[perforations["ZoneType"] == "Formation Top"]
    if formations.empty:
        return start_row
    headers = ["Formation", "MD", "TVD"]
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=start_row, column=i, value=h)
        c.font = _BOLD
        c.fill = _HEADER_FILL
    for r_offset, (_, row) in enumerate(formations.iterrows(), start=1):
        r = start_row + r_offset
        ws.cell(row=r, column=1, value=str(row.get("Formation", "")).strip())
        ws.cell(row=r, column=2, value=_to_num(row.get("MD")))
        ws.cell(row=r, column=3, value=_to_num(row.get("TVD")))
    return start_row + len(formations) + 1


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fmt_date(d: datetime | None) -> str | None:
    return d.strftime("%Y-%m-%d") if isinstance(d, datetime) else None


def _to_num(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _autosize_columns(ws, max_width: int = 30) -> None:
    for col_idx in range(1, ws.max_column + 1):
        letter = get_column_letter(col_idx)
        longest = 0
        for cell in ws[letter]:
            if cell.value is None:
                continue
            longest = max(longest, len(str(cell.value)))
        ws.column_dimensions[letter].width = min(max(longest + 2, 10), max_width)
