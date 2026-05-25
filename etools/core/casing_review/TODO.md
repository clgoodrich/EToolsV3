# Casing Review — Deferred Work

This directory implements the foundations of the Casing Review engineering
review (parser, calc engine, catalog, template writer, UI). Several
sheets and features were scoped out of the initial build for time, and
are documented here so the next pass can pick them up.

## Pending implementation

### 1. Grid Numbers SQLite DB  (Task #28)
- **What**: Extract the `Grid Numbers` reference sheet (2,674 rows of
  per-section corner data) into a SQLite DB alongside `casing_catalog.sqlite`.
- **Why**: Drives SHL / BHL section sheet footage lookups. Without it
  those sheets stay at the template's original well's values.
- **How**: Mirror `tools/build_casing_catalog.py`. Schema:
  `(section, township, township_dir, range, range_dir, baseline,
    side, length_ft, degrees, minutes, seconds, alignment, north_ref)`.

### 2. Vertical Wellbore Diagram  (Task #33)
- **What**: Replace the static Excel chart on the `Vertical WBD` sheet
  with a computed Plotly figure showing concentric casings + cement
  columns + formation tops at correct depths.
- **Why**: User-facing visualisation in the UI; can also be embedded
  in the engineering review PDF.
- **How**: `etools/core/casing_review/wbd_renderer.py`. Plotly is
  already a project dependency. Output: SVG/PNG bytes for embedding,
  + an interactive HTML for the UI.

### 3. SHL + BHL Section sheets  (Task #34)
- **What**: Replicate the `SHL Section`, `BHL Section 1`, `BHL Section 2`,
  `BHL Section 3` sheets (each 156×82 cells of plat references) and
  extend to BHL Sections 4-8 per user requirement.
- **Why**: Engineering review needs per-section plat info to verify
  the location footages.
- **How**: Pull section corner data from the Grid Numbers DB, owner /
  lease info from PLSS shapefiles already loaded in `etools/core/plat`.

### 4. BOPE parser  (Task #31)
- **What**: Page-2 of every APD has a Blowout Prevention Equipment
  block (ram preventer ratings, choke manifold, FIT, MIRU). Currently
  we don't parse it.
- **Why**: Required to populate the `BOPE` sheet of the Casing Review.
- **How**: New `_extract_bope()` in `apd_parser.py`; add `bope:
  APDBOPE` field to `APDPdfData`.

### 5. Exact-match burst-load formula
- **What**: My burst-load formula matches the spreadsheet's surface
  string to within 0.5%, but diverges on intermediate / production
  because the spreadsheet has more elaborate `MIN(I, L)` branching.
- **Why**: Engineering accuracy. Currently OK for screening — must
  reconcile before official engineering submissions.
- **How**: Re-derive the spreadsheet's `X12` / `X27` / `X42` formulas
  cell-by-cell and translate to `CasingStringDesign.burst_load_psi`.
  The structure is in the workbook's column header pre-computation
  (rows `$I$24`, `$L$24`, `$F$24` for each block).

### 6. DxSurvey-driven bottom-block lookups
- **What**: The `DxSurvey` sheet at the bottom carries computed
  Surface / Prod Interval / TD lat-long footages. We don't write
  those today.
- **Why**: Lets the engineering reviewer see real-world coordinates
  next to the PLSS footages.
- **How**: Once survey is loaded, compute via `welleng` min-curvature
  + project to UTM, write into the `DxSurvey` rows 44-50 block in
  `writer.py`.
