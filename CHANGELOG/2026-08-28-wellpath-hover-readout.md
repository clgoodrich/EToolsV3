# Hover the well path on a section panel to read that station

- **Date:** 2026-08-28
- **Author:** Colton Goodrich
- **Commit(s):** (filled after committing)

## What changed

On the Casing Review section panels (SHL / BHL Section 1-7), moving the cursor
over the green well trajectory now pops an instant readout for the nearest
survey station: **MD, TVD, inclination, azimuth**, and — once clearances have
been calculated — **FNL / FSL / FEL / FWL** plus the section those footages are
measured from.

Two deliberate behaviours, both chosen by the user:

- **It snaps to a real survey station.** Nothing is interpolated, so every
  number in the tooltip is a measured value that exists in the survey.
- **Footages come from the section that geometrically contains the point**, not
  from the panel being hovered. Hovering the same spot in the SEC 23 panel and
  the SEC 24 panel gives the identical answer.

The existing named markers (SHL, K.O. Point, Prod. Interval, BHL) now show the
same full readout instead of a bare name label, reading from the same station
list as the path so the two can never disagree.

## Why

User request. The data was already being computed and then discarded:
`calculate_clearances` (`core/clearance/calculator.py:31`) produces `Conc` plus
FNL/FSL/FEL/FWL for **every** survey station, but only four of them (SHL, KOP,
Landing, BHL, via `ClearanceService._build_summary`) were ever surfaced. The
section panel then re-read the survey and kept nothing but `(easting, northing)`.

## What was added

- **`etools/ui/tabs/casing_review_tab.py`**
  - `_WellStation` — frozen dataclass holding one station's plot position and
    its full readout.
  - `_wellpath_stations(state)` — builds the station list; joins footages on by
    measured depth (`_STATION_MD_TOL_FT = 0.51`, matching `edits._MD_TOL_FT`).
  - `_survey_points`, `_footage_lookup`, `_first_result`, `_finite` — extracted
    helpers; `_finite` maps `None`/NaN/non-numeric to `None`.
  - `_conc_label` — `"2303S02WU"` -> `"Sec 23  T3S R2W  (Uintah)"`.
  - `_stations_payload(stations, *, project=None)` — compact JSON; `project`
    maps UTM into SVG plot coordinates so the browser needs no knowledge of UTM
    or the y-axis flip.
  - `_attr` — HTML attribute escaping, kept separate from the JSON so the
    payload stays testable as JSON.
  - JS `etoolsStationHtml` + a rewritten `etoolsWireWellTips`; `.wt-*` styles on
    `#etools-welltip` in the page head.
- **`tests/test_wellpath_hover.py`** — 22 tests.

## What was changed / removed

- `_wellpath_xy_for_section` is now a thin projection of `_wellpath_stations`,
  so the drawn polyline and the hover targets are built from one list and cannot
  drift apart. **Its output is unchanged** — covered by a test — so the graphic
  does not move.
- `_render_plat_svg` emits one fat transparent `polyline.well-hover`
  (`pointer-events:stroke`, non-scaling 14px) as the hit target, carrying the
  stations in `data-stations`. One element per panel rather than a hit-circle
  per station. The visible path keeps `pointer-events:none` so it cannot
  swallow the mousemove.
- `#etools-welltip` grew from a one-line label into a small panel with
  `font-variant-numeric: tabular-nums`, so digits do not jitter as the cursor
  slides along the path, and it flips sides near a screen edge.
- `TYPE_CHECKING` import of pandas added for the `_survey_points` annotation.

## Verification

- New tests: **22 passed**, written before the implementation and confirmed
  failing first (`ImportError: cannot import name '_stations_payload'`).
- Full suite: **246 passed** in 8:31, exit 0.
- `ruff check etools/` — clean. Its F821 check caught an undefined `pd` in the
  `_survey_points` annotation that the tests did not.
- Real-data check (API 4301354722, crossing sections 28/29/30 T2S R4W U):
  **222 of 222 drawn stations resolved footages**. The footage join is keyed
  on measured depth across two different frames, so a unit test built from
  one frame would pass even if it missed every station in practice.
- Behaviour pinned by test: the drawn path is byte-identical to before, the
  visible polyline stays `pointer-events:none`, and the payload survives
  escape/unescape round-tripping.

## Notes / follow-ups

- **Footages require Calculate Clearances to have been run.** Straight after an
  APD parse the frame carries MD/inc/azi but no `Conc`/footages; the tooltip
  shows what it has and prints "Run Calculate Clearances for footages" rather
  than showing blanks or zeros.
- Stations are downsampled to `_MAX_DRAWN_STATIONS = 600` for both drawing and
  hover — the same cap the code already used — so a hovered station is always
  one that was actually drawn.
- The hover ribbon sits above the boundary segments, so it takes precedence
  over segment hover where the path crosses a section line. This is intentional
  (the path is the smaller target) but is the one interaction worth a look
  during manual testing.
- Not covered by tests: the JavaScript itself. The Python side that emits it is
  pinned by source-inspection tests, but the pointer maths needs the manual
  smoke test.
