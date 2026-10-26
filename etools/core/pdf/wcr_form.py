"""Form 8 (WCR) fields that need page geometry or the page stamp.

* Section 28 — HOLE, CASING AND CEMENT INFORMATION. The form prints every
  string as one row (plus a row per extra cement stage), and its number
  fields are character-spaced: "1 9 2 6 3" is 19263. In text order the cells
  interleave, which is why the old line-based reader returned empty rows.
  Here the row/column grid is rebuilt from word positions.
* The page stamp — "Sundry Number: 133008 API: … RECEIVED: Oct. 08, 2024".
* Section 35 — WELL TREATMENTS start dates (the stimulation/perforation date).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from etools.logging_setup import get_logger
from etools.models import CasingRow

log = get_logger(__name__)

# Form code → feature name used in the WCR workbook (same names the DOGM
# database uses, so generated workbooks read the same as before).
STRING_FEATURES = {
    "COND": "Conductor Pipe",
    "SURF": "Surface Casing",
    "INT": "Intermediate Casing",
    "I1": "Intermediate Casing",
    "I2": "Intermediate Casing 2",
    "PROD": "Production Casing",
    "PROD1": "Production Casing",
    "PROD2": "Production Casing 2",
    "P1": "Production Casing",
    "P2": "Production Casing 2",
    "LINER": "Liner",
    "TUBING": "Tubing",
}

# Header words → column key, left to right. "WEIGHT" appears twice (casing
# weight, then cement weight); "TOP"/"CEMENT" appear in two places.
_COLUMNS = (
    "string", "hole", "od", "weight", "grade", "thread", "top", "bottom",
    "dv", "stage", "cement_type", "sacks", "yield", "cement_weight",
    "cement_top", "basis",
)


def _merge_spaced(line: list) -> list[tuple[float, float, str]]:
    """Join character-spaced form-field digits back into tokens.

    Consecutive one-character words with (almost) no gap are one field.
    """
    out: list[list] = []
    for w in line:
        t = w[4]
        if (
            out
            and len(t) == 1
            and out[-1][3]  # previous token is a char run
            and w[0] - out[-1][1] < 2.5
        ):
            out[-1][1] = w[2]
            out[-1][2] += t
            continue
        out.append([w[0], w[2], t, len(t) == 1])
    return [(a, b, t) for a, b, t, _ in out]


def _lines(words) -> list[list]:
    lines: list[list] = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        cy = (w[1] + w[3]) / 2
        if lines and abs((lines[-1][0][1] + lines[-1][0][3]) / 2 - cy) <= 2.5:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(ln, key=lambda w: w[0]) for ln in lines]


def _header_x(header_words) -> dict[str, float] | None:
    """Column left edges from the Section 28 header words."""
    xs: dict[str, float] = {}
    weights = []
    tops = []
    cements = []
    for w in header_words:
        t = w[4].upper().strip()
        if t == "STRING":
            xs["string"] = w[0]
        elif t == "HOLE":
            xs.setdefault("hole", w[0])
        elif t == "CASING":
            xs.setdefault("od", w[0])
        elif t == "WEIGHT":
            weights.append(w[0])
        elif t == "GRADE":
            xs["grade"] = w[0]
        elif t == "THREAD":
            xs["thread"] = w[0]
        elif t == "TOP":
            tops.append(w[0])
        elif t == "BOTTOM":
            xs["bottom"] = w[0]
        elif t == "DV":
            xs["dv"] = w[0]
        elif t == "LEAD":
            xs["stage"] = w[0]
        elif t == "CEMENT":
            cements.append(w[0])
        elif t == "SACKS":
            xs["sacks"] = w[0]
        elif t == "YIELD":
            xs["yield"] = w[0]
        elif t == "BASIS":
            xs["basis"] = w[0]
    weights.sort()
    if weights:
        xs["weight"] = weights[0]
    if len(weights) > 1:
        xs["cement_weight"] = weights[1]
    tops.sort()
    if tops:
        xs["top"] = tops[0]
    if len(tops) > 1:
        # TOP (MD) | CEMENT TOP | "BASIS FOR TOP": the second one.
        xs["cement_top"] = tops[1]
    if cements:
        # "CEMENT TYPE" is the cement word left of SACKS; "CEMENT TOP" the
        # one right of the cement weight.
        left = [c for c in cements if c < xs.get("sacks", 1e9)]
        right = [c for c in cements if c > xs.get("cement_weight", 1e9)]
        if left:
            xs["cement_type"] = max(left)
        if right:
            xs.setdefault("cement_top", min(right))
    need = {"string", "hole", "od", "weight", "grade", "thread", "top", "bottom"}
    return xs if need <= xs.keys() else None


def _column_of(x0: float, starts: list[tuple[float, str]]) -> str | None:
    col = None
    for sx, key in starts:
        if x0 >= sx - 8:
            col = key
    return col


def _num(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def extract_casing(path: str | Path) -> list[CasingRow]:
    """Section 28 rows (one per cement stage) then Section 29 tubing rows,
    values exactly as printed."""
    import fitz  # PyMuPDF

    try:
        with fitz.open(str(path)) as doc:
            for page in list(doc)[:4]:
                words = page.get_text("words")
                rows = _casing_from_page(words)
                if rows:
                    return rows + _tubing_from_page(words)
    except Exception as exc:
        log.warning("wcr_form.casing_failed", error=str(exc))
    return []


def _tubing_from_page(words) -> list[CasingRow]:
    """Section 29 TUBING RECORD: size, top MD, bottom MD (packer ignored)."""
    lines = _lines(words)
    start = next(
        (i for i, ln in enumerate(lines)
         if ln[0][4] == "29." and any(w[4].upper() == "TUBING" for w in ln)),
        None,
    )
    if start is None or start + 1 >= len(lines):
        return []
    hdr = {w[4].upper(): w[0] for w in lines[start + 1]}
    if not {"TOP", "BOT"} <= hdr.keys():
        return []
    edges = sorted(
        [(min(hdr.get("TUBING", 0), hdr.get("SIZE", 0)) or 0, "size"),
         (hdr["TOP"], "top"), (hdr["BOT"], "bottom"),
         (hdr.get("PACKER", 1e9), "packer")]
    )
    out: list[CasingRow] = []
    for ln in lines[start + 2:]:
        if re.fullmatch(r"\d{2}\.", ln[0][4]):
            break
        cells: dict[str, list[str]] = {}
        for x0, _x1, t in _merge_spaced(ln):
            col = _column_of(x0, edges)
            if col:
                cells.setdefault(col, []).append(t)
        size = _num(" ".join(cells.get("size", [])))
        if size is None:
            continue
        out.append(CasingRow(
            feature="Tubing", diameter=size,
            top_md=_num(" ".join(cells.get("top", []))),
            bottom_md=_num(" ".join(cells.get("bottom", []))),
        ))
    return out


def _casing_from_page(words) -> list[CasingRow]:
    lines = _lines(words)
    start = next(
        (i for i, ln in enumerate(lines)
         if ln[0][4] == "28." and any(w[4].upper().startswith("CASING") for w in ln)),
        None,
    )
    if start is None:
        return []
    header: list = []
    body: list[list] = []
    for ln in lines[start + 1:]:
        if re.fullmatch(r"\d{2}\.", ln[0][4]):  # next numbered section
            break
        first = ln[0][4].upper()
        if not body and first not in STRING_FEATURES:
            header.extend(ln)
            continue
        body.append(ln)
    xs = _header_x(header)
    if xs is None:
        return []
    starts = sorted((x, k) for k, x in xs.items())
    rows: list[CasingRow] = []
    current: dict | None = None
    for ln in body:
        cells: dict[str, list[str]] = {}
        for x0, _x1, t in _merge_spaced(ln):
            col = _column_of(x0, starts)
            if col:
                cells.setdefault(col, []).append(t)
        get = {k: " ".join(v).strip() for k, v in cells.items()}
        code = get.get("string", "").upper()
        if code in STRING_FEATURES:
            current = {
                "feature": STRING_FEATURES[code],
                "hole_size": _num(get.get("hole")),
                "diameter": _num(get.get("od")),
                "weight": _num(get.get("weight")),
                "grade": get.get("grade") or None,
                "connection_type": get.get("thread") or None,
                "top_md": _num(get.get("top")),
                "bottom_md": _num(get.get("bottom")),
            }
        elif current is None:
            continue
        else:
            # A row with no string code is a continuation: another cement
            # stage, or the next section of a tapered string (its own size
            # and depths). Whatever it prints replaces the string's values.
            for key, col in (
                ("hole_size", "hole"), ("diameter", "od"), ("weight", "weight"),
                ("top_md", "top"), ("bottom_md", "bottom"),
            ):
                v = _num(get.get(col))
                if v is not None:
                    current[key] = v
            for key, col in (("grade", "grade"), ("connection_type", "thread")):
                if get.get(col):
                    current[key] = get[col]
        if not any(get.get(k) for k in ("stage", "cement_type", "sacks")) and rows and code not in STRING_FEATURES:
            continue
        sacks = _num(get.get("sacks"))
        rows.append(
            CasingRow(
                **current,
                cement_stage=get.get("stage") or None,
                cement_type=get.get("cement_type") or None,
                sacks=int(sacks) if sacks is not None else None,
                yield_=_num(get.get("yield")),
                cement_weight=_num(get.get("cement_weight")),
                cement_top=_num(get.get("cement_top")),
                cement_bottom=current["bottom_md"],
            )
        )
    return rows


_SUNDRY_RE = re.compile(r"Sundry Number:\s*(\d+)")
_RECEIVED_RE = re.compile(r"RECEIVED:\s*([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})")


def extract_stamp(text: str) -> tuple[str | None, str | None]:
    """(sundry number, RECEIVED date "m/d/YYYY") from the page stamp."""
    s = _SUNDRY_RE.search(text)
    r = _RECEIVED_RE.search(text)
    received = None
    if r:
        mon = r.group(1)[:3].title()
        try:
            d = datetime.strptime(f"{mon} {r.group(2)} {r.group(3)}", "%b %d %Y")
            received = f"{d.month}/{d.day}/{d.year}"
        except ValueError:
            received = None
    return (s.group(1) if s else None), received


_S35_RE = re.compile(r"35\.\s*WELL TREATMENTS(.*?)(?:\n\s*36\.|$)", re.S | re.I)
_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def extract_treatment_start(text: str) -> str | None:
    """Latest Section 35 START DATE ("m/d/YYYY").

    Each treatment row prints START DATE then END DATE, so the starts are
    every other date in the block.
    """
    m = _S35_RE.search(text)
    if not m:
        return None
    dates = []
    for mm, dd, yy in _DATE_RE.findall(m.group(1)):
        try:
            dates.append(datetime(int(yy), int(mm), int(dd)))
        except ValueError:
            continue
    starts = dates[0::2]
    if not starts:
        return None
    d = max(starts)
    return f"{d.month}/{d.day}/{d.year}"


CASING_FRAME_COLUMNS = (
    "Feature", "Top_MD", "Bottom_MD", "Diameter", "Weight", "Grade",
    "ConnectionType", "CementTop", "CementBottom", "CementType", "Sacks",
    "Yield", "CementWeight",
)


def casing_frame(rows: list[CasingRow]):
    """Section 28/29 rows → the casing table the WCR workbook writes.

    Same shape the DOGM database used to supply: one "Hole" row per hole
    section (top = previous hole's bottom), then one row per casing/cement
    stage and tubing.
    """
    import pandas as pd

    holes = []
    seen = set()
    prev_bottom = 0.0
    for r in rows:
        if r.feature == "Tubing" or r.hole_size is None or r.bottom_md is None:
            continue
        key = (r.hole_size, r.bottom_md)
        if key in seen:
            continue
        seen.add(key)
        holes.append({"Feature": "Hole", "Top_MD": prev_bottom,
                      "Bottom_MD": r.bottom_md, "Diameter": r.hole_size})
        prev_bottom = r.bottom_md
    strings = [
        {
            "Feature": r.feature, "Top_MD": r.top_md, "Bottom_MD": r.bottom_md,
            "Diameter": r.diameter, "Weight": r.weight, "Grade": r.grade,
            "ConnectionType": r.connection_type, "CementTop": r.cement_top,
            "CementBottom": r.cement_bottom, "CementType": r.cement_type,
            "Sacks": r.sacks, "Yield": r.yield_, "CementWeight": r.cement_weight,
        }
        for r in rows
    ]
    return pd.DataFrame(holes + strings, columns=list(CASING_FRAME_COLUMNS))
