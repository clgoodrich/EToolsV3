"""Scan APD PDFs for casing tables with strings beyond Cond/Surf/I1/Prod.

Uses the APD parser's own text extraction (PyMuPDF, all pages) with a
broader tag set than the rules parser (L1/L2, P2, I2, Liner, ...) so
extra strings the parser would skip still show up. A tag line only
counts as a casing row when it's followed by the table's value dump
(numeric hole size + a "top - bottom" interval) — this filters out the
plat sheets' LINE-TABLE labels (L1, L2, ...) that share the same shape.

Run: PYTHONPATH=. .venv/Scripts/python scripts/find_multi_string_apds.py [root]
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

from etools.core.pdf.apd_parser import _STRING_TAGS, _extract_text

TAG_RE = re.compile(
    r"^\s*(Cond|Surf|I[1-9]|Prod\s?[1-9]?|Liner\s?[1-9]?|L[1-9]|P[2-9]|T[1-9])\s*$"
)
NUM_RE = re.compile(r"^\s*\d+(?:\.\d+)?\s*$")
INTERVAL_RE = re.compile(r"^\s*\d+(?:,\d{3})*(?:\.\d+)?\s*-\s*\d+(?:,\d{3})*(?:\.\d+)?\s*$")
BASIC = {"Cond", "Surf", "I1", "Prod"}


def casing_tags(text: str) -> list[str]:
    """Tag lines that are followed by casing-table values."""
    lines = text.splitlines()
    out = []
    for i, ln in enumerate(lines):
        m = TAG_RE.fullmatch(ln)
        if not m:
            continue
        nxt = [x for x in lines[i + 1 : i + 6] if x.strip()]
        # Real rows: hole size (number) right after the tag, and the
        # "top - bottom" set interval within the next few lines.
        if (
            nxt
            and NUM_RE.fullmatch(nxt[0])
            and any(INTERVAL_RE.fullmatch(x) for x in nxt[:4])
        ):
            out.append(m.group(1).strip())
    return out


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "tests"
    pdfs = sorted(set(glob.glob(f"{root}/**/application_*.pdf", recursive=True)))
    print(f"{len(pdfs)} APD PDFs under {root}/")
    hits = 0
    for p in pdfs:
        try:
            tags = casing_tags(_extract_text(Path(p)))
        except Exception as exc:
            print(f"!! {p}: {type(exc).__name__}: {exc}")
            continue
        extra = [t for t in tags if t not in BASIC]
        unknown = [t for t in extra if t not in _STRING_TAGS]
        marker = ""
        if extra:
            hits += 1
            marker = f"  <<< EXTRA: {','.join(extra)}"
            if unknown:
                marker += f"  (NOT parsed by rules: {','.join(unknown)})"
        print(f"{','.join(tags) or '(no casing table found)':30} {p}{marker}")
    print(f"\n{hits} PDF(s) with strings beyond Cond/Surf/I1/Prod")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
