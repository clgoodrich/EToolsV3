"""Uploaded PDFs must not accumulate in the temp directory forever."""
from __future__ import annotations

import os
import time

from etools.ui import upload_temp


def test_prefix_is_distinctive_enough_to_sweep_safely():
    assert upload_temp.UPLOAD_PREFIX.startswith("etools-upload-")


def test_sweep_removes_only_old_etools_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_temp, "_temp_dir", lambda: tmp_path)
    old = tmp_path / f"{upload_temp.UPLOAD_PREFIX}old.pdf"
    new = tmp_path / f"{upload_temp.UPLOAD_PREFIX}new.pdf"
    other = tmp_path / "someone-elses-file.pdf"
    for p in (old, new, other):
        p.write_bytes(b"x")
    stale = time.time() - (48 * 3600)
    os.utime(old, (stale, stale))

    removed = upload_temp.sweep_stale_uploads(max_age_hours=24.0)

    assert removed == 1
    assert not old.exists()
    assert new.exists()
    assert other.exists(), "the sweep must never touch files it did not create"


def test_sweep_survives_a_locked_file(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_temp, "_temp_dir", lambda: tmp_path)
    locked = tmp_path / f"{upload_temp.UPLOAD_PREFIX}locked.pdf"
    locked.write_bytes(b"x")
    stale = time.time() - (48 * 3600)
    os.utime(locked, (stale, stale))
    fh = open(locked, "r+b")
    try:
        # Must not raise even though the file cannot be removed on Windows.
        upload_temp.sweep_stale_uploads(max_age_hours=24.0)
    finally:
        fh.close()


def test_sweep_on_a_missing_directory_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_temp, "_temp_dir", lambda: tmp_path / "gone")
    assert upload_temp.sweep_stale_uploads() == 0


def test_all_four_tabs_share_one_upload_helper():
    # Four byte-identical copies is how the leak stayed invisible.
    import inspect

    for mod in (
        "etools.ui.tabs.load_tab",
        "etools.ui.tabs.casing_review_tab",
        "etools.ui.tabs.pdf_tab",
        "etools.ui.tabs.wcr_tab",
    ):
        src = inspect.getsource(__import__(mod, fromlist=["*"]))
        assert "async def _save_upload" not in src, (
            f"{mod} still defines its own _save_upload; import the shared one"
        )
        assert "upload_temp" in src, f"{mod} must use the shared upload helper"
