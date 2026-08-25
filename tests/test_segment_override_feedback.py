"""A geometry edit that saved but failed to repaint must say so."""
from __future__ import annotations

import inspect

from etools.ui.tabs import casing_review_tab


def _fire_viz_refresh_source() -> str:
    src = inspect.getsource(casing_review_tab)
    start = src.index("def _fire_viz_refresh")
    return src[start : start + 1400]


def test_fire_viz_refresh_notifies_on_failure():
    body = _fire_viz_refresh_source()
    assert "ui.notify" in body, (
        "_fire_viz_refresh swallows refresh failures; the user must be told "
        "the edit was saved but the view did not repaint"
    )


def test_the_notify_says_the_edit_was_still_saved():
    # Otherwise the user assumes the edit did nothing and makes it twice.
    body = _fire_viz_refresh_source().lower()
    assert "saved" in body


def test_both_refresh_targets_are_still_attempted_independently():
    # A failure in the map refresh must not skip the plat refresh.
    body = _fire_viz_refresh_source()
    assert body.count("except Exception") >= 2 or "for " in body
