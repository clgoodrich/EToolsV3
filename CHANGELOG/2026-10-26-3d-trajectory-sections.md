# 3-D trajectory shows the plat sections at the surface

- **Date:** 2026-10-26
- **Author:** Colton Goodrich (with Claude Code)
- **Commit(s):** see `git log --grep "3-D trajectory"`

## What changed
The Map & Viz tab's 3-D trajectory now outlines the PLSS sections the well
crosses at the surface (depth 0), above the wellbore. Each outline uses the 2D
map's colour and has its label (e.g. `31 3S 4W U`) at its centre. One
"Sections" legend entry toggles them all. Hovering an outline names the section.

## Why
Requested: see which sections the lateral runs under without switching to the 2D map.

## What was added
- `core/survey/processor.latlon_to_offsets`: the exact inverse of station
  placement (AEQD at the SHL, then rotated by −convergence into the grid-north
  `n_offset`/`e_offset` frame the 3-D plot uses).
- `viz_tab._add_surface_sections` and `_sections_crossed`.
- `tests/test_viz_3d_sections.py`: 4 tests.

## What was changed / removed
- `viz_tab._make_3d_figure` takes optional `sections`, `origin` and
  `convergence`. `rerender` passes the same polygons the 2D map draws (which
  honour section-geometry overrides), filtered to the crossed sections. The
  origin is the processed SHL (the Survey-tab override if set).

## Verification
- South Moon 5-31-32-C4-3H (DB): all 204 stations plot inside the outline of
  the section the clearance calc assigned them. The rendered figure was checked
  in a browser: 31-3S-4W, 32-3S-4W and 36-3S-5W are outlined at the surface.
- `pytest tests/test_viz_3d_sections.py`: 4 passed.

## Notes / follow-ups
- Only crossed sections are drawn. All ~17 nearby sections (as on the 2D map)
  stretched the footprint until the well looked flat.
- Requires an app restart.
