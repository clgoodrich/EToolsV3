"""Daily Drilling Report (DDR) parser.

A WCR PDF typically contains one or more "Operation Summary Report"
appendices — one per job category (Drilling, Completion, Workover, …) —
emitted by Peloton. Each appendix is a time-log table where every rig
operation (drill, slide, trip, cement, frac, NPT, …) gets a row with
start/end timestamps, durations, phase tags, depth bookends, and a free-
text comment.

The comments are where the operator records actual events: KOP, EOC,
landing, casing point, cement jobs, FIT pressure, perforation depths,
frac stage parameters, NPT details. This module:

    1. Splits the WCR PDF text into per-DDR chunks.
    2. Extracts the well-header fields from each chunk.
    3. Walks the time log anchored on row-start timestamps.
    4. Hands back a list of ``DDRRecord`` for downstream consumers
       (key-event extraction lives in ``ddr_events.py``).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from etools.logging_setup import get_logger
from etools.models import DDRRecord, DDRTimeLogEntry

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_ddrs_from_pdf(path: str | Path) -> list[DDRRecord]:
    """Return every DDR found in the WCR PDF (zero or more)."""
    text = _extract_text(path)
    return parse_ddrs_from_text(text)


def parse_ddrs_from_text(full_text: str) -> list[DDRRecord]:
    """Parse already-extracted PyMuPDF text into DDRRecords.

    Pulled out so callers that already have the text (e.g. the WCR
    parser) don't have to re-extract.
    """
    chunks = _split_into_ddrs(full_text)
    records: list[DDRRecord] = []
    for chunk in chunks:
        record = _parse_one_ddr(chunk)
        if record is None:
            continue
        records.append(record)
    log.info("ddr.parse.done", records=len(records))
    return records


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------


def _extract_text(path: str | Path) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("PyMuPDF required to parse DDRs") from exc
    doc = fitz.open(str(path))
    return "\n".join(doc.load_page(i).get_text("text") for i in range(len(doc)))


# ---------------------------------------------------------------------------
# DDR-chunk splitting
# ---------------------------------------------------------------------------


# A DDR begins with a "Well Header" block whose "Job Category" field is
# only printed once per job, on the first page of that DDR. We anchor on
# that — the "Operation Summary Report" banner is repeated on every page
# of the appendix and would split a single DDR into 10+ pieces.
_JOB_CATEGORY_RE = re.compile(r"\bJob\s+Category\b\s*\n([^\n]+)", re.I)


def _split_into_ddrs(text: str) -> list[str]:
    """Slice the full WCR PDF text into one chunk per DDR (one per job category).

    The well-header block (Field Name / Pad Name / Legal Well Name / API)
    appears just *above* the ``Job Category`` line, so we include a 2k
    lookback when slicing — that captures the per-DDR header fields
    without leaking into the previous DDR's time-log tail.
    """
    anchors = [m.start() for m in _JOB_CATEGORY_RE.finditer(text)]
    if not anchors:
        return []
    chunks: list[str] = []
    lookback = 2000
    for i, anchor in enumerate(anchors):
        # Don't reach back into the previous DDR's chunk.
        min_start = anchors[i - 1] if i > 0 else 0
        start = max(min_start, anchor - lookback)
        end = anchors[i + 1] if i + 1 < len(anchors) else len(text)
        chunks.append(text[start:end])
    return chunks


# ---------------------------------------------------------------------------
# Per-DDR parser
# ---------------------------------------------------------------------------


_HEADER_FIELDS = {
    "job_category": re.compile(r"Job Category\s*\n([^\n]+)", re.I),
    "well_name": re.compile(r"Legal Well Name\s*\n([^\n]+)", re.I),
    "api": re.compile(r"API/UWI\s*\n(\d{10,14})", re.I),
    "pad_name": re.compile(r"Pad Name\s*\n([^\n]+)", re.I),
    "start_date": re.compile(r"\bStart Date\s*\n(\d{1,2}/\d{1,2}/\d{4})", re.I),
    "end_date": re.compile(r"\bEnd Date\s*\n(\d{1,2}/\d{1,2}/\d{4})", re.I),
}


_TIMESTAMP_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2})\b")


def _parse_one_ddr(chunk: str) -> DDRRecord | None:
    # ---- header fields ----
    header: dict = {}
    for field, pat in _HEADER_FIELDS.items():
        m = pat.search(chunk)
        if m:
            header[field] = m.group(1).strip()

    record = DDRRecord(
        job_category=header.get("job_category"),
        well_name=header.get("well_name"),
        api=header.get("api"),
        pad_name=header.get("pad_name"),
        start_date=_parse_date(header.get("start_date")),
        end_date=_parse_date(header.get("end_date")),
    )

    # ---- time-log rows ----
    # Anchor on the "Time Log" section if present so we don't pick up
    # the "Start Date" header in the well-header block.
    time_log_match = re.search(r"\bTime\s+Log\b", chunk, re.I)
    body = chunk[time_log_match.end():] if time_log_match else chunk

    record.entries = _parse_time_log(body)
    log.info(
        "ddr.parse.one",
        job=record.job_category,
        well=record.well_name,
        api=record.api,
        rows=len(record.entries),
    )
    return record


# ---------------------------------------------------------------------------
# Time-log row walker
# ---------------------------------------------------------------------------


# Page-footer / report-printed lines that show up between rows in the PDF
# text; we strip them so they don't end up in comments.
_NOISE_LINES = (
    re.compile(r"^www\.peloton\.com.*$", re.I | re.MULTILINE),
    re.compile(r"^Page\s+\d+/\d+\s*$", re.I | re.MULTILINE),
    re.compile(r"^Report Printed:.*$", re.I | re.MULTILINE),
    re.compile(r"^SOUTH MOON.*$", re.I | re.MULTILINE),  # generic well-name banner; harmless
    re.compile(r"^Operation Summary Report\s*$", re.I | re.MULTILINE),
    re.compile(r"^Pad:\s+.*$", re.I | re.MULTILINE),
    re.compile(r"^Sundry Number:.*$", re.I | re.MULTILINE),
    re.compile(r"^RECEIVED:.*$", re.I | re.MULTILINE),
    re.compile(r"^Job:.*$", re.I | re.MULTILINE),
    re.compile(r"^District:.*$", re.I | re.MULTILINE),
    re.compile(r"^Time Log\s*$", re.I | re.MULTILINE),
    re.compile(r"^Start Date\s*$", re.I | re.MULTILINE),
    re.compile(r"^End Date\s*$", re.I | re.MULTILINE),
    re.compile(r"^Dur\s*\(hr\)\s*$", re.I | re.MULTILINE),
    re.compile(r"^Phase\s*$", re.I | re.MULTILINE),
    re.compile(r"^Code\s*\d\s*$", re.I | re.MULTILINE),
    re.compile(r"^Ops\s*$", re.I | re.MULTILINE),
    re.compile(r"^Category\s*$", re.I | re.MULTILINE),
    re.compile(r"^Start Depth\s*$", re.I | re.MULTILINE),
    re.compile(r"^\(ftKB\)\s*$", re.I | re.MULTILINE),
    re.compile(r"^End Depth\s*$", re.I | re.MULTILINE),
    re.compile(r"^Com\s*$", re.I | re.MULTILINE),
)


def _clean_body(body: str) -> str:
    out = body
    for pat in _NOISE_LINES:
        out = pat.sub("", out)
    # Collapse 3+ blank lines into 2 for predictability.
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def _parse_time_log(body: str) -> list[DDRTimeLogEntry]:
    """Find every (start_ts, end_ts) pair and parse the row that follows."""
    body = _clean_body(body)
    # A row begins with TWO consecutive timestamps (start, end). Anchor on
    # that pair so we don't get fooled by timestamps inside comments.
    pair_re = re.compile(
        rf"({_TIMESTAMP_RE.pattern})\s*\n?\s*({_TIMESTAMP_RE.pattern})",
        re.MULTILINE,
    )

    rows: list[DDRTimeLogEntry] = []
    matches = list(pair_re.finditer(body))
    for i, m in enumerate(matches):
        start_str = f"{m.group(2)} {m.group(3)}"  # date + time of start
        end_str = f"{m.group(5)} {m.group(6)}"
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        row_text = body[m.end():next_start]
        try:
            entry = _parse_row(
                index=len(rows),
                start_ts=start_str,
                end_ts=end_str,
                row_text=row_text,
            )
        except Exception as exc:
            log.debug("ddr.row_parse_skip", error=str(exc), row_idx=len(rows))
            continue
        if entry is not None:
            rows.append(entry)
    return rows


_FLOAT_RE = re.compile(r"^\d{1,3}(?:,\d{3})*(?:\.\d+)?$")
_FLOAT_PLUS_REST_RE = re.compile(r"^\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s+(.+)$")
# "PT" / "NPT" are the productive-time markers in drilling DDRs. Completion
# DDRs sometimes leave the column blank or use "INACTIVE"; we treat
# anything that's just one of these tokens (possibly followed by a "–"
# subtype) as the anchor.
_OPS_LINE_RE = re.compile(r"^\s*(PT|NPT|INACTIVE)\b")


def _parse_row(
    *,
    index: int,
    start_ts: str,
    end_ts: str,
    row_text: str,
) -> DDRTimeLogEntry | None:
    """Parse a single time-log row using a line-based state machine.

    Column order:
        duration  phase  code1  code2  ops_cat  start_depth  end_depth  comment

    The PDF wraps long cell values across lines, but each cell's content
    stays on its own line(s). We anchor on the ops-category (``PT`` /
    ``NPT``) line — depths follow it, the mixed phase+code1+code2 block
    precedes it.
    """
    lines = [ln.rstrip() for ln in row_text.splitlines() if ln.strip()]
    if not lines:
        return None

    # ---- duration (first token of the first line) ----
    m = re.match(r"\s*(\d+\.\d+)\s*(.*)$", lines[0])
    if not m:
        return None
    duration = float(m.group(1))
    first_remainder = m.group(2).strip()

    # ---- locate the ops-category anchor (PT / NPT / INACTIVE) ----
    ops_idx: int | None = None
    ops_cat: str | None = None
    for i, line in enumerate(lines[1:], start=1):
        om = _OPS_LINE_RE.match(line.strip())
        if om:
            ops_idx = i
            ops_cat = om.group(1)
            break

    # Some completion-DDR rows merge every cell onto a single line and have
    # no PT/NPT marker at all. Fall back to a single-line regex parser; if
    # that also fails, drop the row entirely into ``comment`` so we don't
    # lose the operator's note.
    if ops_idx is None:
        return _parse_row_single_line(
            index=index,
            start_ts=start_ts,
            end_ts=end_ts,
            duration=duration,
            line=first_remainder,
            extras=lines[1:],
        )

    # The PT/NPT line sometimes has trailing detail (e.g. "NPT – Mud Pumps"
    # gets split across "NPT –", "Mud", "Pumps"). Skip continuation lines
    # that aren't pure floats — they belong to the trouble-type column.
    cursor = ops_idx + 1
    while cursor < len(lines) and not _FLOAT_RE.match(lines[cursor].strip()):
        cursor += 1

    # ---- depths ----
    start_depth: float | None = None
    end_depth: float | None = None
    comment_chunks: list[str] = []

    if cursor < len(lines) and _FLOAT_RE.match(lines[cursor].strip()):
        start_depth = _to_float(lines[cursor])
        cursor += 1
    if cursor < len(lines):
        line = lines[cursor]
        # End depth usually shares its line with the start of the comment.
        m2 = _FLOAT_PLUS_REST_RE.match(line)
        if m2:
            end_depth = _to_float(m2.group(1))
            comment_chunks.append(m2.group(2))
            cursor += 1
        elif _FLOAT_RE.match(line.strip()):
            end_depth = _to_float(line)
            cursor += 1

    # Remaining lines are comment continuation.
    comment_chunks.extend(lines[cursor:])
    comment = " ".join(comment_chunks).strip() if comment_chunks else None
    if comment:
        comment = re.sub(r"\s+", " ", comment) or None

    # ---- phase + code1 + code2 block ----
    block = ([first_remainder] if first_remainder else []) + lines[1:ops_idx]
    phase, code1, code2 = _split_phase_block(block)

    return DDRTimeLogEntry(
        index=index,
        start_time=_parse_datetime(start_ts),
        end_time=_parse_datetime(end_ts),
        duration_hr=duration,
        phase=phase,
        code1=code1,
        code2=code2,
        ops_category=ops_cat,
        start_depth_ftkb=start_depth,
        end_depth_ftkb=end_depth,
        comment=comment,
    )


def _parse_row_single_line(
    *,
    index: int,
    start_ts: str,
    end_ts: str,
    duration: float | None,
    line: str,
    extras: list[str],
) -> DDRTimeLogEntry:
    """Fallback when a completion-DDR row flattens onto one line.

    We can't reliably split phase/code1/code2 from a single line, so we
    take what we can and dump the rest into the comment. Examples:

        "Inactive INACTIVE 22,201.0 waiting on Cactus/daylight"
        "Toe Prep, <code2> Safety Meeting SMTG Safety meeting w/ ..."
    """
    body = " ".join([line, *extras]).strip()
    body = re.sub(r"\s+", " ", body)

    # Many completion-DDR rows have a phase with a literal "<code2>" tag
    # in the template; strip those so they don't pollute the comment.
    body = re.sub(r"<code\d+>", "", body, flags=re.I).strip()
    body = re.sub(r"\s+", " ", body)

    # Completion-style rows like "Frac, Perforating PFRT Stage: 1 Open
    # Well: 2,530 psi Plug Depth: 19,212' MD..." have NO depth columns —
    # the numbers in the comment are labeled values, not start/end depth.
    # We detect those rows by content cues and route them straight to
    # "everything after the head is comment" handling.
    annotated_content = bool(
        re.search(
            r"\b(?:Stage|Open\s+Well|Plug\s+Depth|Plug\s+type|Perf\s+Depths?|"
            r"Avg\s+RT|Max\s+RT|Total\s+Fluid|Max\s+Rate|Max\s+psi)\b",
            body,
            re.I,
        )
    )

    # Try to pluck the depths (one or two floats with optional commas).
    start_depth = end_depth = None
    comment = body
    head = ""
    if annotated_content:
        # Take the head as the words up to the first content-cue keyword.
        cue = re.search(
            r"\b(?:Stage|Open\s+Well|Plug\s+Depth|Plug\s+type|Perf\s+Depths?|"
            r"Avg\s+RT|Max\s+RT|Total\s+Fluid|Max\s+Rate|Max\s+psi|"
            r"Safety\s+meeting|MIRU|RDMO|WSI|Test\s+|Function\s+test|"
            r"Pumped|Drilled|Stab|Open\s+well|Pulled|Begin|Continue|Set|Cont\.)\b",
            body,
            re.I,
        )
        if cue:
            head = body[: cue.start()].strip()
            comment = body[cue.start():].strip()
        else:
            head = ""
            comment = body
    else:
        depth_match = re.search(
            r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s+(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s+(.+)$",
            body,
        )
        if depth_match:
            start_depth = _to_float(depth_match.group(1))
            end_depth = _to_float(depth_match.group(2))
            head = body[: depth_match.start()].strip()
            comment = depth_match.group(3).strip()
        else:
            single = re.search(r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s+(.+)$", body)
            if single:
                start_depth = _to_float(single.group(1))
                head = body[: single.start()].strip()
                comment = single.group(2).strip()
            else:
                head = body
                comment = ""

    # Pull a code2 (short all-caps tag) out of the head if present.
    # Examples: "Toe Prep, Safety Meeting SMTG" → code2=SMTG
    #           "Frac, Frac. Job FRAC" → code2=FRAC
    phase = code1 = code2 = None
    if head:
        # Phase = first "X, Y" segment, code2 = last ALL-CAPS token in head.
        ph = re.match(r"^([A-Za-z][\w.]*,\s*[A-Za-z][\w. ]*?)(?=\s+[A-Z]|\s*$)", head)
        if ph:
            phase = re.sub(r"\s+", " ", ph.group(1)).strip().rstrip(",")
            head = head[ph.end():].strip()
        tag_match = re.search(r"\b([A-Z][A-Z0-9]{2,7})\b\s*$", head)
        if tag_match:
            code2 = tag_match.group(1)
            head = head[: tag_match.start()].strip()
        if head:
            code1 = re.sub(r"\s+", " ", head)
    # Some rows have only a single-word phase like "Inactive" / "Toe Prep,"
    if phase is None and head and not code1 and not code2:
        phase = head

    return DDRTimeLogEntry(
        index=index,
        start_time=_parse_datetime(start_ts),
        end_time=_parse_datetime(end_ts),
        duration_hr=duration,
        phase=phase,
        code1=code1,
        code2=code2,
        ops_category=None,
        start_depth_ftkb=start_depth,
        end_depth_ftkb=end_depth,
        comment=comment or None,
    )


def _is_all_upper(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def _split_phase_block(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    """Split the mixed (phase, code1, code2) block from a list of lines.

    code2 is the trailing run of all-uppercase lines. The remaining
    lines, joined, are split into phase (first 'X, Y' fragment) and
    code1 (the rest).
    """
    if not lines:
        return None, None, None
    # Walk back to pick up code2 (contiguous all-uppercase lines at end).
    end = len(lines)
    while end > 0 and _is_all_upper(lines[end - 1]):
        end -= 1
    code2 = " ".join(lines[end:]).strip() or None
    head = lines[:end]
    if not head:
        return None, None, code2

    joined = " ".join(s.strip() for s in head if s.strip())
    # Strip a trailing hyphen that survives wrapping like "Drilling -\nRotate"
    joined = re.sub(r"\s+-\s+", " - ", joined).strip()

    # Phase is the first "X, Y" segment (e.g. "Surface, Drill").
    phase_match = re.match(r"^([A-Za-z][\w ]*?,\s*[A-Za-z][\w ]*?)(?=\s+[A-Z]|\s*$)", joined)
    if phase_match:
        phase = re.sub(r"\s+", " ", phase_match.group(1)).strip().rstrip(",")
        code1 = joined[phase_match.end():].strip() or None
        if code1:
            code1 = re.sub(r"\s+", " ", code1)
    else:
        # No comma — entire block is the phase (rare).
        phase = re.sub(r"\s+", " ", joined).strip()
        code1 = None

    return phase or None, code1, code2


def _to_float(s: str) -> float | None:
    try:
        return float(s.strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%-m/%-d/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%m/%d/%Y %H:%M",):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
