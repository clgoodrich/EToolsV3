# Formations tab, APD formation extraction rewrite & Load-Well cleanup

- **Date:** 2026-08-13
- **Author:** Colton Goodrich
- **Commit(s):** <filled after committing>

## What changed
Casing Review now surfaces geological formation tops as a dedicated **Formations**
navigation tab, the APD parser reliably extracts those tops across the full test
corpus, the WCR view shows a formations table, the deprecated "From Database"
on-ramp was removed from Load Well, and the portable bundle was refreshed to carry
all of it.

## Why
- Formation detection existed but had no first-class UI — the tops rendered only at
  the bottom of the parsed-APD view and were easy to miss. The user asked for a
  proper tab.
- The whitelist-only extractor returned `[]` for several real APDs
  (e.g. `application_43013537460000 Check.pdf` — 0 formations despite a clear page-2
  table) because operator-specific formation names weren't in the hardcoded list.
- The "From Database" Load-Well on-ramp (API + lateral lookup) was deprecated.

## What was added
- **`etools/ui/tabs/casing_review_tab.py`** — a top-level `Formations` tab
  (`ui.tab("Formations", icon="layers")`), its panel, visibility wiring, and a new
  `_render_formations(card, data)` renderer showing a `#/Formation/Top MD/Top TVD`
  table (with an explicit empty state).
- **`etools/ui/tabs/wcr_tab.py`** — a "Section 32 — formation tops" table below the
  well-info grid, always-visible header plus empty state.
- **`etools/core/pdf/apd_parser.py`** — three complementary formation parsers plus a
  quality gate:
  - `_extract_formations_tops_table` (page-2 FORMATION TOPS table),
  - `_extract_formations_geosteering` (geosteering plan table),
  - `_extract_formations_known` (name whitelist, as a fallback),
  - `_plausible_formation_name` + `_finalize_formations` (drop junk names, enforce
    `MD ≥ TVD` via min/max), and `_extract_formations` picks the longest *clean*
    candidate list.

## What was changed / removed
- **`etools/ui/tabs/load_tab.py`** — removed the `From Database` sub-tab and its whole
  panel (API/lateral inputs, `submit_db`, "Load Well" button); sub-tabs now default to
  **From APD PDF**; docstring/intro updated "three on-ramps" → "two on-ramps";
  `on_load` made optional so `etools/ui/app.py` needs no change. The post-parse DB
  survey auto-lookups (`_try_db_survey_for_apd` / `_try_db_survey_for_wcr`) were
  deliberately kept — they are not the deprecated on-ramp.
- Formations block was removed from `_render_meta` to avoid duplication with the new
  tab.

## Verification
- Full APD sweep (rules mode): **77 files, 0 MD<TVD violations, 0 junk rows, 2 empty,
  median 12 formations, max 15**.
- Target well `application_43013537460000 Check.pdf`: **0 → 12 formations**, all
  `MD ≥ TVD`.
- Related pytest: **4 passed, 128 deselected**, exit 0.
- All touched modules import cleanly under the project `.venv`.
- Portable bundle: app source mirrored via robocopy `/MIR` (14 files updated,
  0 failed); `compileall` under the embedded interpreter → exit 0; verified
  `From Database` absent and `formations_tab` present in the bundle copies.

## Notes / follow-ups
- The Ollama backfill path (`mode="rules+llm"`) is slow (~240s) and its 2048-token
  cap can truncate JSON; rules-only extraction is what produced the results above.
- The portable `.env` sets `ETOOLS_LLM__ENABLED=true`, so the portable app takes the
  slower `rules+llm` path on APD load.
