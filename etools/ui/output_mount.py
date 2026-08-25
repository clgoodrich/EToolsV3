"""Serve generated workbooks over /output.

Previously duplicated in casing_review_tab and wcr_tab, both of which set
their "already mounted" flag unconditionally after a bare
``except Exception: pass`` -- so a single failed mount disabled every
Open-folder and Download link for the rest of the process lifetime, with no
notification and no retry.
"""

from __future__ import annotations

from pathlib import Path

from nicegui import app

from etools.config import settings
from etools.logging_setup import get_logger

log = get_logger(__name__)

MOUNT_PATH = "/output"
_mounted = False


def _do_mount(directory: str) -> None:
    from starlette.staticfiles import StaticFiles

    app.mount(MOUNT_PATH, StaticFiles(directory=directory), name="etools_output")


def serve_output_file(path: Path | str) -> str:
    """Return the browser URL for a generated file, mounting /output once."""
    global _mounted
    if not _mounted:
        out_dir = Path(settings.output_dir).resolve()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            _do_mount(str(out_dir))
        except Exception as exc:
            # Deliberately do NOT latch: the usual cause is a transient
            # missing directory, and latching made the failure permanent for
            # the rest of the process.
            log.warning(
                "output_mount.failed", directory=str(out_dir), error=str(exc)
            )
            return f"{MOUNT_PATH}/{Path(path).name}"
        _mounted = True
    return f"{MOUNT_PATH}/{Path(path).name}"
