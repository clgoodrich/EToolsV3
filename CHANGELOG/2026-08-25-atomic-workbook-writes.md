# Atomic workbook writes: a failed generation no longer destroys the previous one

- **Date:** 2026-08-25
- **Author:** Colton Goodrich
- **Commit(s):** 731dbf5, (write-error message commit)

## What changed

Generating a workbook used to overwrite the destination as its *first* action.
From that moment the previously generated, reviewed workbook no longer existed —
so any failure part-way through left a blank template on disk while the UI
reported only "Generation failed", saying nothing about the file having been
replaced.

All four workbook writers now build at a sibling temp file and swap it into
place only once the write has completed. A failure leaves the existing workbook
byte-identical. Write failures also now name the cause: the overwhelmingly
common one is the file being open in Excel, and the message says so.

## Why

Audit findings 7.A2 and 7.A3, ranked second in the failure-path review.
`writer.py:68` did `shutil.copyfile(template, output_path)` and only called
`wb.save(output_path)` about 90 lines later, with almost none of the `_write_*`
helpers guarded in between.

7.A3 compounds it: the output filename is deterministic
(`casing_review_service.py:123-127`, no timestamp) and every successful
generation auto-opens the file in Excel (`casing_review_tab.py:586-589`). The
ordinary generate → tweak → generate loop therefore targets a path Excel is
holding open.

## What was added

- **`etools/core/io_safety.py`** — `atomic_output()` (context manager yielding a
  sibling temp path, `os.replace`d into position on clean exit) and
  `describe_write_error()`.
- **`tests/test_io_safety.py`** — 9 tests.

## What was changed / removed

- **`etools/core/casing_review/writer.py`**, **`.../generator.py`**,
  **`etools/core/wcr/generator.py`**, **`etools/services/tracking_service.py`** —
  each public writer became a thin wrapper around a renamed `_..._to()` private
  function, so no existing function body was re-indented or edited. The tracking
  wrapper additionally seeds the temp file from the existing workbook, because
  that updater loads-or-creates from its own target and would otherwise drop all
  prior rows.
- **`etools/ui/tabs/casing_review_tab.py`** and **`.../wcr_tab.py`** — write
  failures route through `describe_write_error` when the exception is an
  `OSError`. Adds `_wcr_output_hint()` for the WCR generate path, which fails
  before it has a result path in scope.

## Verification

- `tests/test_io_safety.py` — 9 passed (verified failing first).
- Full suite: **153 passed** in 8:28, exit 0.
- A `FileNotFoundError` mid-generation left a sentinel file byte-identical, with
  no orphaned temp file. Before the change it became a copied template.
- A real generation still emits all 15 sheets to the correct final path.
- Against a genuinely locked file (`msvcrt.locking`), three consecutive blocked
  attempts produced the actionable message, left the file intact, and orphaned
  nothing.

## Notes / follow-ups

- **Windows limitation, deliberate:** `os.replace` onto a file Excel holds open
  still raises `PermissionError`. This change does *not* make the write succeed —
  it guarantees the existing file survives the failure and the user is told why.
- **A leak was found in `atomic_output` during verification.** `os.replace` was
  initially outside the cleanup path, so every save blocked by an open Excel file
  — the most common failure of all — orphaned a partial file. The unit tests
  passed; only running it against a genuinely locked workbook exposed it. Now
  guarded, with a regression test.
- Part of the failure-path hardening effort planned in
  `docs/superpowers/plans/2026-08-19-failure-path-hardening.md`.
