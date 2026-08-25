"""A failed orchestration must not leave two wells' data side by side."""
from __future__ import annotations

import inspect

import pytest

from etools.ui.state import AppState
from etools.ui.state_staging import clear_group_on_failure

FIELDS = ("processed", "clearances", "section_definitions")


def _loaded_state():
    s = AppState()
    s.processed = {"AsDrilled": "OLD-processed"}
    s.clearances = {"AsDrilled": "OLD-clearances"}
    s.section_definitions = {"2303S02WU": "OLD-sections"}
    return s


def test_success_leaves_every_field_as_written():
    s = _loaded_state()
    with clear_group_on_failure(s, FIELDS):
        s.processed = {"AsDrilled": "NEW-processed"}
        s.clearances = {"AsDrilled": "NEW-clearances"}
        s.section_definitions = {"x": "NEW-sections"}
    assert s.processed == {"AsDrilled": "NEW-processed"}
    assert s.clearances == {"AsDrilled": "NEW-clearances"}
    assert s.section_definitions == {"x": "NEW-sections"}


def test_a_failure_clears_the_whole_group_rather_than_mixing():
    s = _loaded_state()
    with pytest.raises(RuntimeError):
        with clear_group_on_failure(s, FIELDS):
            s.processed = {"AsDrilled": "NEW-processed"}  # new well
            raise RuntimeError("clearances blew up")
    # The new well's survey must NOT be left sitting next to the old well's
    # clearances -- that mixture is invisible in the UI.
    assert not s.processed
    assert not s.clearances
    assert not s.section_definitions


def test_the_exception_still_propagates():
    s = _loaded_state()
    with pytest.raises(ValueError, match="boom"):
        with clear_group_on_failure(s, FIELDS):
            raise ValueError("boom")


def test_intermediate_reads_still_see_the_live_state():
    # The whole reason for this design: post_load_orchestrate reads these
    # fields between the writes, so they must be readable as normal.
    s = _loaded_state()
    with clear_group_on_failure(s, FIELDS):
        s.processed = {"AsDrilled": "NEW"}
        assert s.processed == {"AsDrilled": "NEW"}


def test_post_load_orchestrate_uses_the_guard():
    from etools.ui import app as app_module

    src = inspect.getsource(app_module)
    body = src[src.index("async def post_load_orchestrate"):]
    body = body[: body.index("async def ", 10)] if "async def " in body[10:] else body
    assert "clear_group_on_failure" in body, (
        "post_load_orchestrate must group its state writes so a mid-pipeline "
        "failure cannot leave two wells mixed"
    )
