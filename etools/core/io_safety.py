"""Write files without destroying the previous version on failure.

Every workbook writer in ETools used to write straight to its final path:
``shutil.copyfile(template, output_path)`` followed, ~90 lines later, by
``wb.save(output_path)``. Between those two calls the user's previously
generated workbook no longer existed, so any exception in between left a
blank template on disk while the UI reported only "Generation failed".

``atomic_output`` writes to a sibling temp file and ``os.replace``s it into
position only after the caller has finished cleanly. ``os.replace`` is
atomic within a single filesystem, which is why the temp file is a sibling
rather than something under the system temp directory.

Note for Windows: replacing a file that Excel holds open still raises
``PermissionError``. This module does not make that write succeed -- it
guarantees the existing file survives it.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from etools.logging_setup import get_logger

log = get_logger(__name__)


@contextmanager
def atomic_output(path: Path | str, *, keep_failed: bool = False) -> Iterator[Path]:
    """Yield a temp path to write to; swap it onto ``path`` on clean exit.

    On any exception the temp file is removed (unless ``keep_failed``) and
    ``path`` is left exactly as it was.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Sibling temp file: os.replace is only atomic within one filesystem.
    # The PID keeps two concurrent generations of the same well apart.
    work = path.with_name(f".{path.stem}.{os.getpid()}.partial{path.suffix}")
    try:
        yield work
    except BaseException:
        if not keep_failed:
            try:
                work.unlink(missing_ok=True)
            except OSError as exc:
                log.warning(
                    "io_safety.temp_cleanup_failed", path=str(work), error=str(exc)
                )
        raise
    os.replace(work, path)


def describe_write_error(path: str | Path, exc: BaseException) -> str:
    """Turn a write failure into a sentence naming the cause and the fix."""
    name = Path(path).name
    if isinstance(exc, PermissionError):
        return (
            f"Can't write {name} - it is most likely open in Excel. "
            "Close it and try again. Your previous copy has not been changed."
        )
    if isinstance(exc, FileNotFoundError):
        return f"Can't write {name} - a required file is missing: {exc}"
    if isinstance(exc, OSError):
        detail = getattr(exc, "strerror", None) or str(exc)
        return f"Can't write {name} - {detail}"
    return f"Couldn't generate {name}: {type(exc).__name__}: {exc}"
