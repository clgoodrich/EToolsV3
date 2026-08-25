"""utm_to_latlon must raise ValueError like its sibling converters."""
from __future__ import annotations

import pytest

from etools.core.coordinates.converter import utm_to_latlon


def test_a_valid_utm_pair_round_trips():
    lat, lon = utm_to_latlon(555247.77, 4457938.89, 12, "N")
    assert 40.0 < lat < 40.5
    assert -111.0 < lon < -110.0


def test_swapped_lat_lon_raises_value_error():
    # The real break case: the user typed longitude into the easting box.
    # utm.OutOfRangeError is NOT a ValueError, so survey_tab's
    # `except ValueError` missed it entirely and the button did nothing.
    with pytest.raises(ValueError):
        utm_to_latlon(-110.3502, 40.2701, 12, "N")


def test_non_finite_input_raises_value_error():
    with pytest.raises(ValueError):
        utm_to_latlon(float("nan"), 4457938.89, 12, "N")
    with pytest.raises(ValueError):
        utm_to_latlon(555247.77, float("inf"), 12, "N")


def test_bad_zone_raises_value_error():
    with pytest.raises(ValueError):
        utm_to_latlon(555247.77, 4457938.89, 99, "N")


def test_non_numeric_input_raises_value_error():
    with pytest.raises(ValueError):
        utm_to_latlon("not a number", 4457938.89, 12, "N")


def test_the_raised_error_names_the_offending_values():
    with pytest.raises(ValueError) as ei:
        utm_to_latlon(-110.3502, 40.2701, 12, "N")
    msg = str(ei.value)
    assert "-110.3502" in msg
    assert "12N" in msg or "zone=12" in msg


def test_reprocess_shl_covers_the_conversion_with_its_except():
    """Break case E2: swapping lat and lon made the button do nothing.

    The cause was placement, not exception type -- utm's OutOfRangeError IS a
    ValueError, but the utm_to_latlon call sat *below* the except clause, so
    nothing caught it and the async handler died silently.
    """
    import ast
    import inspect
    import textwrap

    from etools.ui.tabs import survey_tab

    src = inspect.getsource(survey_tab)
    fn_src = src[src.index("async def reprocess_shl"):]
    fn_src = fn_src[: fn_src.index("\n    # ---")]
    tree = ast.parse(textwrap.dedent(fn_src))

    calls_in_try = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                    calls_in_try.add(sub.func.id)
    assert "utm_to_latlon" in calls_in_try, (
        "utm_to_latlon must sit inside the try block, or a bad coordinate "
        "kills the handler with no user-visible feedback"
    )
    assert "dms_to_decimal" in calls_in_try
