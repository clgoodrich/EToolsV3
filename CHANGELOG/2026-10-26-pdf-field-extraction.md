# PDF parsing: slant, formation tops, frac gradient, collars, depths, lat/lon

- **Date:** 2026-10-26
- **Author:** Colton Goodrich (with Claude Code)
- **Commit(s):** see `git log --grep "pdf: read"`

## What changed
The APD parser now reads:
- the slant actually ticked on Form 3;
- the Drilling Program formation tops with their real depths;
- the frac gradient the permit prints;
- full connection names (STC/LTC/BTC).

The WCR parser no longer turns a blank TVD into the next section number. Survey
PDFs no longer report a target's (or a 0.0) lat/lon as the surface location.
The single-page vision transcription no longer crashes after the LLM call.

## Why
Each was reproduced on repo fixtures:
- **Slant.** Form 3 prints all three labels and marks the choice with a drawn
  dot, so the regex always returned "VERTICAL". Corpus: 77 permits were all
  "VERTICAL"; they are now 66 HORIZONTAL and 11 DIRECTIONAL.
- **Formation tops.** PyMuPDF's text order scatters the table, and the
  known-name fallback paired names with the next two numbers in the text. On
  Myton City 16-23 7H that gave `Lateral TD 3135/8238` and
  `Uteland Butte 7650/18592`. The reference Casing Review records
  Uinta 0 / Green River 3135 / Garden Gulch 5854 / Uteland Butte 8238.
- **Frac gradient.**
  - The header regex matched prose ("frac gradient of the casing shoe") and
    read an unrelated "8" as 8 ppg (0.4156 psi/ft, 7 permits).
  - The "1" of "4 1/2" or "1,900'" was read as 1.0 psi/ft (39 permits).
  - Permits stating "Frac gradient at … casing shoe = 12 ppg" were never read.
- **Collar.** `ST&C` was cut to `ST`, which gets the 1.5 premium tension
  threshold instead of STC's 1.8. `N-80 Buttress` was left as the grade, with
  no collar.
- **WCR Sections 24/25.** `\s*` crossed the newline, so a blank TVD read the
  "26" of "26. CURRENT WELL STATUS" (WCR 43047570050000).
- **Survey lat/lon.** The regex took the first number after any "Latitude" word,
  across newlines. On 13067_survey.pdf that was `0.0` or the PBHL target,
  about 1.8 km from the SHL.
- **Vision.** `len(doc)` was read after the `with fitz.open` block had closed
  the document.

## What was added
- `apd_parser._extract_slant_radio`: finds the filled radio dot beside the label.
- `apd_parser._formations_by_position`: reads the table by word coordinates.
  MD/TVD are assigned by an inline label or the nearest column header; the
  "CONFIDENTIAL" watermark and "TD" rows are dropped. When it finds the table it
  wins over the text-order readers (the geosteering list still wins if longer).
- `apd_parser._normalize_collar`, `wcr_parser._casing_row_has_data`.
- `tests/test_pdf_field_extraction.py`: 12 tests.

## What was changed / removed
- `_extract_frac_gradient`:
  - The prose statement wins when present.
  - The table header must be bare cells.
  - Fractions, thousands and feet tokens are stripped first.
  - Only the first four numbers after the header are considered.
- `_GRADE_THREAD_RE` accepts `&`, `-` and mixed case in the connection.
- The APD `MD:/TVD:` and WCR Section 24/25 regexes stay on one line; a blank
  TVD now gives `None`.
- `parser._LAT_DEC_RE` / `_LON_DEC_RE` require the value on the label's line and
  reject `0.0`.
- WCR `_extract_casing` no longer emits all-None rows, and `_merge_llm` lets the
  LLM fill features the rules left empty.
- `vision_transcribe_page` reads the page count inside the `with` block.

## Verification
- Before/after parse of all 235 APD PDFs under `tests/APD` in rules mode:
  - MD/TVD: unchanged.
  - Slant and collars: as described above.
  - 21 formation lists changed, each checked against its PDF. Myton 16-23 7H,
    16-23 1H and 4301353701 match their reference sheets.
  - Frac: 25 permits went from 1.0 to 0.9351 (they print 14/18/18 ppg), and 7 to
    0.7273 (they print 14 ppg). The prose-only permits now read their stated
    value; the rest have none (the engine's 1.0 default applies).
- `pytest tests/test_pdf_field_extraction.py`: 12 passed. Full suite green.

## Notes / follow-ups
- **Output change:** Myton 16-23 7H's Casing Review now uses 0.727 psi/ft (the
  permit's 14 ppg) instead of 1.0. The hand-made reference used 1.0, which
  equals the template default, not the permit.
- Survey PDFs whose surface lat/lon is only in a columnar block now return none,
  so supply the SHL (survey-tab override) or load from the DB.
- The BMSGW row is still added on sparse permits, as before, although the three
  reference sheets checked here don't include it.
