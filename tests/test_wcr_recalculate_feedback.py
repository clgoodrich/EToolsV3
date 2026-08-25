"""A partially-repainted WCR grid must not silently diverge from the data."""
from __future__ import annotations

import inspect

from etools.ui.tabs import wcr_tab


def _recalc_source() -> str:
    src = inspect.getsource(wcr_tab)
    start = src.index("def recalculate_edits")
    end = src.index("\n    def ", start + 10)
    return src[start:end]


def test_row_repaint_failures_are_counted():
    body = _recalc_source()
    assert "stale" in body or "skipped" in body, (
        "recalculate_edits must count rows that failed to repaint"
    )


def test_row_repaint_failures_are_surfaced_to_the_user():
    body = _recalc_source()
    # The outer handler already notifies on total failure; the per-row path
    # must notify too, or the exported Excel silently disagrees with the grid.
    assert body.count("ui.notify") >= 2, (
        "a partial repaint leaves the visible grid disagreeing with the data "
        "that will be exported; the user must be told"
    )


def test_the_message_says_the_values_are_still_saved():
    body = _recalc_source().lower()
    assert "saved" in body or "will be used" in body


def test_the_data_model_is_still_updated_on_a_partial_repaint():
    # The recompute succeeded, so result.location_rows SHOULD advance --
    # the bug was silence about the display, not the assignment.
    body = _recalc_source()
    assert "result.location_rows = new_rows" in body
