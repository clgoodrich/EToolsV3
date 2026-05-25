"""Write a fully-computed ``CasingDesign`` into the Casing Review xlsx.

Drops computed values into the Casing Review sheet AND the DataPrint
panel, so the workbook opens with every design factor already filled
in (the formulas still recompute when Excel opens the file — we just
don't depend on them).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import openpyxl

from etools.core.casing_review.domain import CasingDesign, CasingStringDesign
from etools.core.casing_review.generator import CASING_REVIEW_TEMPLATE


# Row offsets relative to each STRING block top (10, 25, 40, 55).
_DATA_ROW_OFFSET = 2  # row 12 / 27 / 42 / 57


def write_casing_review(
    design: CasingDesign,
    output_path: Path,
    *,
    template_path: Path | None = None,
    surface_location=None,
) -> Path:
    """Fill the Casing Review xlsx with both inputs and computed values.

    ``surface_location`` (an ``APDLocationRow`` for "Location At Surface")
    drives the SHL Section sheet's section/township/range/UTM block.
    """
    template_path = Path(template_path or CASING_REVIEW_TEMPLATE)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_path, output_path)

    wb = openpyxl.load_workbook(output_path)
    cr = wb["Casing Review"]

    # Header
    cr["B4"] = design.company
    cr["B5"] = design.well_name
    cr["B6"] = design.api
    cr["B9"] = design.frac_gradient_psi_per_ft

    block_tops = (10, 25, 40, 55)
    for idx, s in enumerate(design.strings[:4]):
        _write_block(cr, block_tops[idx], s, is_surface=idx == 0)

    # DataPrint panel mirrors per-string outputs into a normalized form.
    if "DataPrint" in wb.sheetnames:
        _write_dataprint(wb["DataPrint"], design)

    # SHL Section sheet — fill the well/API header and the surface
    # location's PLSS + UTM block. The rest of the sheet's formulas
    # resolve against the Grid Numbers reference.
    if "SHL Section" in wb.sheetnames:
        _write_shl_section(wb["SHL Section"], design, surface_location)

    wb.save(output_path)
    return output_path


def _write_shl_section(ws, design: CasingDesign, surface_location) -> None:
    """Populate the input block at the top of the SHL Section sheet.

    The sheet's downstream rows (KOP / Prod Interval / Total Depth)
    inherit from row 7 via cell references, so writing the surface row
    cascades through the whole sheet once Excel recomputes.
    """
    ws["C2"] = design.well_name
    ws["C3"] = design.api
    if surface_location is None:
        return
    # Section / Township / Range / Meridian — integer codes per the
    # Grid Numbers schema (twp 2=S 1=N, rng 2=W 1=E, mer 2=Uintah 1=SaltLake).
    if surface_location.section:
        try:
            ws["N7"] = int(surface_location.section)
        except ValueError:
            pass
    if surface_location.township:
        try:
            ws["O7"] = int(surface_location.township)
        except ValueError:
            pass
    if surface_location.township_dir:
        ws["P7"] = 2 if surface_location.township_dir.upper() == "S" else 1
    if surface_location.range:
        try:
            ws["Q7"] = int(surface_location.range)
        except ValueError:
            pass
    if surface_location.range_dir:
        ws["R7"] = 2 if surface_location.range_dir.upper() == "W" else 1
    if surface_location.meridian:
        ws["S7"] = 2 if surface_location.meridian.upper() == "U" else 1
    # UTM coordinates — left at template values when we don't have them.
    # The APD doesn't ship UTM; the WCR survey-PDF parser sets them on
    # ``WCRPdfData.surface_position`` and a future iteration can pipe
    # those through here.


def _write_block(ws, top: int, s: CasingStringDesign, *, is_surface: bool) -> None:
    data_row = top + _DATA_ROW_OFFSET

    def put(col: str, row: int, value) -> None:
        if value is None:
            return
        ws[f"{col}{row}"] = value

    # Inputs
    put("B", data_row, s.hole_size_in)
    put("C", data_row, s.od_in)
    put("D", data_row, s.set_depth_md_ft)
    put("E", data_row, s.weight_ppf)
    put("F", data_row, s.grade)
    put("G", data_row, s.collar)
    put("H", data_row, s.cement_lead_sacks)
    put("I", data_row, s.cement_lead_yield)
    put("J", data_row, s.cement_tail_sacks)
    put("K", data_row, s.cement_tail_yield)

    # Engineering knobs
    put("B", top + 7, "y" if s.buoyed else "n")
    put("B", top + 8, s.mud_weight_ppg)
    put("B", top + 10, s.hole_washout_pct)
    put("B", top + 11, s.internal_gradient_psi_per_ft)
    put("B", top + 12, s.backup_mud_ppg)
    put("B", top + 13, s.internal_mud_ppg)

    # Computed values — Excel formulas will recompute these on open, but
    # we pre-fill so the workbook shows correct numbers even if formulas
    # haven't refreshed (e.g. headless openpyxl reads).
    put("Q", data_row, s.cement_height_ft)
    put("R", data_row, s.top_of_cement_ft)
    put("S", data_row, s.masp_psi)
    put("T", data_row, s.collapse_psi)
    put("U", data_row, s.collapse_load_psi)
    put("V", data_row, s.collapse_df)
    put("W", data_row, s.burst_psi)
    put("X", data_row, s.burst_load_psi)
    put("Y", data_row, s.burst_df)
    put("Z", data_row, s.joint_klbs)
    put("AA", data_row, s.tension_df)
    put("AB", data_row, s.neutral_point_ft)
    put("AC", data_row, s.tension_air_klbs)
    put("AD", data_row, s.tension_buoyed_klbs)
    put("AE", data_row, s.id_in)


def _write_dataprint(ws, design: CasingDesign) -> None:
    """Write each string's normalized output into the DataPrint sheet.

    Column-range per string starts at column B (string 1), Q (string 2),
    AF (string 3), AU (string 4). The data rows start at row 11.
    """
    starts = ("B", "Q", "AF", "AU")
    for idx, s in enumerate(design.strings[:4]):
        col0 = starts[idx]
        # Row 7 carries the inch-prefix label, e.g. '9.625" Casing'.
        ws[f"{col0}7"] = f'{s.od_in}" Casing'
        # Row 11 starts the values; the spreadsheet repeats the per-stage
        # block but we just write the single shoe values for the lead row.
        row = 11
        _put(ws, col0, "C", row, s.masp_psi)
        _put(ws, col0, "D", row, s.collapse_psi)
        _put(ws, col0, "E", row, s.collapse_load_psi)
        _put(ws, col0, "F", row, s.collapse_df)
        _put(ws, col0, "G", row, s.burst_psi)
        _put(ws, col0, "H", row, s.burst_load_psi)
        _put(ws, col0, "I", row, s.burst_df)
        _put(ws, col0, "J", row, s.joint_klbs)
        _put(ws, col0, "K", row, s.tension_df)
        _put(ws, col0, "L", row, s.neutral_point_ft)
        _put(ws, col0, "M", row, s.tension_air_klbs)
        _put(ws, col0, "N", row, s.tension_buoyed_klbs)


def _put(ws, base_col: str, offset_col: str, row: int, value) -> None:
    """Write to (base_col + (offset_col - 'C') offset, row).

    The DataPrint panel uses C..N for the per-stage output columns within
    each string's block. We translate that to the string's starting column.
    """
    if value is None:
        return
    base_idx = openpyxl.utils.column_index_from_string(base_col)
    offset_idx = openpyxl.utils.column_index_from_string(offset_col)
    target = openpyxl.utils.get_column_letter(base_idx + offset_idx - 3)  # C is offset 0
    ws[f"{target}{row}"] = value
