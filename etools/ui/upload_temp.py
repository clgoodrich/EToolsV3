"""Temp storage for uploaded PDFs, with an age-based sweep.

Four tabs each carried a byte-identical ``_save_upload`` using
``NamedTemporaryFile(delete=False)``, and nothing in the package ever
deleted the result -- so every upload leaked a PDF into the OS temp
directory for the life of the machine. ``wcr_parser._slice_pdf`` says the
quiet part out loud: *"We don't bother cleaning up the temp file; OS will
eventually."*

Files are swept by **age**, not removed right after parsing, because
``state.apd_pdf_path`` is kept and re-read when the user regenerates without
re-uploading. Deleting on parse would break that flow.

The sweep only ever touches files it created, identified by
``UPLOAD_PREFIX`` -- it must never remove another program's temp files.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from etools.logging_setup import get_logger

log = get_logger(__name__)

UPLOAD_PREFIX = "etools-upload-"


def _temp_dir() -> Path:
    return Path(tempfile.gettempdir())


async def save_upload(upload, name: str) -> str:
    """Persist an uploaded file to a sweepable temp path."""
    suffix = Path(name).suffix or ".pdf"
    fh = tempfile.NamedTemporaryFile(
        delete=False, prefix=UPLOAD_PREFIX, suffix=suffix
    )
    tmp_path = fh.name
    fh.close()
    if upload is not None and hasattr(upload, "save"):
        await upload.save(tmp_path)
    elif upload is not None and hasattr(upload, "read"):
        read_result = upload.read()
        if hasattr(read_result, "__await__"):
            data = await read_result
        else:
            data = read_result
        Path(tmp_path).write_bytes(
            data if isinstance(data, bytes) else bytes(data)
        )
    else:
        raise RuntimeError(
            f"Don't know how to read upload object: {type(upload).__name__}"
        )
    return tmp_path


def sweep_stale_uploads(max_age_hours: float = 24.0) -> int:
    """Delete this app's leftover uploads. Returns how many were removed."""
    cutoff = time.time() - (max_age_hours * 3600.0)
    removed = 0
    try:
        candidates = list(_temp_dir().glob(f"{UPLOAD_PREFIX}*"))
    except OSError as exc:
        log.warning("upload_temp.sweep_listing_failed", error=str(exc))
        return 0
    for path in candidates:
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError as exc:
            # Locked (still open in a viewer) or already gone. Never fatal --
            # a failed sweep must not stop the app from starting.
            log.debug("upload_temp.sweep_skipped", path=str(path), error=str(exc))
    if removed:
        log.info("upload_temp.swept", removed=removed)
    return removed
