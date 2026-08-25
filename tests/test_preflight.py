"""Startup preflight for the gitignored data files."""
from __future__ import annotations

from pathlib import Path

from etools import preflight


def test_required_data_files_lists_all_three():
    statuses = preflight.required_data_files()
    names = {s.name for s in statuses}
    assert names == {"Plat sections", "Casing catalog", "Grid numbers"}
    for s in statuses:
        assert s.build_hint, f"{s.name} must carry a build hint"
        assert s.purpose, f"{s.name} must explain what it is for"


def test_missing_data_files_is_empty_on_a_working_install():
    # This repo has all three present; the audit baseline depends on it.
    assert preflight.missing_data_files() == []


def test_missing_data_files_detects_an_absent_file(monkeypatch):
    monkeypatch.setattr(
        preflight.settings, "plats_db", Path("C:/nope/definitely_missing.db")
    )
    missing = preflight.missing_data_files()
    assert [s.name for s in missing] == ["Plat sections"]
    assert missing[0].present is False


def test_format_preflight_report_is_empty_when_nothing_missing():
    assert preflight.format_preflight_report([]) == ""


def test_format_preflight_report_names_file_and_hint(monkeypatch):
    monkeypatch.setattr(
        preflight.settings, "plats_db", Path("C:/nope/definitely_missing.db")
    )
    report = preflight.format_preflight_report(preflight.missing_data_files())
    assert "Plat sections" in report
    assert "definitely_missing.db" in report
    assert "Board_DB_Plss_Sections.db" in report  # the build hint
