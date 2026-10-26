# Survey station coordinates follow true north

- **Date:** 2026-10-26
- **Author:** Colton Goodrich (with Claude Code)
- **Commit(s):** see `git log --grep "true north"`

## What changed
Every processed survey station's lat/lon, UTM easting/northing, PLSS section and
FNL/FSL/FEL/FWL footages now land where the survey actually puts them. On
Uintah Basin laterals they moved by roughly 15–140 ft at the BHL. The WCR and
APD/WCR-promote paths now process a DB survey in its own north reference
instead of assuming grid.

## Why
- `process_survey` un-projected welleng's `n`/`e` offsets through an AEQD that
  is oriented to true north. welleng integrates the **grid** azimuth, so every
  station was rotated about the SHL by the grid convergence (~0.7–1.3°).
- Against the DB's own `LatitudeCalc`/`LongitudeCalc`, the old BHLs missed by
  18–142 ft (4301353996, 4301354822, 4304757155, 4301353898). They now land
  within 0–4 ft.
- `WCRPdfService.generate` defaulted to `north_reference="grid"`, and the
  APD/WCR header builders hard-code "grid". For true-north DB surveys the old
  rotation error happened to cancel this one out, which is why the South Moon
  regression test still passed. Fixing only the rotation broke 10 South Moon
  location checks by about 114 ft. Fixing both brings it back to matching the
  reference workbook, which itself matches DOGM's stored X/Y.

## What was added
- `tests/test_survey_true_north_latlon.py`: the BHL bearing equals the true
  azimuth for True and Grid surveys (3 tests; they fail on the old code).
- `ui/promote.py` `_adopt_survey_north_reference`.

## What was changed / removed
- `core/survey/processor.py`: rotates n/e by the convergence before
  `_nev_to_latlon`. The `n_offset`/`e_offset` columns (DxSurvey rows, 3-D plot)
  are unchanged.
- `services/wcr_pdf_service.py`: `north_reference` now defaults to `None`, which
  resolves to the survey's `attrs["north_reference"]`, then to "grid".
- `ui/promote.py`: the APD/WCR promote adopts the survey frame's reference.

## Verification
- DB-truth comparison script (numbers above).
- `pytest tests/test_wcr_south_moon.py tests/test_survey_repo_citing.py`: 79 passed.

## Notes / follow-ups
- Any footages/workbooks generated before this change for directional wells
  carry the rotation error.
