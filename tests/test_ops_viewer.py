"""Operations viewer: entries are located on the right PDF row, and the
reformatted log keeps the operator's wording (layout-only changes)."""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

import fitz
import pytest

from etools.core.pdf.ddr_locate import locate_entries
from etools.core.pdf.ddr_parser import parse_ddrs_from_pdf
from etools.models import DDRRecord, DDRTimeLogEntry
from etools.ui.ops_viewer import build_log_html, build_pdf_html

WCR = Path(__file__).parent / "fixtures" / "wcr" / "WCR 43013539960000.pdf"


@pytest.fixture(scope="module")
def ddrs():
    return parse_ddrs_from_pdf(WCR)


def _norm(s: str) -> str:
    return re.sub(r"\W+", "", s or "").upper()


def test_every_entry_lands_on_its_own_row(ddrs) -> None:
    spots = locate_entries(WCR, ddrs)
    assert len(spots) == sum(len(d.entries) for d in ddrs)
    with fitz.open(WCR) as doc:
        checked = 0
        for (di, ei), sp in spots.items():
            words = (ddrs[di].entries[ei].comment or "").split()[:3]
            if not words:
                continue
            pg = doc[sp.page]
            h = pg.rect.height
            band = pg.get_text(clip=fitz.Rect(0, sp.top * h, pg.rect.width, sp.bottom * h + 30))
            if sp.page + 1 < len(doc):
                band += doc[sp.page + 1].get_text(clip=fitz.Rect(0, 0, pg.rect.width, 140))
            assert _norm(" ".join(words)) in _norm(band), (di, ei)
            checked += 1
    assert checked > 300


def test_locate_entries_survives_a_missing_pdf(ddrs) -> None:
    assert locate_entries("no/such.pdf", ddrs) == {}


def test_log_html_keeps_wording_and_escapes() -> None:
    e = DDRTimeLogEntry(
        index=0,
        start_time=datetime(2024, 7, 12, 2, 0), end_time=datetime(2024, 7, 12, 5, 0),
        duration_hr=3.0, phase="Frac, <code2>", code1="Frac. Job", code2="FRAC",
        ops_category="NPT", start_depth_ftkb=128.0, end_depth_ftkb=1900.0,
        comment="Stage 12\nOW: 3,120 psi   <<<PAGE>>>  Avg RT - 84 bpm",
        trouble=["stuck pipe"],
    )
    ddr = DDRRecord(job_category="Completion", entries=[e])
    out = build_log_html([ddr], {})
    assert "Stage 12 OW: 3,120 psi Avg RT - 84 bpm" in out  # verbatim, whitespace tidied
    assert "<<<PAGE>>>" not in out
    assert "Frac, &lt;code2&gt;" in out and "<code2>" not in out  # escaped
    assert "02:00 – 05:00" in out and "128 → 1,900 ftKB" in out
    assert "Friday, July 12, 2024" in out
    assert "stuck pipe" in out and ">NPT<" in out
    assert html.unescape(out).count("Stage 12") == 1


def test_pdf_html_one_lazy_image_per_page() -> None:
    out = build_pdf_html("tok", [(612.0, 792.0), (638.3, 1052.25)])
    assert out.count('loading="lazy"') == 2
    assert "/etools-pdf/tok/1.png" in out and 'id="ops-hl"' in out
