"""A survey typed or pasted by hand, for wells whose PDFs don't carry one.

Pure helpers behind the "Type / paste survey" table:

* ``parse_pasted_rows`` turns text copied from Excel (or a PDF / CSV) into
  ``(md, inc, azi)`` rows. Pick columns by header name when there is a
  header row (so a full survey export with TVD/N/E columns still works),
  otherwise take the first three numbers on each line.
* ``build_manual_survey`` validates the rows and returns the same frame
  shape the PDF readers produce (``MeasuredDepth`` / ``Inclination`` /
  ``Azimuth`` plus ``attrs["north_reference"]``), so it flows through the
  exact same processing as a parsed survey.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Sequence

import pandas as pd

Row = tuple[float, float, float]

_NUM_RE = re.compile(r"^[-+]?\d[\d,]*\.?\d*$|^[-+]?\.\d+$")
_SPLIT_RE = re.compile(r";|,(?!\d{3}\b)|\s+")

# Header words that identify each column, checked in order.
_HEADER_KEYS = {
    "md": ("measured", "md", "depth"),
    "inc": ("inc", "incl", "inclination"),
    "azi": ("azi", "azm", "azimuth", "az", "dir"),
}


def _number(token: str) -> float | None:
    token = token.strip().replace("°", "").replace("'", "")
    if not token or not _NUM_RE.match(token):
        return None
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def _cells(line: str) -> list[str]:
    # Excel copies tab-separated; fall back to commas/whitespace for CSV or
    # text copied out of a PDF.
    if "\t" in line:
        return [c.strip() for c in line.split("\t")]
    line = line.strip()
    # Plain CSV ("1500,3.4,245.3"): every comma is a separator. Thousands
    # separators only survive in spaced text ("1,500.00 3.40 245.30").
    if "," in line and not re.search(r"\s", line):
        return [c for c in line.split(",") if c]
    return [c for c in _SPLIT_RE.split(line) if c]


def _header_columns(cells: Sequence[str]) -> dict[str, int] | None:
    """Column index of MD / Inc / Azi when ``cells`` is a header row."""
    found: dict[str, int] = {}
    for i, cell in enumerate(cells):
        word = re.sub(r"[^a-z]", "", cell.lower())
        if not word:
            continue
        for key, names in _HEADER_KEYS.items():
            if key in found:
                continue
            # "TVD" / "vertical depth" is not MD.
            if key == "md" and ("tvd" in word or "vertical" in word):
                continue
            if any(word == n or word.startswith(n) for n in names):
                found[key] = i
                break
    return found if len(found) == 3 else None


def parse_pasted_rows(text: str) -> list[Row]:
    """Rows of ``(md, inc, azi)`` from pasted text; non-data lines are skipped."""
    rows: list[Row] = []
    columns: dict[str, int] | None = None
    for line in (text or "").splitlines():
        cells = _cells(line)
        if not cells:
            continue
        values = [_number(c) for c in cells]
        if not any(v is not None for v in values):
            # A header row. Only trust its column positions when it came from
            # Excel (tab-separated): "Measured Depth" split on spaces shifts
            # every column after it.
            if columns is None and "\t" in line:
                columns = _header_columns(cells)
            continue
        if columns is not None:
            picked = [
                values[columns[k]] if columns[k] < len(values) else None
                for k in ("md", "inc", "azi")
            ]
        else:
            picked = [v for v in values if v is not None][:3]
        if len(picked) == 3 and all(v is not None for v in picked):
            rows.append((picked[0], picked[1], picked[2]))
    return rows


def build_manual_survey(
    rows: Iterable[Sequence[float | None]], north_reference: str
) -> pd.DataFrame:
    """Validated survey frame from hand-entered rows.

    Blank rows are ignored. Raises ``ValueError`` naming the first bad row
    (1-based, as the user sees it) so the table can point at it.
    """
    clean: list[Row] = []
    for n, row in enumerate(rows, start=1):
        vals = [None if v is None or v == "" else v for v in list(row)[:3]]
        if all(v is None for v in vals):
            continue
        nums = [v if isinstance(v, (int, float)) else _number(str(v)) for v in vals]
        if len(nums) < 3 or any(v is None for v in nums):
            raise ValueError(f"Row {n}: MD, inclination and azimuth all need a number.")
        md, inc, azi = (float(v) for v in nums)
        if not all(math.isfinite(v) for v in (md, inc, azi)):
            raise ValueError(f"Row {n}: values must be finite numbers.")
        if md < 0:
            raise ValueError(f"Row {n}: MD can't be negative.")
        if not 0 <= inc <= 180:
            raise ValueError(f"Row {n}: inclination must be between 0 and 180°.")
        if not 0 <= azi <= 360:
            raise ValueError(f"Row {n}: azimuth must be between 0 and 360°.")
        clean.append((md, inc, azi % 360))

    if len(clean) < 2:
        raise ValueError("Enter at least two stations.")
    df = pd.DataFrame(clean, columns=["MeasuredDepth", "Inclination", "Azimuth"])
    df = df.sort_values("MeasuredDepth", kind="stable").reset_index(drop=True)
    dup = df["MeasuredDepth"].duplicated()
    if dup.any():
        md = df.loc[dup.idxmax(), "MeasuredDepth"]
        raise ValueError(f"MD {md:,.2f} is entered twice.")
    ref = (north_reference or "").lower()
    if ref not in ("true", "grid"):
        raise ValueError("Choose whether the azimuths are True or Grid north.")
    df.attrs["north_reference"] = ref
    return df
