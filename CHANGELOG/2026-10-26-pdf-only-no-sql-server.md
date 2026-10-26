# No more SQL Server: every well value comes from the PDFs

- **Date:** 2026-10-26
- **Author:** Colton Goodrich (with Claude Code)
- **Commit(s):** see `git log --grep "no SQL Server"`

## What changed
ETools no longer connects to any database server. Everything it used to fetch
from `UTRBDMSNET` is now read from the PDFs themselves:

| Used to come from SQL Server | Now comes from |
|---|---|
| Directional survey (APD route) | The APD's own directional-plan table |
| Directional survey (WCR route) | The as-drilled survey report attached to the WCR, or an uploaded survey PDF |
| Survey north reference | The "North Reference:" value printed on the survey pages |
| WCR workbook casing table | WCR Sections 28 (hole, casing, cement) and 29 (tubing) |
| WCR workbook perforation date | WCR Section 35 treatment start date |
| Tracking sundry number | The WCR page stamp ("Sundry Number: …") |
| Tracking date filed | A new editable field, pre-filled from the WCR's RECEIVED stamp |

The reference data was already local: PLSS sections, Grid Numbers and casing
strengths.

Removed: the WCR tab's Legacy flow, the old "load a well from the database"
path (which already had no button), the SQL Server repositories, `WellService`
and `WCRService`, the `ETOOLS_DB__*` settings and the `pyodbc` dependency.

## Why
Requested: data should come only from the PDF or the local bundled databases.
The portable copy now runs on any PC without SQL Server.

## Accuracy (checked against the DB before removing it)
- **Surveys:** 25 fixture PDFs carry a survey table. All 25 matched the DB
  station for station (inclination error 0.000°); the PDF often has 3–6 extra
  tie-in/casing-point stations. The north reference matched the DB on all 26
  PDFs that have one, including the GRID surveys the old text rule misread as
  true. 41 of the 63 fixture WCRs don't carry their survey at all; for those
  you upload the survey PDF, as before when the DB had none.
- **Casing/cement:** 264 of 277 DB casing rows reproduced exactly. Of the rest,
  4 are empty DB placeholder rows; the others are where the form and the DB
  disagree (e.g. 540 vs 550 sacks, or a "1740" typed on the form where the DB
  has 17,638). The workbook shows what the form says.
- **Perforation date:** the Section 35 start date equals the DB's perforation
  date (e.g. 7/4/2024 on South Moon).
- **Sundry number:** matches the DB wherever both exist (one well's DB has a
  later sundry).
- **Date filed:** RECEIVED is DOGM's received stamp, usually a few days to a few
  weeks after the operator's submit date, hence the editable field.

## What was added
- `etools/core/pdf/survey_table.py`: `extract_survey_table` (survey table read
  by word position, plus north reference) and `survey_from_pdf` (falls back to
  the older text rules).
- `etools/core/pdf/wcr_form.py`: `extract_casing` (Sections 28/29),
  `casing_frame`, `extract_stamp`, `extract_treatment_start`.
- `WCRPdfData.sundry_no` / `received_date` / `treatment_start_date`,
  `CasingRow.hole_size` / `cement_stage`.
- `tests/test_pdf_only_sources.py` (9 tests);
  `tests/fixtures/surveys/4301353996_AsDrilled_True.csv`, the South Moon survey
  exported before removal (that WCR doesn't carry it).

## What was changed / removed
- `load_tab`: after an APD/WCR parse, the survey is read from the PDF.
- `wcr_tab`: the Legacy flow and the DB lookup were removed. Tracking uses the
  PDF sundry number and the new "Date filed" field.
- `casing_review_tab`: the unused DB lookup was removed.
- `wcr_pdf_service._pdf_extras` replaces `_db_extras`.
- `parser.parse_survey_pdf`: the position-based table reader runs first (fast,
  exact); Docling/OCR/LLM only run when it finds nothing.
- `wcr_parser`:
  - `_PADDED_DATE_RE` no longer spans line breaks. It used to glue neighbouring
    cells into dates, e.g. "19202" + "07/04/2024" became
    "1920 207/04/20240 7 / …".
  - The empty-row Section 28 text reader was replaced.
- Deleted `repositories/{survey,well,wcr}.py`, `services/{well,wcr}_service.py`,
  the SQL Server engine (`db/session.py` keeps only SQLite), `DatabaseConfig`,
  and the DB-only tests.
- Updated `.env.example`, `pyproject.toml`, `build_portable.ps1`, the README,
  the portable README and the in-app Help guide.
- Updated `scripts/compare_apd_batch.py`, `diag_bope_next.py`,
  `verify_four_points.py` (APD survey from the PDF) and `compare_wcr.py`
  (South Moon from the fixture; Reay removed, since it had only a DB path).

## Verification
- Before/after scoring against the DB, as above.
- In the running app with no database code:
  - Myton City 16-23 7H APD gave "APD PDF / Planned (194 stations)" and was
    promoted.
  - Wild 74-3328-22G WCR gave "WCR PDF / As-Drilled (222 stations)", was
    promoted, and generated a workbook with the perforation date and full casing
    table. Date filed was pre-filled as 8/19/2024.
- Full test suite (see commit).

## Notes / follow-ups
- WCRs without an attached survey need the survey PDF uploaded.
- Scanned (image-only) survey pages still go through OCR/vision AI, which the
  portable bundle doesn't ship (no vision model).
