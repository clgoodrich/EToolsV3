# Silent degradation that changes a regulatory workbook is now visible

- **Date:** 2026-08-25
- **Author:** Colton Goodrich
- **Commit(s):** 02b132f, (db-lookup notify commit)

## What changed

Two paths used to degrade quietly in ways that altered what gets submitted or
generated, with the only evidence in the server log. Both now say something.

A database failure while assembling a WCR no longer silently drops the casing
table out of the workbook. A failed survey lookup is no longer indistinguishable
from a well that genuinely has no survey on file.

## Why

Audit findings 7.B1 and 7.B3, ranked fourth in the failure-path review.

`_db_extras` (`wcr_pdf_service.py:309`) swallowed every exception at **`log.info`**
level and returned `(None, None)`. A momentary SQL Server outage therefore
produced a Form 8 with no casing table and no perforation date — and the same
button pressed a minute later produced a different workbook, with nothing on
screen to distinguish them.

The three DB survey lookups (`load_tab.py:290` and `:416`,
`casing_review_tab.py:449`) each did `log.warning` then a bare `return`. The user
could not tell an outage from "this well has no survey" — and that difference
decides whether every casing TVD comes from a real trajectory or from the
synthetic vertical welltrack.

## What was added

- **`tests/test_wcr_db_extras.py`** — 3 tests.
- **`tests/test_db_lookup_notifies.py`** — 2 parametrized tests that assert every
  DB-failure log marker has a `ui.notify` within its handler.

## What was changed / removed

- **`etools/services/wcr_pdf_service.py`** — `_db_extras` takes an optional
  `warnings` list, appends an explanation on failure, and logs at `warning` level
  with the API attached. Both call sites (`generate` at `:190` and
  `rewrite_excel` at `:270`) pass `pdf_data.warnings`.
- **`etools/ui/tabs/casing_review_tab.py`**, **`etools/ui/tabs/load_tab.py`** —
  the three DB survey-lookup failure branches now call `ui.notify` alongside the
  existing log line.

## Verification

- `tests/test_wcr_db_extras.py` — 3 passed (verified failing first with
  `TypeError: unexpected keyword argument 'warnings'`).
- `tests/test_db_lookup_notifies.py` — 2 passed (verified failing first).
- Full suite: **165 passed** in 8:38, exit 0.
- Confirmed `WCRPdfData.warnings` is a per-instance list under Pydantic v2 (not
  shared across instances) and is already rendered by the WCR tab at
  `wcr_tab.py:720`, so no new UI was required.

## Notes / follow-ups

- The "query succeeded but returned no rows" branches (`chosen is None`) were
  deliberately left silent — that is an ordinary answer, not a failure, and
  notifying on it would train the user to ignore the toast.
- `test_db_lookup_notifies.py` works by source inspection around known log
  markers. If a new DB-failure log event is added under a different name, add it
  to `FAILURE_MARKERS` — the test asserts at least one marker is found so a
  rename cannot silently disable it.
- Part of the failure-path hardening effort planned in
  `docs/superpowers/plans/2026-08-19-failure-path-hardening.md`.
