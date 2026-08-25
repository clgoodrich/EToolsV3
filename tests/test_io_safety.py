"""Atomic output: a failed write must leave the previous file intact."""
from __future__ import annotations

import pytest

from etools.core.io_safety import atomic_output, describe_write_error


def test_successful_write_replaces_the_target(tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("old", encoding="utf-8")
    with atomic_output(target) as work:
        assert work != target
        work.write_text("new", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "new"


def test_target_is_created_when_absent(tmp_path):
    target = tmp_path / "sub" / "out.txt"
    with atomic_output(target) as work:
        work.write_text("fresh", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "fresh"


def test_failed_write_leaves_the_previous_file_untouched(tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("precious", encoding="utf-8")
    with pytest.raises(RuntimeError):
        with atomic_output(target) as work:
            work.write_text("half written", encoding="utf-8")
            raise RuntimeError("boom")
    assert target.read_text(encoding="utf-8") == "precious"


def test_failed_write_removes_the_temp_file(tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("precious", encoding="utf-8")
    seen = {}
    with pytest.raises(RuntimeError):
        with atomic_output(target) as work:
            work.write_text("half", encoding="utf-8")
            seen["work"] = work
            raise RuntimeError("boom")
    assert not seen["work"].exists()
    assert list(tmp_path.iterdir()) == [target]


def test_failed_replace_does_not_orphan_the_temp_file(tmp_path, monkeypatch):
    # Real leak found during verification: os.replace sat outside the
    # try/except, so when the destination was locked (the file open in
    # Excel -- the most common failure of all) the partial file was left
    # behind on every attempt.
    import etools.core.io_safety as io_safety

    target = tmp_path / "out.xlsx"
    target.write_text("precious", encoding="utf-8")

    def boom(src, dst):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(io_safety.os, "replace", boom)
    with pytest.raises(PermissionError):
        with io_safety.atomic_output(target) as work:
            work.write_text("new", encoding="utf-8")

    assert target.read_text(encoding="utf-8") == "precious"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "out.xlsx"]
    assert leftovers == [], f"temp file orphaned: {leftovers}"


def test_describe_write_error_calls_out_excel_for_permission_error(tmp_path):
    msg = describe_write_error(
        tmp_path / "Casing Review_x.xlsx", PermissionError(13, "denied")
    )
    assert "Casing Review_x.xlsx" in msg
    assert "Excel" in msg
    assert "Close it" in msg


def test_describe_write_error_falls_back_for_other_errors(tmp_path):
    msg = describe_write_error(tmp_path / "out.xlsx", ValueError("nope"))
    assert "out.xlsx" in msg
    assert "ValueError" in msg


def test_permission_error_message_is_reused_by_the_ui_layer():
    # The Casing Review tab must not hand-roll its own wording; it must use
    # the shared helper so every write path says the same actionable thing.
    import inspect

    from etools.ui.tabs import casing_review_tab

    src = inspect.getsource(casing_review_tab)
    assert "describe_write_error" in src, (
        "casing_review_tab must surface write failures via describe_write_error"
    )


def test_wcr_tab_also_uses_the_shared_write_error_message():
    import inspect

    from etools.ui.tabs import wcr_tab

    assert "describe_write_error" in inspect.getsource(wcr_tab)


def test_wcr_output_hint_is_defined_and_total():
    # Regression: this helper was referenced by the WCR generate error path
    # but never actually defined -- a NameError that only fires when a write
    # fails, which no other test exercises. Ruff caught it; this keeps it caught.
    from etools.ui.tabs.wcr_tab import _wcr_output_hint

    class _Result:
        output_path = "C:/out/South Moon_WCR.xlsx"

    assert _wcr_output_hint({}) == "the WCR workbook"
    assert _wcr_output_hint({"last_result": None}) == "the WCR workbook"
    assert _wcr_output_hint({"last_result": _Result()}).endswith("_WCR.xlsx")


def test_every_ui_module_is_lint_clean_for_undefined_names():
    # F821 would have caught the _wcr_output_hint bug at edit time.
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "F821", "etools/"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
