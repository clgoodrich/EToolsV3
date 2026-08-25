# Resource leaks: PDF handles and temp uploads

- **Date:** 2026-08-25
- **Author:** Colton Goodrich
- **Commit(s):** 4473353, (upload-temp commit)

## What changed

Parsing a PDF no longer leaks a file handle, and uploaded PDFs no longer
accumulate in the OS temp directory forever. Startup sweeps this app's own
leftovers.

## Why

Audit finding 7.E. Lowest severity in the ranking, but both leaks were unbounded.

No `doc.close()` existed anywhere in `parser.py`, `apd_parser.py`,
`wcr_parser.py` or `ddr_parser.py` — the sole exception was
`wcr_parser._slice_pdf`. Every parse leaked a handle until GC, and on Windows an
open `fitz` Document keeps the file **locked**, which is what would have made the
temp sweep below fail on every run.

All four tabs carried a byte-identical `_save_upload` using
`NamedTemporaryFile(delete=False)`, and a grep for `unlink` / `os.remove` /
`TemporaryDirectory` across `etools/` returned nothing. `wcr_parser._slice_pdf`
states the situation plainly in its own docstring: *"We don't bother cleaning up
the temp file; OS will eventually."*

## What was added

- **`etools/ui/upload_temp.py`** — `save_upload()` (one shared implementation,
  writing under an `etools-upload-` prefix) and `sweep_stale_uploads()`.
- **`tests/test_pdf_handles.py`** (5) and **`tests/test_upload_temp.py`** (5).

## What was changed / removed

- All seven `fitz.open` sites across the four parsers converted to `with`
  blocks. `parser._pymupdf_extract_text` uses a bare `with doc:` because its
  open sits in its own `try` that returns `""` on failure.
- Deleted the four duplicated `_save_upload` functions; each tab imports the
  shared one under the same private name, so no call site changed. Removing them
  orphaned five imports (`tempfile` ×4, `pathlib.Path` ×1), cleaned up by ruff.
- **`etools/main.py`** — `run()` sweeps stale uploads at startup.

## Verification

- New tests: 10 passed, each verified failing first.
- Full suite: **212 passed** in 8:24, exit 0 — including `test_wcr_south_moon`,
  which parses a real PDF end to end.
- Handle release verified against `tests/APD/13067_survey.pdf`: 26,245 chars
  extracted, and the file deletes immediately afterwards with **no**
  `gc.collect()`.
- Sweep round trip verified: a saved upload carries the prefix, fresh files are
  kept, a back-dated file is removed, a bystander file in the same directory is
  untouched, and a locked file does not raise.
- `ruff check etools/` — all checks passed across the whole package.

## Notes / follow-ups

- **Sweeping by age, not deleting after parse.** `state.apd_pdf_path` is retained
  and re-read when the user regenerates without re-uploading; delete-on-parse
  would break that flow. Default window is 24 hours.
- The sweep only ever removes files carrying its own `etools-upload-` prefix. It
  must never be broadened to a bare `*.pdf` glob over the temp directory.
- Task 15 (handle closing) is a **prerequisite** for this, not an independent
  fix: without deterministic closing the sweep would hit locked files every run.
- Part of the failure-path hardening effort planned in
  `docs/superpowers/plans/2026-08-19-failure-path-hardening.md`.
