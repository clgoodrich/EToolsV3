# Survey edges and the casing connection fallback

- **Date:** 2026-10-27
- **Author:** Colton Goodrich (with Claude Code)
- **Commit(s):** see `git log --grep "survey edges"`

## What changed
A second reviewer's notes were checked one by one with repro scripts. These
reproduced and are fixed:

- **BHL past the end of the survey.** `interpolate_at_md` clamped an MD past
  the last station to that station's position, but kept the asked-for MD. The
  WCR BHL is requested at the PDF's TD, which is usually deeper than the last
  survey station, so the BHL was reported at TD but placed at the last
  station. `WCRPdfService.generate` now projects the survey to TD (or to the
  last perf, if that is deeper) on the last station's inclination and azimuth.
  The results card shows a note saying how far it projected.
  `interpolate_at_md` raises for an MD more than 0.5 ft past the last station
  instead of returning a made-up position.
- **Azimuth across north.** Interpolating 359° → 1° gave 180° at the midpoint.
  It now takes the short way round (0°).
- **Points exactly on a section line or corner.** These matched no section,
  because the spatial join used `within`. It now uses `intersects` and keeps
  the first section, as it already did for duplicates.
- **Uncatalogued casing connection.** When the APD's connection (e.g. TXP)
  isn't in the catalog, the lookup retried without the connection and took
  the first row's joint strength (5.5" 20# P-110 → LTC 548 klbs, against BTC
  667). The pipe-body ratings (collapse, burst, body, ID) are still taken
  from that row. The joint strength is left blank, so the workbook's DGET
  shows the miss and a `casing.catalog.connection_miss` warning is logged.
  None of the 5 APD fixtures use an uncatalogued connection, so their output
  is unchanged.
- **`welltrack_from_processed_survey`** iterated the DataFrame's column
  names and raised `AttributeError`. Nothing calls it with a survey today. It
  now reads the `measured_depth` / `tvd` rows.

## Why
The notes came from a review by another tool; the user asked for it to be acted
on. Each claim was reproduced before it was fixed.

## What was added
- `processor.project_to_md`, `WCRPdfResult.notes`.
- `tests/test_survey_edges.py` (8 tests).

## What was changed / removed
- `processor.interpolate_at_md`: azimuth wrap; raises past the last station.
- `wcr_pdf_service.WCRPdfService.generate`: projection to TD.
- `wcr_tab._render_results`: shows `result.notes`.
- `plat.locator.locate_points`: `intersects` predicate.
- `casing_review.engine.CasingDesignEngine._build_string`: connection fallback.
- `casing_review.engine.welltrack_from_processed_survey`.

## Verification
- Repro script before the fix: MD 1,200 on a survey ending at 1,000 returned
  the 1,000 ft station; 359→1 gave 180; a point on a section line or corner
  gave NaN; TXP took LTC's joint strength. After the fix, each one gives the
  expected result.
- New tests fail to import on the old code and pass on the new code.
- Full test suite: 303 passed. South Moon is unchanged: its survey already reaches TD (19,263 ft).

## Notes / follow-ups (from the same review, not changed)
- The Survey tab's edits (stations, SHL, convergence) don't reach WCR
  Generate, which uses the WCR tab's own survey. Making the two share one
  well model is a design change and needs a decision.
- Convergence uses NAD27 Utah Central (EPSG:32043) for every well, the
  legacy behaviour. A survey referenced to a different grid would be off by
  the difference.
- A survey that starts below MD 0 is still tied in with a vertical station at
  MD 0, without saying so.
- More than 4 reviewable casing strings: the extras are only logged, not shown.
- The WCR KOP takes the shallowest DDR kickoff with confidence 1.0.
