"""Every PyMuPDF document must be closed, including on the error path."""
from __future__ import annotations

import inspect
import shutil
from pathlib import Path

import pytest

MODULES = [
    "etools.core.pdf.parser",
    "etools.core.pdf.apd_parser",
    "etools.core.pdf.wcr_parser",
    "etools.core.pdf.ddr_parser",
]


@pytest.mark.parametrize("modname", MODULES)
def test_every_fitz_open_is_closed(modname):
    mod = __import__(modname, fromlist=["*"])
    src = inspect.getsource(mod)
    opens = src.count("fitz.open(")
    # Three shapes count as closed: `with fitz.open(...) as doc`, a bare
    # `with doc:` (used where the open sits in its own try/except so the
    # failure can return "" instead of raising), and an explicit .close().
    closes = (
        src.count(".close()")
        + src.count("with fitz.open(")
        + src.count("with doc:")
    )
    assert closes >= opens, (
        f"{modname}: {opens} fitz.open() call(s) but only {closes} "
        "close()/with statement(s) -- each unclosed document leaks a file "
        "handle and, on Windows, keeps the temp PDF locked"
    )


def _sample_pdf() -> Path | None:
    for root in (Path("tests/fixtures"), Path("tests/APD")):
        if root.exists():
            found = next(iter(root.glob("**/*.pdf")), None)
            if found is not None:
                return found
    return None


def test_a_parsed_pdf_releases_its_file_lock(tmp_path):
    # On Windows an unclosed fitz handle keeps the file locked, which is
    # exactly what makes temp-upload cleanup fail.
    src = _sample_pdf()
    if src is None:
        pytest.skip("no sample PDF available")
    from etools.core.pdf.apd_parser import parse_apd_pdf

    work = tmp_path / "sample.pdf"
    shutil.copyfile(src, work)
    try:
        parse_apd_pdf(work, mode="rules")
    except Exception:
        pass  # parsing may legitimately fail; the lock is what matters
    work.unlink()  # raises PermissionError if a handle is still open
    assert not work.exists()
