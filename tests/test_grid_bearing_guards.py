"""A zero-length section boundary has no bearing, not a bearing of zero."""
from __future__ import annotations

from etools.core.casing_review.grid_corners import _bearing_to_dms_alignment


def test_a_real_boundary_yields_a_bearing():
    deg, minutes, seconds, align = _bearing_to_dms_alignment(0.0, d_north=1000.0)
    assert deg is not None
    assert align in (1, 2, 3, 4)


def test_a_due_east_boundary_still_reads_as_a_right_angle():
    # Pins existing behavior: a near-E/W boundary reads 89-90 deg in the NE
    # quadrant per the Grid Numbers convention.
    deg, minutes, seconds, align = _bearing_to_dms_alignment(1000.0, d_north=0.0)
    assert deg == 90
    assert align == 2


def test_a_zero_length_boundary_yields_none():
    # atan2(0, 0) is exactly 0.0, which used to be emitted as a confident
    # due-north bearing for a boundary that does not exist.
    assert _bearing_to_dms_alignment(0.0, d_north=0.0) == (None, None, None, None)


def test_a_sub_micrometre_boundary_yields_none():
    assert _bearing_to_dms_alignment(1e-9, d_north=1e-9) == (None, None, None, None)


def test_the_result_is_always_a_four_tuple():
    # The caller unpacks four values; None must not change the shape.
    for args in ((0.0, 0.0), (1000.0, 0.0), (0.0, 1000.0), (500.0, 500.0)):
        result = _bearing_to_dms_alignment(args[0], d_north=args[1])
        assert isinstance(result, tuple)
        assert len(result) == 4
