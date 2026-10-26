# Loading a new well no longer inherits the previous well's data

- **Date:** 2026-10-26
- **Author:** Colton Goodrich (with Claude Code)
- **Commit(s):** see `git log --grep "per-well state"`

## What changed
Every way of bringing a well into the app (Load Well from DB, APD parse, WCR
parse, survey-PDF inject, APD/WCR promote) now starts from a complete, clean
slate for that well instead of overwriting only the fields it knows about.
"Clear all" now really clears everything. The Survey tab's **Process Survey** and
the Clearance tab's **Calculate Clearances** buttons run the same off-loop
pipeline as a load, so the server doesn't freeze and the downstream tabs update
with them.

## Why
Each load path hand-rolled its own reset list and each missed different fields,
so two wells' data mixed with nothing on screen to show it (reproduced while
writing the tests below):
- **Clear All** left the entire WCR side (`wcr_data`, `wcr_pdf_*`, `wcr_survey_*`)
  and `extra` loaded, even though its dialog promises to wipe "any PDF-parsed data".
- **Parsing a second APD** kept the previous well's `casing_overrides`,
  `bope_overrides`, `casing_last_output_path` and, when the DB had no survey for
  the new well, **its TVD survey** (`casing_survey_df`). The new permit's frac
  gradient was also ignored because the old well's value was still set.
- **DB load / survey-PDF inject** after an APD or WCR well kept that other
  well's parsed APD/WCR, so Casing Review and WCR showed the previous well.
- **Process Survey** replaced `state.processed` only. Clearances, section
  geometry and Map & Viz kept the previous survey's results. It also ran
  synchronously on the event loop and built a new dialog on every click.
  **Calculate Clearances** had the same blocking and dialog problems.

## What was added
- `etools/ui/workspace.py`: `begin_document(state, doc_id, keep=...)`, plus the
  `APD_FIELDS` / `WCR_FIELDS` families. It stashes the outgoing well into its
  buffer (including edits made after its last upsert) and rebuilds the live
  state from the incoming well's buffer, or empty if it has none. It carries
  over the `keep` fields and any APD/WCR family whose parsed API matches the
  incoming well, so APD + WCR + DB for one well still combine. It also clears
  `active_doc_id`, so a failed load can't be captured into the wrong buffer.
- 5 tests in `tests/test_workspace.py` covering: dropping the other well's
  fields, the outgoing buffer staying intact, keeping a matching family, the
  same-well no-op, and restoring the incoming well's buffer.

## What was changed / removed
- `app.py` `clear_all_state`: now `apply_document_data(state, empty_document_data())`
  (derived from `DOCUMENT_FIELDS`) instead of a hand list.
- `app.py` `load_handler`, `promote.py` `promote_apd_to_active` /
  `promote_wcr_to_active`, `pdf_tab.py` inject, `load_tab.py`
  `_parse_apd_now` / `_parse_wcr_now`: call `begin_document` before writing the
  new well.
- `survey_tab.process` / `clearance_tab.run`: now `async` and route through
  `state.post_load`. Removed their per-click dialogs and the now-unused service
  instances.

## Verification
- `pytest tests/test_workspace.py`: 12 passed (7 existing + 5 new).
- Full fast suite (everything but the slow South Moon WCR file): 180 passed.
- `ruff check --select F` clean on all touched files.

## Notes / follow-ups
- An APD parsed for a different well clears the screen's active well (it stays
  in the switcher) even if the permit can't be geolocated. That's intended: the
  alternative is the silent mix this fixes.
