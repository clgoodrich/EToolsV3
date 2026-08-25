"""Degenerate geometry must raise rather than emit NaN footages."""
from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon

from etools.core.casing_review.footages import (
    DegenerateGeometryError,
    footages_to_xy,
    polygon_footages,
)


def _empty_polygon() -> Polygon:
    # This is exactly what sections.resolve_polygon's buffer(0) repair
    # produces from a zero-length ring.
    collapsed = Polygon([(0, 0), (0, 0), (0, 0)]).buffer(0)
    assert collapsed.is_empty
    return collapsed


def test_shapely_still_returns_nan_bounds_for_an_empty_polygon():
    # Pins the upstream behavior this guard exists for. If shapely ever
    # starts raising here, this test tells us the guard can be simplified.
    assert all(math.isnan(v) for v in _empty_polygon().bounds)


def test_polygon_footages_rejects_an_empty_polygon():
    with pytest.raises(DegenerateGeometryError):
        polygon_footages(_empty_polygon(), (100.0, 200.0))


def test_footages_to_xy_rejects_an_empty_polygon():
    with pytest.raises(DegenerateGeometryError):
        footages_to_xy(_empty_polygon(), fnl=100.0, fwl=200.0)


def test_degenerate_error_is_a_value_error():
    # Existing callers catch ValueError and skip the section; that must keep
    # working rather than becoming a hard crash.
    assert issubclass(DegenerateGeometryError, ValueError)


def test_zero_area_polygon_is_rejected():
    flat = Polygon([(0, 0), (10, 0), (20, 0), (0, 0)])
    with pytest.raises(DegenerateGeometryError):
        polygon_footages(flat, (5.0, 0.0))


def test_a_normal_polygon_still_works():
    square = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    f = polygon_footages(square, (250.0, 750.0))
    assert all(math.isfinite(v) for v in (f.fnl, f.fsl, f.fel, f.fwl))
    assert f.fsl > f.fnl  # the point sits in the northern half


def test_footages_round_trip_on_a_normal_polygon():
    square = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    f = polygon_footages(square, (250.0, 750.0))
    x, y = footages_to_xy(square, fnl=f.fnl, fwl=f.fwl)
    assert x == pytest.approx(250.0)
    assert y == pytest.approx(750.0)
