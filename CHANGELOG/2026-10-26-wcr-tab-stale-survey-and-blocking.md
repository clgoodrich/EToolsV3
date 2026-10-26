# WCR tab: no stale survey, no event-loop DB calls, right well in tracking

- **Date:** 2026-10-26
- **Author:** Colton Goodrich (with Claude Code)
- **Commit(s):** see `git log --grep "wcr-tab"`

## What changed
Three fixes on the WCR tab:
- Parsing a new WCR now drops the survey the tab had resolved for the previous
  one.
- The legacy DB bundle loads in a worker thread, once per well.
- "Update Personal Record" logs the WCR on screen, and does its DB lookup and
  workbook write off the event loop.

## Why
- `refresh()` kept `cache["surveys"]` whenever the new well had no DB survey, so
  Generate stayed enabled and built well B's workbook from well A's trajectory
  (confirmed by the audit's UI harness).
- `refresh()` discarded the legacy bundle on every call and reloaded it with
  three synchronous pyodbc queries. That cost 0.26 s per refresh with the DB up
  and about 20 s per refresh with it down, for every connected client.
- `update_personal_record` preferred `state.primary`, so a WCR that couldn't
  auto-promote was logged under whichever DB well was active.

## What was added
- `_bundle_is_current`, `_load_then_rerender` and a "Loading WCR data…" state in
  the legacy section.

## What was changed / removed
- `wcr_tab.py`: `refresh()` resets the survey/PDF-SHL/last-result cache when
  `state.wcr_data` changes. `load_legacy_bundle` is async via `asyncio.to_thread`
  and keyed by API/lateral (a failure is cached too, so an outage costs one
  timeout per well). `generate_legacy` and `update_personal_record` are now async.

## Verification
- `ruff --select F` clean; full fast suite green.
- Needs a manual pass in the running app (restart required).

## Notes / follow-ups
- Re-loading the same well reuses its cached legacy bundle until the app restarts.
