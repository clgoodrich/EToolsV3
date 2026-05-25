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
from etools.core.casing_review.footages import (
    footages_to_xy,
    location_footages,
    polygon_footages,
)
from etools.core.casing_review.generator import CASING_REVIEW_TEMPLATE
from etools.logging_setup import get_logger

log = get_logger(__name__)


# Row offsets relative to each STRING block top (10, 25, 40, 55).
_DATA_ROW_OFFSET = 2  # row 12 / 27 / 42 / 57


def write_casing_review(
    design: CasingDesign,
    output_path: Path,
    *,
    template_path: Path | None = None,
    surface_location=None,
    producing_interval_location=None,
    td_location=None,
    intermediate_locations: list | None = None,
    plat_repo=None,
) -> Path:
    """Fill the Casing Review xlsx with both inputs and computed values.

    Section-sheet inputs:
        * ``surface_location``              → SHL Section (PLSS + UTM block)
        * ``producing_interval_location``   → BHL Section 1
        * ``td_location``                   → BHL Section 3
                                              (BHL 2 left blank for an
                                              intermediate-section pass,
                                              wired in when clearance data
                                              is plumbed through)

    All three are ``APDLocationRow`` instances from
    ``APDPdfData.locations`` (Section 20 of the Form 3).
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

    # SHL + BHL Section sheets. Each section sheet's row-7 input block
    # drives every formula in that sheet via Grid-Numbers DGET lookups.
    #
    # Layout: SHL = surface, BHL 1 = top of producing zone, BHL 3 = TD.
    # ``intermediate_locations`` slots into BHL 2 (first item) and any
    # additional items create BHL Section 4, 5, 6, ... by duplicating
    # the BHL Section 3 sheet as a template.
    intermediate_locations = list(intermediate_locations or [])
    bhl2_loc = intermediate_locations[0] if intermediate_locations else None
    extra_locs = intermediate_locations[1:]

    section_sheet_map = [
        ("SHL Section",   surface_location),
        ("BHL Section 1", producing_interval_location),
        ("BHL Section 2", bhl2_loc),
        ("BHL Section 3", td_location),
    ]
    for sheet_name, location in section_sheet_map:
        if sheet_name in wb.sheetnames:
            _write_section_sheet(
                wb[sheet_name],
                design,
                location,
                sheet_label=sheet_name,
                plat_repo=plat_repo,
            )

    # Dynamic BHL Section 4+ for wells that cross more sections than
    # the template ships with. Copy the BHL Section 3 sheet (which
    # already has the full formula structure) and rename.
    if extra_locs and "BHL Section 3" in wb.sheetnames:
        template_sheet = wb["BHL Section 3"]
        for i, loc in enumerate(extra_locs, start=4):
            new_name = f"BHL Section {i}"
            if new_name in wb.sheetnames:
                continue  # don't clobber an existing sheet
            new_sheet = wb.copy_worksheet(template_sheet)
            new_sheet.title = new_name
            _write_section_sheet(
                new_sheet,
                design,
                loc,
                sheet_label=new_name,
                plat_repo=plat_repo,
            )
            log.info("section_sheet.created_dynamic", name=new_name)

    wb.save(output_path)
    return output_path


def _write_section_sheet(
    ws,
    design: CasingDesign,
    location,
    *,
    sheet_label: str,
    plat_repo=None,
) -> None:
    """Populate the well/API header, the PLSS input block at row 7, and
    the computed UTM coordinates (T7/U7/V7) for the location.

    ``plat_repo`` is an optional ``PlatRepository`` — when provided, we
    look up the section polygon and derive UTM from the APD footages
    via shapely geometry. With no plat polygon available the UTM cells
    stay at the template default.
    """
    ws["C2"] = design.well_name
    ws["C3"] = design.api
    if location is None:
        return

    # Section / Township / Range / Meridian — integer codes per the
    # Grid Numbers schema (twp 2=S 1=N, rng 2=W 1=E, mer 2=Uintah 1=SaltLake).
    if location.section:
        try:
            ws["N7"] = int(location.section)
        except ValueError:
            pass
    if location.township:
        try:
            ws["O7"] = int(location.township)
        except ValueError:
            pass
    if location.township_dir:
        ws["P7"] = 2 if location.township_dir.upper() == "S" else 1
    if location.range:
        try:
            ws["Q7"] = int(location.range)
        except ValueError:
            pass
    if location.range_dir:
        ws["R7"] = 2 if location.range_dir.upper() == "W" else 1
    if location.meridian:
        ws["S7"] = 2 if location.meridian.upper() == "U" else 1

    # Compute UTM from the APD's footages + the plat polygon. We also
    # write the four cardinal footages back into I7/K7 — those are
    # formula cells in the template referencing DxSurvey, but the user
    # wants the actual APD footages here.
    if plat_repo is None:
        return
    try:
        conc = _location_to_conc(location)
        if conc is None:
            return
        df = plat_repo._fetch_concs([conc])  # noqa: SLF001 — direct lookup
        if df.empty:
            log.info("section_sheet.plat_miss", sheet=sheet_label, conc=conc)
            return
        gdf = plat_repo._build_sections(df)  # noqa: SLF001
        if gdf.empty:
            return
        polygon = gdf.iloc[0].geometry
        fnl, fsl, fel, fwl = location_footages(location)
        if (fnl is None and fsl is None) or (fel is None and fwl is None):
            return
        x, y = footages_to_xy(polygon, fnl=fnl, fsl=fsl, fel=fel, fwl=fwl)
        ws["T7"] = round(x, 3)
        ws["U7"] = round(y, 3)
        ws["V7"] = 12  # UTM zone 12 for Utah

        # Also fill the four "Section Line Footages" cells so the user
        # sees the APD footages instead of the template's DxSurvey ref.
        # I7 = FNL or FSL (numeric); J7 = 1 if FNL, 2 if FSL
        # K7 = FEL or FWL (numeric); L7 = 1 if FEL, 2 if FWL
        if fnl is not None:
            ws["I7"] = fnl
            ws["J7"] = 1
        elif fsl is not None:
            ws["I7"] = fsl
            ws["J7"] = 2
        if fel is not None:
            ws["K7"] = fel
            ws["L7"] = 1
        elif fwl is not None:
            ws["K7"] = fwl
            ws["L7"] = 2
        log.info(
            "section_sheet.utm_written",
            sheet=sheet_label,
            conc=conc,
            utm=(round(x, 1), round(y, 1)),
        )
    except Exception as exc:
        log.warning(
            "section_sheet.utm_failed",
            sheet=sheet_label,
            location=location.name,
            error=str(exc),
        )


def _location_to_conc(location) -> str | None:
    """Build the 9-char Conc PLSS code (matches PlatRepository.BaseData).

    Format: ``"SSTTDRRRDDM"`` (2+2+1+2+1+1) → e.g. ``"2303S02WU"``.
    """
    try:
        sec = int(location.section)
        twp = int(location.township)
        rng = int(location.range)
    except (TypeError, ValueError):
        return None
    twpd = (location.township_dir or "").upper()
    rngd = (location.range_dir or "").upper()
    mer = (location.meridian or "").upper()
    if twpd not in ("N", "S") or rngd not in ("E", "W") or not mer:
        return None
    return f"{sec:02d}{twp:02d}{twpd}{rng:02d}{rngd}{mer}"


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
