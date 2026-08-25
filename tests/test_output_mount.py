"""The output static-mount must retry after a failure, not latch."""
from __future__ import annotations

from etools.ui import output_mount


def test_url_is_derived_from_the_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(output_mount, "_mounted", False, raising=False)
    calls = []
    monkeypatch.setattr(output_mount, "_do_mount", lambda d: calls.append(d))
    url = output_mount.serve_output_file(tmp_path / "Casing Review_x.xlsx")
    assert url == "/output/Casing Review_x.xlsx"
    assert len(calls) == 1


def test_a_failed_mount_is_retried_on_the_next_call(tmp_path, monkeypatch):
    monkeypatch.setattr(output_mount, "_mounted", False, raising=False)
    attempts = []

    def flaky(directory):
        attempts.append(directory)
        if len(attempts) == 1:
            raise RuntimeError("mount failed")

    monkeypatch.setattr(output_mount, "_do_mount", flaky)
    output_mount.serve_output_file(tmp_path / "a.xlsx")
    output_mount.serve_output_file(tmp_path / "b.xlsx")
    assert len(attempts) == 2, "a failed mount must be retried"


def test_a_successful_mount_is_not_repeated(tmp_path, monkeypatch):
    monkeypatch.setattr(output_mount, "_mounted", False, raising=False)
    attempts = []
    monkeypatch.setattr(output_mount, "_do_mount", lambda d: attempts.append(d))
    output_mount.serve_output_file(tmp_path / "a.xlsx")
    output_mount.serve_output_file(tmp_path / "b.xlsx")
    assert len(attempts) == 1


def test_a_failed_mount_still_returns_a_usable_url(tmp_path, monkeypatch):
    monkeypatch.setattr(output_mount, "_mounted", False, raising=False)

    def always_fails(directory):
        raise RuntimeError("mount failed")

    monkeypatch.setattr(output_mount, "_do_mount", always_fails)
    url = output_mount.serve_output_file(tmp_path / "c.xlsx")
    assert url == "/output/c.xlsx"
