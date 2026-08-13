# Casing Review output correctness: formations, liner placement, editable tops

- **Date:** 2026-08-13
- **Author:** Colton Goodrich
- **Commit(s):** <filled after committing>

## What changed
Three output-correctness defects in the generated Casing Review workbook were
fixed, and the Formations tab became editable. The headline issue: **every
workbook ever generated carried the wrong well's formation tops.**

## Why
A cell-by-cell audit of `Casing Review_43013537270000_Myton City UT 16-23
3-2-25-36-7H.xlsx` against both the program's computed design and the
hand-made reference for the same well. The per-string engineering numbers all
matched exactly; the layout and formations did not.

## What was added
- **`writer.py: _write_formations()`** — writes the Formation Tops table
  (B = name, C = depth MD), depth-sorted, clearing unused rows. Always runs,
  even with an empty list. Wired through `casing_review_service.generate` via a
  new `formations=` argument on `write_casing_review`.
- **`domain.py: CasingStringDesign.block_index`** (`int | None`) — which
  STRING N block a string occupies, plus `top_depth_ft` and an `is_liner`
  property.
- **`writer.py: _block_of()`** — resolves a string's block, falling back to
  list position for hand-built designs.
- **`engine.py: _free_slot()`** — collision-safe slot allocation.
- **`apd_parser.py`** — `_BMSGW_RE`, `_extract_bmsgw_ft()`, `_with_bmsgw()`;
  new `APDPdfData.bmsgw_depth_ft`.
- **Formations tab** (`casing_review_tab.py`) — add / rename / edit MD / edit
  TVD / delete, auto-sorted by MD, with Top TVD interpolated from the loaded
  survey, and MD bounded (no negatives; no deeper than 110% of the survey's
  final MD, falling back to the APD's proposed MD).
- Generating the Excel now opens it in Excel (`_open_in_default_app`), plus an
  "Open in Excel" button on the result card.

## What was changed / removed
- **Stale template formations.** `templates/casing_review_template.xlsx` ships
  with a sample well's tops baked into `Formations!B3:C6` (Uinta 0 / Green
  River 3135 / Garden Gulch 5854 / Uteland Butte 8238 — Myton City's own), and
  nothing overwrote them. Every generated workbook inherited them regardless of
  well. Now always rewritten.
- **Production liner block placement.** `_TAG_TO_LABEL` chose the STRING block
  from the APD's tag text, and APDs tag a liner `Prod` like any other
  production casing, so liners landed in STRING 3. The hand-made reviews always
  put a liner in STRING 4 with STRING 3 empty. The slot is now decided by
  geometry (`length_top_ft > 0` ⇒ liner ⇒ STRING 4); everything else fills in
  order. Strings are sorted shallowest-first first, since 2 APDs list the
  casing table in reverse. As a side effect the **TOL row (row 69)**, which was
  silently blank, now populates (7896 ft MD for Myton City) and matches the
  reference.
- **BMSGW.** Added to the tops list only on sparse permits (≤6 tops) that state
  a depth — matching reviewer behavior (3/3 sparse references include it; 11/11
  full-geosteering references omit it, including two whose APDs *do* state a
  depth). Re-applied after the LLM merge, which replaces the list wholesale.

## Verification
- **Block layout vs. hand-made references: 9/9 match (was 0/9).**
- Corpus sweep, 82 APDs: 0 strings dropped, surface always block 0, 0 MD<TVD
  violations, 0 junk formation names.
- BMSGW: 5/5 correct — extracted 1,800 / 2,100 / 1,775 exactly matching the
  three references that carry it; omitted on the two rich-list wells.
- Per-well formations confirmed: Butcher Butte 19-134H-22 now writes its own 12
  tops (depths matching its reference) instead of Myton City's 4.
- MD guard: rejects negatives and >110%; boundary at exactly 110% allowed.
- `pytest tests/`: **132 passed**. `ruff check etools/`: clean.

## Notes / follow-ups
- A bug introduced during this work and caught before commit: `block_index`
  defaulted to `0`, which would have written every hand-built design's strings
  into STRING 1. Changed to `None` = unassigned; `test_bope` +
  `test_writer_sections` (16 tests) confirm the fallback.
- Rules-only formation extraction on the Myton permit is still weak
  (`Lateral TD 8238`, `Uteland Butte 18592`); the good list comes from the LLM
  path. This change fixed *delivery* of formations, not extraction quality
  there.
- openpyxl writes formulas with no cached value, so 224 formula cells in the
  Casing Review sheet are computed by Excel on open — pure-Python checks cannot
  verify what those render.
