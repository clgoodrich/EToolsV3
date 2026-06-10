"""DDR appendix parsing — the three Peloton layouts + narrative chunking.

Fixture-driven: each test pins the entry counts the walkers extract from a
real WCR PDF so a regression in one layout can't hide behind another.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from etools.core.pdf.ddr_events import detect_trouble, extract_events, trouble_excerpt
from etools.core.pdf.ddr_llm import _chunk_entries, _narrative_line
from etools.core.pdf.ddr_parser import parse_ddrs_from_pdf
from etools.models import DDRTimeLogEntry

FIXTURES = Path(__file__).parent / "fixtures" / "wcr"


def _ddrs(name: str):
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"fixture {name} not present")
    return parse_ddrs_from_pdf(path)


def test_columnar_time_log_layout():
    ddrs = {d.job_category: d for d in _ddrs("WCR 43013539950000.pdf")}
    assert len(ddrs["Drilling"].entries) == 320
    assert len(ddrs["Completion"].entries) == 236
    # Columnar rows carry depths + PT/NPT.
    assert any(e.start_depth_ftkb is not None for e in ddrs["Drilling"].entries)
    assert any(e.ops_category == "PT" for e in ddrs["Drilling"].entries)


def test_daily_blocks_layout():
    (ddr,) = _ddrs("WCR 43013540190000.pdf")
    assert ddr.job_category == "Completion"
    assert len(ddr.entries) == 12
    first = ddr.entries[0]
    assert first.start_time == datetime(2024, 6, 25, 8, 0)
    assert first.end_time == datetime(2024, 6, 25, 9, 0)
    assert first.duration_hr == 1.0
    assert first.phase == "Install Tubing head"
    assert "tubing head" in (first.comment or "").lower()
    # The 24-hour frac days carry the full multi-kB account.
    assert max(len(e.comment or "") for e in ddr.entries) > 2500


def test_daily_blocks_survive_time_log_phrase_in_comment():
    # This PDF says "time log" inside a comment; the anchor must not
    # slice the appendix away.
    (ddr,) = _ddrs("WCR 43013540300000.pdf")
    assert len(ddr.entries) == 11


def test_report_rows_layout():
    ddrs = {d.job_category: d for d in _ddrs("WCR 43013543510000.pdf")}
    assert len(ddrs["Drilling"].entries) == 26
    assert len(ddrs["Completion"].entries) == 31
    e = ddrs["Drilling"].entries[1]
    assert e.start_time == datetime(2022, 12, 25)
    assert e.end_time == datetime(2022, 12, 26)
    assert "skid rig" in (e.comment or "").lower()


def _entry(i: int, comment: str) -> DDRTimeLogEntry:
    return DDRTimeLogEntry(index=i, comment=comment)


def test_narrative_chunking_packs_by_count_and_chars():
    short = [_entry(i, "x" * 50) for i in range(70)]
    chunks = _chunk_entries(short, max_entries=30, char_budget=100_000, comment_chars=4000)
    assert [len(c) for c in chunks] == [30, 30, 10]

    long = [_entry(i, "y" * 3000) for i in range(5)]
    chunks = _chunk_entries(long, max_entries=30, char_budget=7000, comment_chars=4000)
    # ~3KB comments → 2 per chunk under the 7KB budget.
    assert [len(c) for c in chunks] == [2, 2, 1]
    # Nothing dropped, order preserved.
    assert [e.index for c in chunks for e in c] == [0, 1, 2, 3, 4]


def _c(comment: str, **kw) -> DDRTimeLogEntry:
    return DDRTimeLogEntry(index=0, comment=comment, **kw)


def test_detect_trouble_categories():
    assert detect_trouble(_c("Pipe stuck @ 8200, jarring to work string free")) == [
        "stuck pipe"
    ]
    assert detect_trouble(_c("RIH w/ overshot, fishing for parted tubing")) == [
        "fishing",
        "twist-off / parted",
    ]
    assert "equipment failure" in detect_trouble(
        _c("Weatherford power swivel kept losing torque, called for replacement")
    )
    assert "leak" in detect_trouble(_c("BOP door seals leaking, X-over repair"))
    assert "lost circulation" in detect_trouble(_c("Lost returns @ 4,200, mixed LCM"))
    assert "well control" in detect_trouble(
        _c("Well flowing & surging, RIH to set kill plug")
    )
    assert "screen-out" in detect_trouble(_c("Stage 12 screened out, flushed well"))
    assert detect_trouble(_c("Drilled 17.5in surface from 1,600 to 2,400")) == []


def test_detect_trouble_negation_and_routine():
    # Negated mentions don't flag.
    assert detect_trouble(_c("Pressure tested stack to 10,000 psi, no leaks")) == []
    assert detect_trouble(_c("Checked for H2S, none detected")) == []
    # Frac formation breakdown is routine, not equipment failure.
    assert detect_trouble(
        _c("Initial breakdown pressure 2100 @ 10 bpm, pumped 1000 gals HCL")
    ) == []
    # Routine bit trips don't flag; failed bits do.
    assert detect_trouble(_c("CBU, TOOH, C/O Bit, Inspect M/Mtr (OK), TIH")) == []
    assert "bit problem" in detect_trouble(_c("TOOH, bit rung out, lost cone in hole"))
    # The NPT column still counts on columnar layouts.
    assert detect_trouble(_c("Rig repair", ops_category="NPT")) == [
        "NPT",
        "equipment failure",
    ]


def test_trouble_flags_stamped_and_excerpt():
    (ddr,) = _ddrs("WCR 43013540190000.pdf")
    extract_events(ddr)
    flagged = [e for e in ddr.entries if e.trouble]
    # June 28: swivel losing torque + BOP door seals leaking.
    june28 = next(e for e in ddr.entries if e.index == 1)
    assert "equipment failure" in june28.trouble and "leak" in june28.trouble
    assert len(flagged) >= 2
    ex = trouble_excerpt(june28)
    assert ex and len(ex) <= 200


def test_narrative_line_keeps_long_comments():
    e = DDRTimeLogEntry(index=0, comment="z" * 5000, phase="Frac ops")
    assert len(_narrative_line(e, 4000)) >= 4000
    assert "Frac ops" in _narrative_line(e, 4000)
