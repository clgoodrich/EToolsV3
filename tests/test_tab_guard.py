"""Tab render isolation: one broken tab must not kill the page."""
from __future__ import annotations

from etools.ui.tab_guard import describe_tab_failure, safe_tab_render


def test_successful_render_returns_its_refresh_callback():
    calls = []
    cb = safe_tab_render("Demo", lambda: (lambda: calls.append("refreshed")))
    cb()
    assert calls == ["refreshed"]


def test_render_returning_none_still_yields_a_callable():
    cb = safe_tab_render("Demo", lambda: None)
    cb()  # must not raise


def test_failing_render_does_not_propagate_and_records_the_panel():
    seen = []

    def boom():
        raise RuntimeError("kaboom")

    cb = safe_tab_render("Demo", boom, panel=lambda n, e: seen.append((n, e)))
    cb()  # the substituted refresh must be a safe no-op
    assert len(seen) == 1
    assert seen[0][0] == "Demo"
    assert isinstance(seen[0][1], RuntimeError)


def test_describe_tab_failure_plain_exception_names_the_tab():
    msg = describe_tab_failure("Casing Review", RuntimeError("kaboom"))
    assert "Casing Review" in msg
    assert "kaboom" in msg


def test_describe_tab_failure_maps_a_missing_data_file_to_its_build_hint():
    exc = FileNotFoundError(
        "Plat database not found: C:/x/Board_DB_Plss_Sections.db"
    )
    msg = describe_tab_failure("Casing Review", exc)
    assert "Board_DB_Plss_Sections.db" in msg
    # The preflight hint must be surfaced, not just the raw error text.
    assert "data/" in msg


def test_guard_survives_a_logger_that_itself_raises(monkeypatch):
    # Real failure, hit during verification: structlog writes to a cp1252
    # console and log.exception() raised UnicodeEncodeError on a traceback
    # containing an em-dash. The guard must not be defeated by its own
    # logging -- see the same nested guard at casing_review_tab.py:2499.
    import etools.ui.tab_guard as tg

    class BoomLogger:
        def exception(self, *a, **k):
            raise UnicodeEncodeError("charmap", "x", 0, 1, "undefined")

    monkeypatch.setattr(tg, "log", BoomLogger())
    seen = []

    def boom():
        raise RuntimeError("kaboom")

    cb = tg.safe_tab_render("Demo", boom, panel=lambda n, e: seen.append((n, e)))
    cb()
    assert len(seen) == 1, "the panel must still render when logging fails"


def test_guard_survives_a_panel_that_itself_raises():
    # A disposed slot can make the panel render fail too; the page must
    # still come up rather than dying on the error path.
    def boom():
        raise RuntimeError("kaboom")

    def bad_panel(name, exc):
        raise RuntimeError("panel is broken too")

    cb = safe_tab_render("Demo", boom, panel=bad_panel)
    cb()  # must not raise
