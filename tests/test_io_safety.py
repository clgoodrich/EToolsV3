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
