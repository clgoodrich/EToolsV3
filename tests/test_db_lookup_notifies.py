"""A DB survey lookup failure must reach the user, not just the log."""
from __future__ import annotations

import inspect

import pytest

MODULES = [
    "etools.ui.tabs.casing_review_tab",
    "etools.ui.tabs.load_tab",
]

# Log events emitted when a DB survey lookup fails outright (as opposed to
# succeeding and returning no rows, which is an ordinary answer).
FAILURE_MARKERS = ("db_lookup_failed", "db_survey_failed", "apd_db_survey_failed")


@pytest.mark.parametrize("modname", MODULES)
def test_db_lookup_failure_notifies_the_user(modname):
    mod = __import__(modname, fromlist=["*"])
    src = inspect.getsource(mod)
    found_any = False
    for marker in FAILURE_MARKERS:
        start = 0
        while True:
            idx = src.find(marker, start)
            if idx == -1:
                break
            found_any = True
            window = src[idx : idx + 700]
            assert "ui.notify" in window, (
                f"{modname}: '{marker}' is logged but never surfaced to the user"
            )
            start = idx + 1
    assert found_any, f"{modname}: no DB-failure marker found; update FAILURE_MARKERS"
