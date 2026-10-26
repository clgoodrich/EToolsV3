"""Find where each operations-log entry sits on the WCR PDF's pages.

Feeds the side-by-side operations viewer: clicking a day or an entry
scrolls the embedded PDF to that row and highlights it.

Every DDR layout prints an entry's start as ``M/D/YYYY HH:MM`` (Peloton
time log, daily blocks) or at least ``M/D/YYYY`` (report rows). We read
each page's words once, collect every date(+time) token in reading order,
then walk the entries in order with a cursor, so an entry's start is never
confused with the previous row's end time (which prints the same timestamp
on the same line, one column to the right).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from etools.logging_setup import get_logger

log = get_logger(__name__)

_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_LINE_TOL = 2.0  # pt: tokens within this of each other share a line


@dataclass(frozen=True, slots=True)
class PageSpot:
    """Where an entry starts: 0-based page, and its band as page fractions."""

    page: int
    top: float
    bottom: float


@dataclass(frozen=True, slots=True)
class _Stamp:
    page: int
    y0: float
    y1: float
    x0: float
    when: datetime
    has_time: bool


def page_sizes(path: str | Path) -> list[tuple[float, float]]:
    """(width, height) in points for every page."""
    import fitz  # PyMuPDF

    with fitz.open(str(path)) as doc:
        return [(p.rect.width, p.rect.height) for p in doc]


def _stamps(path: str | Path) -> tuple[list[_Stamp], list[float]]:
    import fitz  # PyMuPDF

    out: list[_Stamp] = []
    heights: list[float] = []
    with fitz.open(str(path)) as doc:
        for pno, page in enumerate(doc):
            heights.append(page.rect.height)
            words = sorted(page.get_text("words"), key=lambda w: (round(w[1], 1), w[0]))
            for i, w in enumerate(words):
                dm = _DATE_RE.match(w[4])
                if not dm:
                    continue
                mo, dd, yy = (int(g) for g in dm.groups())
                try:
                    day = date(yy, mo, dd)
                except ValueError:
                    continue
                hh = mi = 0
                has_time = False
                nxt = words[i + 1] if i + 1 < len(words) else None
                if nxt is not None and abs(nxt[1] - w[1]) <= _LINE_TOL:
                    tm = _TIME_RE.match(nxt[4])
                    if tm and int(tm.group(1)) < 24 and int(tm.group(2)) < 60:
                        hh, mi = int(tm.group(1)), int(tm.group(2))
                        has_time = True
                out.append(
                    _Stamp(
                        page=pno, y0=w[1], y1=w[3], x0=w[0],
                        when=datetime(day.year, day.month, day.day, hh, mi),
                        has_time=has_time,
                    )
                )
    out.sort(key=lambda s: (s.page, s.y0, s.x0))
    return out, heights


def locate_entries(path: str | Path, ddrs) -> dict[tuple[int, int], PageSpot]:
    """Map ``(ddr_index, entry_index)`` → where that entry starts in the PDF.

    Entries that can't be matched (no start time, or the timestamp isn't
    printed in a recognisable form) are simply absent from the result.
    """
    try:
        stamps, heights = _stamps(path)
    except Exception as exc:  # unreadable / missing PDF: viewer shows no jumps
        log.warning("ddr_locate.failed", error=str(exc))
        return {}
    found: dict[tuple[int, int], _Stamp] = {}
    for di, ddr in enumerate(ddrs):
        cursor = (-1, -1e9)  # (page, y): each match must come after this
        for ei, entry in enumerate(ddr.entries):
            st = entry.start_time
            if st is None:
                continue
            want_time = (st.hour, st.minute) != (0, 0)

            def after(s: _Stamp) -> bool:
                return (s.page, s.y0) > (cursor[0], cursor[1] + _LINE_TOL)

            hit = next(
                (
                    s for s in stamps
                    if after(s) and s.when.date() == st.date()
                    and (s.has_time and s.when == st if want_time else True)
                    # The start column is the left one: skip a same-line
                    # end-time stamp that matched only by its date.
                ),
                None,
            )
            if hit is None:
                continue
            found[(di, ei)] = hit
            cursor = (hit.page, hit.y0)

    # Band: from this entry's start down to the next located entry on the
    # same page (or a short default at a page break).
    spots: dict[tuple[int, int], PageSpot] = {}
    ordered = sorted(found.items(), key=lambda kv: (kv[1].page, kv[1].y0))
    for k, (key, s) in enumerate(ordered):
        h = heights[s.page] or 1.0
        nxt = ordered[k + 1][1] if k + 1 < len(ordered) else None
        if nxt is not None and nxt.page == s.page and nxt.y0 > s.y0:
            bottom = nxt.y0 - 1.0
        else:
            bottom = min(s.y1 + 48.0, h)
        spots[key] = PageSpot(
            page=s.page,
            top=max(s.y0 - 2.0, 0.0) / h,
            bottom=min(max(bottom, s.y1 + 2.0), h) / h,
        )
    log.info(
        "ddr_locate.done",
        entries=sum(len(d.entries) for d in ddrs),
        located=len(spots),
    )
    return spots
