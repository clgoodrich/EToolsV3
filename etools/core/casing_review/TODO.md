# Casing Review — Deferred Work

This directory implements the Casing Review engineering review (parser,
calc engine, catalog, template writer, BOPE, wellbore diagram, UI).
Most of the originally deferred items have since landed:

- Grid Numbers SQLite DB → `grid_corners.py` + `scripts/build_grid_numbers_db.py`
- Vertical wellbore diagram → `wbd.py` (`render_wellbore_figure`, used by the UI)
- SHL/BHL section sheets → `sections.py` + `writer.py` (provisions up to BHL 7)
- BOPE parsing + sheet → `_extract_bope()` in `apd_parser.py`, `bope.py`, BOPE tab
- DxSurvey bottom-block lookups → `_write_dx_survey_locations` in `writer.py`

## Still pending

### Exact-match burst-load formula
- **What**: The burst-load formula (`domain.py::burst_load_psi`) matches the
  spreadsheet's surface string to within 0.5%, but diverges on intermediate /
  production because the spreadsheet has more elaborate `MIN(I, L)` branching.
- **Why**: Engineering accuracy. Currently OK for screening — must
  reconcile before official engineering submissions.
- **How**: Re-derive the spreadsheet's `X12` / `X27` / `X42` formulas
  cell-by-cell and translate to `CasingStringDesign.burst_load_psi`.
  The structure is in the workbook's column header pre-computation
  (rows `$I$24`, `$L$24`, `$F$24` for each block).
