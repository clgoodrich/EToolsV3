"""Grid-bearing derivation from a plat polygon.

When a crossed section is absent from the curated ``grid_numbers.sqlite``
reference, its 16 quarter-side rows are derived from the plat polygon so
the Casing Review section sheet's DGET bearing lookups resolve instead of
coming up blank. These tests lock the geometry and the encoding the
section sheet depends on.
"""

from __future__ import annotations


from etools.core.casing_review.grid_corners import (
    _bearing_to_dms_alignment,
    derive_section_corners,
)

# A clean, axis-aligned 1-mile section (UTM metres). 5280 ft ≈ 1609.34 m.
_MILE_M = 5280 / 3.280839895
_SQUARE = [
    (500_000.0, 4_000_000.0 + _MILE_M),          # NW
    (500_000.0 + _MILE_M, 4_000_000.0 + _MILE_M),  # NE
    (500_000.0 + _MILE_M, 4_000_000.0),            # SE
    (500_000.0, 4_000_000.0),                      # SW
    (500_000.0, 4_000_000.0 + _MILE_M),            # close
]


def test_derives_sixteen_quarter_sides() -> None:
    rows = derive_section_corners(
        section=17, township=3, township_dir=2, range_=1, range_dir=1,
        baseline=2, polygon_points=_SQUARE,
    )
    assert len(rows) == 16
    # All 16 canonical side names present, no dups.
    sides = {r.side for r in rows}
    assert len(sides) == 16
    # PLSS fields propagate verbatim (DGET matches on these).
    assert all(
        (r.section, r.township, r.township_dir, r.range, r.range_dir, r.baseline)
        == (17, 3, 2, 1, 1, 2)
        for r in rows
    )


def test_quarter_lengths_are_a_quarter_mile() -> None:
    rows = derive_section_corners(
        section=1, township=1, township_dir=1, range_=1, range_dir=1,
        baseline=1, polygon_points=_SQUARE,
    )
    # Each quarter-side of a 1-mile section ≈ 1320 ft.
    for r in rows:
        assert abs(r.length_ft - 1320) < 5, f"{r.side}: {r.length_ft}"


def test_axis_aligned_bearings_are_near_cardinal() -> None:
    rows = {
        r.side: r
        for r in derive_section_corners(
            section=1, township=1, township_dir=1, range_=1, range_dir=1,
            baseline=1, polygon_points=_SQUARE,
        )
    }
    # A perfectly axis-aligned section: N/S boundaries read ~90° (NE
    # quadrant), E/W boundaries read ~0° (the N-S axis).
    north = rows["North-Left1"]
    assert north.degrees == 89 and north.minutes >= 59 or north.degrees == 90
    assert north.alignment == 2  # NE
    east = rows["East-Up1"]
    assert east.degrees == 0
    assert east.alignment in (1, 4)  # SE or NW (a vertical line)


def test_bearing_to_dms_alignment_quadrants() -> None:
    # Due east travel (dN=0, dE>0): azimuth 90 → NE, 90°.
    d, m, s, align = _bearing_to_dms_alignment(1.0, d_north=0.0)
    assert (d, align) == (90, 2)
    # Due south (dN<0, dE=0): azimuth 180 → SE quadrant, 0°.
    d, m, s, align = _bearing_to_dms_alignment(0.0, d_north=-1.0)
    assert (d, align) == (0, 1)
    # Due west (azimuth 270) → SW quadrant, 90° from the N-S axis (S90°W).
    d, m, s, align = _bearing_to_dms_alignment(-1.0, d_north=0.0)
    assert (d, align) == (90, 3)
    # Due north (azimuth 0) → NE, 0°.
    d, m, s, align = _bearing_to_dms_alignment(0.0, d_north=1.0)
    assert (d, align) == (0, 2)


def test_degenerate_polygon_yields_nothing() -> None:
    assert derive_section_corners(
        section=1, township=1, township_dir=1, range_=1, range_dir=1,
        baseline=1, polygon_points=[(0.0, 0.0)],
    ) == []
