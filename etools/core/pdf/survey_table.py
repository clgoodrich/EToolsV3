"""Read a directional-survey table straight out of a PDF by word position.

APDs carry the operator's directional plan as an appendix and many WCRs carry
the as-drilled survey report, as real text (not scans). Their tables look like

    Measured   INC   AZI   Vertical   +N/-S ...
    Depth                  Depth
    (usft)     (°)   (°)   (usft)
    230.00     0.44  320.70  230.00   0.68 ...

but in text-extraction order the header cells, wrapped units and right-aligned
numbers come out interleaved, so line-based regexes miss them. Here each page's
words are grouped into visual lines, the header row's column positions are
found, and every number below is assigned to the nearest header column.

Only rows with a valid MD, inclination and azimuth are kept. The longest run of
strictly increasing MD wins, which drops short "section details" and target
tables and handles a header repeated on every page.

Fast (PyMuPDF only, no Docling/LLM): ~0.1 s per PDF.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from etools.logging_setup import get_logger

log = get_logger(__name__)

_LINE_TOL = 3.0  # pt
_NUM_RE = re.compile(r"^-?\d{1,3}(?:,\d{3})*(?:\.\d+)?$|^-?\d+(?:\.\d+)?$")

# Header-word → column role. Matched case-insensitively on whole words.
_ROLE = {
    "md": "md", "measured": "md",
    "inc": "inc", "incl": "inc", "incl.": "inc", "inclination": "inc",
    "azi": "azi", "azimuth": "azi", "az": "azi", "azi.": "azi", "azm": "azi",
}
# Other header words that define columns (so their numbers don't get pulled
# into MD/INC/AZI by "nearest column").
_OTHER = {
    "tvd", "vertical", "depth", "+n/-s", "+e/-w", "n/s", "e/w", "north", "east",
    "northing", "easting", "latitude", "longitude", "longituge", "section",
    "sect", "vs", "vsect", "dls", "dleg", "dogleg", "build", "turn", "rate",
    "tface", "comments", "target", "sec", "local", "coordinates", "map", "geo",
}
_HEADER_SPAN = 40.0  # pt: header cells may wrap over several lines


@dataclass
class _Col:
    role: str
    x: float  # centre


def _lines(words) -> list[list]:
    lines: list[list] = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        cy = (w[1] + w[3]) / 2
        if lines and abs(((lines[-1][0][1] + lines[-1][0][3]) / 2) - cy) <= _LINE_TOL:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(ln, key=lambda w: w[0]) for ln in lines]


def _num(tok: str) -> float | None:
    t = tok.strip().rstrip("†*'’°")
    if not _NUM_RE.match(t):
        return None
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return None


def _header_columns(lines: list[list], i: int) -> tuple[list[_Col], int] | None:
    """If line ``i`` starts a survey header, return its columns and the index
    of the first line after the header band."""
    y0 = lines[i][0][1]
    band = []
    j = i
    while j < len(lines) and lines[j][0][1] - y0 <= _HEADER_SPAN:
        if any(_num(w[4]) is not None for w in lines[j]) and j > i:
            # A numeric line ends the header — unless it's only units.
            if sum(_num(w[4]) is not None for w in lines[j]) >= 3:
                break
        band.extend(lines[j])
        j += 1
    roles = {}
    cols: list[_Col] = []
    for w in band:
        key = w[4].strip().lower().strip("()[]:")
        cx = (w[0] + w[2]) / 2
        if key in _ROLE:
            role = _ROLE[key]
            # "Measured Depth": the MD column is the leftmost depth-ish word.
            if role not in roles or (role == "md" and cx < roles[role]):
                roles[role] = cx
        elif key in _OTHER:
            cols.append(_Col("other", cx))
    if not {"inc", "azi"} <= roles.keys():
        return None
    if "md" not in roles:
        # Header says "Depth" for MD (e.g. "Measured / Depth" split oddly):
        # take the leftmost "depth"-like column left of INC.
        left = [c.x for c in cols if c.x < roles["inc"]]
        if not left:
            return None
        roles["md"] = min(left)
    if not (roles["md"] < roles["inc"] < roles["azi"]):
        return None
    cols = [c for c in cols if all(abs(c.x - x) > 6 for x in roles.values())]
    cols += [_Col(r, x) for r, x in roles.items()]
    return cols, j


def _rows_from_page(words) -> list[tuple[float, float, float]]:
    lines = _lines(words)
    out: list[tuple[float, float, float]] = []
    i = 0
    cols: list[_Col] | None = None
    while i < len(lines):
        hdr = _header_columns(lines, i)
        if hdr is not None:
            cols, i = hdr
            continue
        if cols is not None:
            vals: dict[str, tuple[float, float]] = {}  # role -> (dist, value)
            for w in lines[i]:
                v = _num(w[4])
                if v is None:
                    continue
                cx = (w[0] + w[2]) / 2
                # Numbers are right-aligned under their header: compare the
                # token's centre with each column centre, nearest wins.
                col = min(cols, key=lambda c: abs(c.x - cx))
                d = abs(col.x - cx)
                if col.role != "other" and d < 40 and (col.role not in vals or d < vals[col.role][0]):
                    vals[col.role] = (d, v)
            if {"md", "inc", "azi"} <= vals.keys():
                md, inc, azi = vals["md"][1], vals["inc"][1], vals["azi"][1]
                if 0 <= md < 60000 and 0 <= inc <= 180 and 0 <= azi <= 360:
                    out.append((md, inc, azi))
        i += 1
    return out


_NREF_VALUES = {"true": "true", "grid": "grid", "magnetic": "magnetic"}


def north_reference_on_page(words) -> str | None:
    """The value printed right of "North Reference:" on the same line.

    Survey-report headers put each label and its value in separate columns,
    so in text order the value lands lines away from its label (the old
    text rule then guessed "true" for GRID surveys).
    """
    lines = _lines(words)
    for ln in lines:
        toks = [w[4].strip().lower() for w in ln]
        for k in range(len(toks) - 1):
            if toks[k] == "north" and toks[k + 1].startswith("reference"):
                x_label = ln[k + 1][2]
                for w in ln[k + 2:]:
                    v = _NREF_VALUES.get(w[4].strip().lower().rstrip(":,"))
                    if v and w[0] >= x_label:
                        return v
    return None


def extract_survey_table(path: str | Path) -> pd.DataFrame:
    """MD/INC/AZI stations from the PDF's survey table, or an empty frame.

    Columns: ``MeasuredDepth``, ``Inclination``, ``Azimuth`` (the shape every
    survey consumer in the app expects). ``attrs["north_reference"]`` holds
    the azimuth reference printed on the survey pages ("true"/"grid"/
    "magnetic"), or None when none is printed.
    """
    import fitz  # PyMuPDF

    empty = pd.DataFrame(columns=["MeasuredDepth", "Inclination", "Azimuth"])
    nref_votes: dict[str, int] = {}
    try:
        with fitz.open(str(path)) as doc:
            rows: list[tuple[float, float, float]] = []
            for page in doc:
                words = page.get_text("words")
                page_rows = _rows_from_page(words)
                rows.extend(page_rows)
                if page_rows:
                    v = north_reference_on_page(words)
                    if v:
                        nref_votes[v] = nref_votes.get(v, 0) + len(page_rows)
    except Exception as exc:
        log.warning("survey_table.failed", path=str(path), error=str(exc))
        return empty
    # Longest run of strictly increasing MD (repeated page headers and short
    # side tables break runs; duplicates of the previous station are skipped).
    best: list[tuple[float, float, float]] = []
    run: list[tuple[float, float, float]] = []
    for r in rows:
        if run and r[0] == run[-1][0]:
            continue
        if run and r[0] < run[-1][0]:
            if len(run) > len(best):
                best = run
            run = []
        run.append(r)
    if len(run) > len(best):
        best = run
    if len(best) < 5:  # a section-details table, not a survey
        return empty
    nref = max(nref_votes, key=nref_votes.get) if nref_votes else None
    log.info("survey_table.done", path=str(path), stations=len(best),
             md_max=best[-1][0], north_reference=nref)
    df = pd.DataFrame(best, columns=["MeasuredDepth", "Inclination", "Azimuth"])
    df.attrs["north_reference"] = nref
    return df


def survey_from_pdf(path: str | Path) -> pd.DataFrame:
    """The survey carried inside an APD / WCR / survey PDF, or an empty frame.

    Tries the position-based table reader first, then the older text-rules
    reader (which handles a few plan layouts the position reader doesn't).
    Same columns and ``attrs["north_reference"]`` as
    :func:`extract_survey_table`.
    """
    df = extract_survey_table(path)
    if not df.empty:
        return df
    try:
        from etools.core.pdf.parser import _pymupdf_extract_text, _rules_extract

        r = _rules_extract(_pymupdf_extract_text(Path(path)))
    except Exception as exc:
        log.warning("survey_from_pdf.rules_failed", path=str(path), error=str(exc))
        return df
    s = r.surveys
    if s is None or s.empty or len(s) < 5:
        return df
    s = s[["MeasuredDepth", "Inclination", "Azimuth"]].reset_index(drop=True)
    s.attrs["north_reference"] = (r.north_reference or "").lower() or None
    return s
