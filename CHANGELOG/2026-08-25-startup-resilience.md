# Startup resilience: missing data files no longer kill the whole app

- **Date:** 2026-08-25
- **Author:** Colton Goodrich
- **Commit(s):** 2ba1a4d, (tab guard commit)

## What changed

ETools used to start, bind port 8080, and then fail to render *any* page if one
of the three gitignored data files was absent — with the real cause visible only
in the log. The launcher looked healthy; the app was simply blank.

Now two things happen instead. At startup the console names every missing data
file, what it is for, and the exact command or copy that fixes it. At render
time each tab is isolated, so a tab that cannot build shows an inline
explanation and the other six work normally.

## Why

Audit finding 7.A1, ranked the single most severe issue in the failure-path
review. All three data assets are gitignored (`.gitignore:71` and `:80`), so a
fresh clone — or a portable bundle copied without its `data/` directory — has
none of them. `PlatRepository.__init__` and `CasingCatalog.__init__` both raise
`FileNotFoundError` eagerly, and `CasingReviewService()` constructs both at
page-render time from `casing_review_tab.py:193`. Because `app.py` rendered the
tabs outside any `try`/`except`, that exception propagated straight out of
`root()`.

Confirmed by execution before the fix:

```
CasingReviewService() -> FileNotFoundError : Plat database not found: ...
WCRPdfService()       -> FileNotFoundError : Plat database not found: ...
```

## What was added

- **`etools/preflight.py`** — `DataFileStatus` (frozen dataclass),
  `required_data_files()`, `missing_data_files()` and
  `format_preflight_report()`. Pure: no UI, no logging, no side effects. The
  catalog/grid path constants are imported inside the function so a broken
  import cannot break startup.
- **`etools/ui/tab_guard.py`** — `safe_tab_render()` and
  `describe_tab_failure()`. The latter matches a `FileNotFoundError` against the
  preflight registry so the panel prints the real build command rather than
  echoing the exception. `safe_tab_render` always returns a callable, so
  `refresh_callbacks` stays uniform and `fire_refresh` needs no special case.
- **`tests/test_preflight.py`** (5 tests) and **`tests/test_tab_guard.py`**
  (7 tests).

## What was changed / removed

- **`etools/main.py`** — `run()` now calls `missing_data_files()` before
  `build_app()` and prints the report when anything is missing.
- **`etools/ui/app.py`** — the six non-Load tab panels at `:554-574` now render
  through `safe_tab_render`. The Load Well panel is unchanged: it constructs no
  services eagerly and cannot fail this way.

## Verification

- `tests/test_preflight.py` — 5 passed (verified failing first with
  `ImportError`).
- `tests/test_tab_guard.py` — 7 passed (verified failing first with
  `ModuleNotFoundError`).
- Full suite: **144 passed** in 8:06, exit 0 (baseline was 132).
- End-to-end repro of the original failure, without deleting any real data file,
  by pointing `settings.plats_db` at a missing path in-process: the panel fires,
  the substituted refresh callback is a safe no-op, and the message names
  `Board_DB_Plss_Sections.db` plus the copy instruction. Re-run under
  `PYTHONIOENCODING=cp1252` after the fix below.

## Notes / follow-ups

- **A real defect was found in the guard itself during verification.**
  `log.exception` raised `UnicodeEncodeError` when structlog wrote a traceback
  containing an em-dash to a cp1252 console — so the guard failed and the
  exception escaped anyway, defeating its entire purpose. Both the logging call
  and the panel render are now individually wrapped, mirroring the nested guard
  that already existed at `casing_review_tab.py:2499-2506`. Two regression tests
  cover it.
- `describe_tab_failure` matches on filename, so a data file renamed in
  `config.py` without updating `preflight.py` degrades to echoing the raw
  exception rather than showing the build hint. Acceptable, and the generic
  branch is tested.
- Part of the failure-path hardening effort planned in
  `docs/superpowers/plans/2026-08-19-failure-path-hardening.md`.
