# Load Well off the event loop, WCR repaint feedback, zero-length bearings

- **Date:** 2026-08-25
- **Author:** Colton Goodrich
- **Commit(s):** a3650f3, 8f3a75d, (bearing commit)

## What changed

An unreachable database no longer freezes the whole app while you wait for the
error. A WCR recalculation that only half-repaints now says so. And a section
boundary with no length no longer reports a confident bearing due north.

## Why

Audit findings 7.C4 (ranked #6), 7.D4 and 7.B6.

**7.C4** — `load_handler` (`app.py:534`) called `service.load(lookup)` directly
on the event loop. `pyodbc`'s connect is blocking, so an unreachable SQL Server
froze the entire NiceGUI server — for every connected client — for the full ODBC
timeout before the error toast could appear. Every other DB call site in the UI
already used `asyncio.to_thread`; this was the sole exception.

**7.D4** — `recalculate_edits` swapped `result.location_rows` to the recomputed
values, then updated the on-screen labels in a loop whose per-row handler was a
bare `log.debug`. A disposed widget skipped its row, leaving the visible grid
showing old values while the export already used the new ones.

**7.B6** — `_bearing_to_dms_alignment` computes `atan2(d_east, d_north)`. When a
boundary genuinely has no length both deltas are zero, `atan2(0, 0)` returns
exactly `0.0`, and that was emitted as a real bearing due north.

## What was added

- **`tests/test_load_handler_offloads.py`** (3),
  **`tests/test_wcr_recalculate_feedback.py`** (4),
  **`tests/test_grid_bearing_guards.py`** (5).
- `_MIN_BOUNDARY_LEN_M = 1e-6` and a module logger in `grid_corners.py`.

## What was changed / removed

- **`etools/ui/app.py`** — `bundle = await asyncio.to_thread(service.load, lookup)`;
  `asyncio` promoted to a module-scope import.
- **`etools/ui/tabs/wcr_tab.py`** — counts rows that failed to repaint and raises
  one `ui.notify` stating the values are saved and will be used in the export.
- **`etools/core/casing_review/grid_corners.py`** — returns
  `(None, None, None, None)` for a boundary shorter than `_MIN_BOUNDARY_LEN_M`.

## Verification

- New tests: 12 passed, each verified failing first.
- Full suite: **224 passed** in 8:32, exit 0.
- `ruff check etools/` — clean across the package.
- `WellNotFoundError` confirmed to still route to its friendly warning branch
  through `to_thread`, and the event loop confirmed responsive (7 timer ticks)
  during a simulated blocking call.

## Notes / follow-ups

- **This changes real output.** Checked against the live plat database rather
  than synthetic fixtures: across **2,000 real Utah sections / 31,968 derived
  corners, 25 zero-length boundaries hit the new guard** (~0.3% of bearing
  calls). Those 25 previously wrote a fabricated `0°` due-north bearing into the
  Grid Numbers sheet and now write a blank cell. `GridCorner`'s dms fields were
  already `int | None`, so nothing downstream changed and the caller's 4-tuple
  unpack is unaffected; openpyxl keeps a blank cell distinguishable from a
  genuine `0`. A fabricated bearing is a wrong answer and a blank is an honest
  one, but this is a visible change worth a look before it reaches a submitted
  workbook.
- `result.location_rows = new_rows` was deliberately left where it is: the
  recompute succeeded, so the data model should advance. The defect was silence
  about the display falling behind it.
- Part of the failure-path hardening effort planned in
  `docs/superpowers/plans/2026-08-19-failure-path-hardening.md`.
