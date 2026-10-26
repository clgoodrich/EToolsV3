# DB surveys: right citing type, one header per type, right sundry

- **Date:** 2026-10-26
- **Author:** Colton Goodrich (with Claude Code)
- **Commit(s):** see `git log --grep "citing types"`

## What changed
Loading a well from the database now finds the As-Drilled survey however its
citing type is spelled, uses only the newest upload of each citing type, and
picks the drilled header as the primary well header. TrackingWCR's "Date Filed"
comes from the WCR's own sundry, and the legacy WCR flow uses the newest
well-info row.

## Why
All of these were confirmed against the live DB:
- `CitingType` is free text: `ASDRILLED` (128 headers), `Asdrilled` (19),
  `PLANNED` (1038) and `planned` (11) sit alongside `AsDrilled`/`Planned`. Every
  picker looks up the exact `"AsDrilled"` key, so wells like 4304757155 used the
  **Planned** survey as the drilled one, and 4301354822 reported "no survey".
- `WellService` tested `.startswith("drill")`, which never matches `AsDrilled`,
  so the primary header (elevation, north reference) was often the Planned one.
  For 4301353898 the elevation shown was 2384 instead of 6463.
- Re-uploads of the same citing type were concatenated and sorted by MD. That
  interleaved two surveys into one zig-zag; 4304757696 showed a 399°/100 ft DLS.
- `get_latest_wcr_submission` joined `tblAPDSundry` on the API only, so it paired
  the WCR's SundryNo with the date of the well's newest sundry of any type.
  For 4304757202 it reported 2025-01-23; the real eWCR date is 2024-12-18.
- `_get_well_info` had no `ORDER BY`, so an original/amended WCR pair returned
  either row at random.

## What was added
- `repositories/survey.py`: `canonical_citing_type()` and `newest_header_pkey()`.
  Each returned survey frame now carries its header's `NorthReference` in
  `frame.attrs["north_reference"]`, which the survey-frame change uses.
- `tests/test_survey_repo_citing.py`: 8 tests with the SQL stubbed out.

## What was changed / removed
- `SurveyRepository.get_points_by_api_lateral`: canonical keys; newest header
  per type, with a `survey.duplicate_headers` warning when it drops one.
- `WellRepository.list_headers` / `_row_to_header`: canonical citing type, and
  one (newest) header per type.
- `WellService.load`: the primary is the header whose citing type contains "drill".
- `WCRRepository.get_latest_wcr_submission`: `JOIN ... ON tas.idx = wi.SundryNo`.
  `_get_well_info`: `ORDER BY wi.PKey DESC`.

## Verification
- Live DB: 4301354822, 4304757155, 4304757696, 4304756091 and 4301353898 now
  return monotonic surveys with no duplicate MDs, and the drilled header is
  primary. Sundry 134189 reports 2024-12-18. 4304757284 reports completion
  2024-01-19, which is the newest row.
- `pytest tests/test_survey_repo_citing.py`: 8 passed.

## Notes / follow-ups
- "Newest" means newest `UploadDateTime`, with PKey as the tie-break. For
  4304756091 the newest As-Drilled upload has 49 stations and the older one has
  144. Worth a look if that well matters.
