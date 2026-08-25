# Degenerate section polygons now raise instead of emitting NaN footages

- **Date:** 2026-08-25
- **Author:** Colton Goodrich
- **Commit(s):** (this commit)

## What changed

A section polygon that collapsed to nothing used to produce footages of `NaN`
without raising anything anywhere. Those NaNs flowed straight into the Casing
Review section sheets. Now the collapse is caught at its source and at both
points of use, and the affected section is skipped with an explanation rather
than written out as a non-answer.

## Why

Audit finding 7.A4, ranked third in the failure-path review — and a **correction
to earlier finding #30**, which predicted a `ValueError` crash here. The real
behavior was worse than predicted: verified on shapely 2.0.5,

```
Polygon().bounds            -> (nan, nan, nan, nan)
minx, miny, maxx, maxy = …  -> unpacks cleanly, no exception
```

Traced end to end before the fix:

```
polygon_footages(empty, (100, 200))      -> SectionFootages(fnl=nan, fsl=nan, fel=nan, fwl=nan)
footages_to_xy(empty, fnl=100, fwl=200)  -> (nan, nan)
```

The trigger is `sections.py:669-672`, where `buffer(0)` "repairs" a
self-intersecting or zero-length-segment ring by collapsing it to an empty
polygon. A crash would have stopped the user; NaN did not.

## What was added

- **`DegenerateGeometryError`** in `etools/core/casing_review/footages.py`. It
  subclasses `ValueError` deliberately: `sections.py:316`, `writer.py:473` and
  `build_section_definitions:941` already catch `ValueError` and skip the
  offending section, which is exactly the wanted behavior. A new unrelated
  exception type would have converted a silent-NaN bug into a hard crash.
- **`_checked_bounds()`** in the same module — rejects `None`, empty geometry,
  non-finite bounds, and zero extent.
- **`tests/test_geometry_guards.py`** — 7 tests, including one that pins
  shapely's NaN-bounds behavior so we learn if upstream ever changes it.

## What was changed / removed

- `polygon_footages` and `footages_to_xy` now take bounds via `_checked_bounds`.
- `SectionDefinition.resolve_polygon` raises `DegenerateGeometryError` when
  `buffer(0)` returns an empty geometry, and logs `section.polygon_repaired`
  with before/after areas when a repair does succeed — previously the repair was
  entirely silent either way.
- `_bbox_corners` uses `_checked_bounds` instead of taking `.bounds` after only a
  `None` check.

## Verification

- `tests/test_geometry_guards.py` — 7 passed (verified failing first with
  `ImportError`).
- Full suite: **160 passed** in 8:28, exit 0.
- Direct repro after the fix: both `polygon_footages` and `footages_to_xy` raise
  on a `buffer(0)`-collapsed polygon where they previously returned NaN.
- `test_section_traversal`, `test_grid_derivation` and `test_writer_sections`
  all build real polygons and were watched specifically — no real section has
  zero extent, so the guard changed no existing output.

## Notes / follow-ups

- `sections.py` now imports `footages` at module level (it previously only did so
  locally inside functions). Verified no import cycle: `footages.py` imports only
  `math`, `dataclasses` and shapely.
- `_checked_bounds` is a private name imported across modules. Acceptable for now
  given both live in `etools/core/casing_review/`; worth promoting to a public
  name if a third consumer appears.
- Part of the failure-path hardening effort planned in
  `docs/superpowers/plans/2026-08-19-failure-path-hardening.md`.
