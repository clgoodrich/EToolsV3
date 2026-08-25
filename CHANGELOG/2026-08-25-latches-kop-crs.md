# Mount latch, KOP guards, and the spatial-join CRS assumption

- **Date:** 2026-08-25
- **Author:** Colton Goodrich
- **Commit(s):** 9be7063, e272f0b, (locator commit)

## What changed

Three unrelated silent-degradation paths, grouped because each is small.

A failed `/output` mount no longer disables every download link for the rest of
the session. KOP detection no longer analyses zero-padded garbage on a survey too
short to filter, and no longer lets a duplicated station perturb the result. A
spatial join that matches nothing now says so at warning level instead of `info`.

## Why

Audit findings 7.B2, 7.B4, 7.B5 and 7.B6.

- **7.B2** — `casing_review_tab` and `wcr_tab` each carried an identical
  `_serve_output_file` that set `_mounted = True` unconditionally *after* a bare
  `except Exception: pass`. One failure latched the flag and every Open-folder
  and Download link 404'd for the rest of the process.
- **7.B4** — `detect_kop` checked only `survey.empty`. Verified before the fix: a
  3-station survey emitted a scipy zero-padding `UserWarning` plus two
  divide-by-zero `RuntimeWarning`s and analysed the padded result; duplicate MDs
  put NaN into the gradient array (2 of 17 values on the test survey);
  `_kop_clustering` swallowed every exception with no log at all.
- **7.B5/B6** — `locate_points` assigns the sections' CRS to the points rather
  than reprojecting, and nothing recorded that the assumption was never checked.

## What was added

- **`etools/ui/output_mount.py`** — one `serve_output_file()` that latches only
  on success. Both tabs import it under their existing private name, so no call
  site changed.
- **`tests/test_output_mount.py`** (4), **`tests/test_kop_guards.py`** (6),
  **`tests/test_locator_crs.py`** (4).
- A **ruff `F821` check over `etools/`** inside the test suite.

## What was changed / removed

- Deleted the duplicated `_serve_output_file` from both tabs; removed the imports
  that became orphaned (`nicegui.app`, `etools.config.settings`).
- **`etools/core/survey/kop.py`** — dedupes MDs (with a warning), returns
  `method="insufficient_data"` when the survey is shorter than the median-filter
  kernel, and logs `kop.clustering_failed`. Added a module logger; there was none.
- **`etools/core/plat/locator.py`** — documents that the CRS is assigned and not
  reprojected, and warns `plat.locate.no_matches` when a non-empty join matches
  nothing.

## Verification

- New tests: 14 passed, each verified failing first.
- Full suite: **181 passed** in 8:37, exit 0. No existing KOP moved — the normal
  survey is pinned to its exact prior result (md 1000.0, 5 candidates).
- Locator warning verified in both directions: degrees-into-metres warns, a
  normal join does not.

## Notes / follow-ups

- **Two live `NameError`s introduced earlier in this branch were found here by
  ruff, not pytest** — `_wcr_output_hint` referenced but never defined, and
  `log.warning` in `sections.py` with no logger bound. Both sat on error paths no
  test reaches and had passed the full suite three times. The `F821` check now in
  the suite exists so this cannot recur silently; a lint pass is part of every
  remaining task's verification.
- **Scope correction to 7.B4.** I claimed duplicate MDs make candidates "vanish
  silently". The NaN contamination is real and now fixed, but on the survey
  tested it did not change the final KOP — a clean survey of the same length
  drops the same voters, so length rather than NaN was the cause there. The test
  asserts the guarantee that is actually verified: a re-surveyed depth gives
  byte-identical results to the clean survey.
- Two test-mechanism gotchas for future work: `caplog` does not capture this
  app's structlog output (use a recording double), and source-inspection
  assertions must match single words, not phrases that line-wrapping splits.
- Part of the failure-path hardening effort planned in
  `docs/superpowers/plans/2026-08-19-failure-path-hardening.md`.
