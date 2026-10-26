"""Everything that used to come from SQL Server now comes from the PDFs.

Expected values were checked against DOGM's database before it was removed
from the app: every station, the north reference, the casing/cement rows and
the perforation date matched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from etools.core.pdf.survey_table import extract_survey_table, survey_from_pdf
from etools.core.pdf.wcr_form import (
    casing_frame,
    extract_casing,
    extract_stamp,
    extract_treatment_start,
)
from etools.core.pdf.wcr_parser import _collapse_padded_dates

FX = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "pdf,rows,md_max,nref",
    [
        # APD directional plan, grid north.
        ("apd/application_43013537270000.pdf", 194, 18591.63, "grid"),
        # WCR with the as-drilled survey report attached, true north.
        ("wcr/WCR 43013543050000.pdf", 222, 20514.0, "true"),
        # WCR survey report referenced to grid north.
        ("wcr/WCR 43047570050000.pdf", 207, 18676.0, "grid"),
    ],
)
def test_survey_table_read_by_position(pdf, rows, md_max, nref) -> None:
    s = extract_survey_table(FX / pdf)
    assert len(s) == rows
    assert s["MeasuredDepth"].max() == pytest.approx(md_max, abs=0.01)
    assert s["MeasuredDepth"].is_monotonic_increasing
    assert s.attrs["north_reference"] == nref


def test_survey_from_pdf_falls_back_to_text_rules() -> None:
    # A plan layout only the older text reader handles.
    s = survey_from_pdf(FX / "apd/application_4304756010.pdf")
    assert len(s) == 210
    assert s.attrs["north_reference"] == "true"


def test_wcr_without_a_survey_returns_empty() -> None:
    assert survey_from_pdf(FX / "wcr/WCR 43013539960000.pdf").empty


def test_section_28_casing_matches_the_form() -> None:
    rows = extract_casing(FX / "wcr/WCR 43013539960000.pdf")
    got = [(r.feature, r.diameter, r.bottom_md, r.cement_stage, r.sacks, r.yield_) for r in rows]
    assert got == [
        ("Conductor Pipe", 16.0, 128.0, "L", 390, 1.15),
        ("Surface Casing", 9.625, 1505.0, "L", 200, 2.66),
        ("Surface Casing", 9.625, 1505.0, "T", 300, 1.43),
        ("Intermediate Casing", 7.0, 8001.0, "L", 460, 2.06),
        ("Intermediate Casing", 7.0, 8001.0, "T", 585, 1.8),
        ("Liner", 4.5, 19263.0, "L", 865, 1.53),
    ]
    surf = rows[1]
    assert (surf.hole_size, surf.weight, surf.grade, surf.connection_type) == (12.25, 36.0, "J-55", "BTC")
    frame = casing_frame(rows)
    holes = frame[frame["Feature"] == "Hole"][["Top_MD", "Bottom_MD", "Diameter"]].values.tolist()
    assert holes == [[0.0, 128.0, 24.0], [128.0, 1505.0, 12.25], [1505.0, 8001.0, 8.75], [8001.0, 19263.0, 6.125]]


def test_tubing_and_tapered_string() -> None:
    rows = extract_casing(FX / "wcr/WCR 43047560590000.pdf")
    tubing = [r for r in rows if r.feature == "Tubing"]
    assert [(t.diameter, t.bottom_md) for t in tubing] == [(2.875, 7636.0)]
    # The production string's second stage is the 5" section to TD.
    prod = [r for r in rows if r.feature.startswith("Production")]
    assert (prod[-1].diameter, prod[-1].bottom_md, prod[-1].sacks) == (5.0, 18491.0, 1190)


def test_stamp_and_treatment_date() -> None:
    text = (
        "FORM 8\nSundry Number: 133008 API: 43013539960000\nRECEIVED: Oct. 08, 2024\n"
        "35. WELL TREATMENTS (FR ...)\nSTART DATE\nEND DATE\n6\nWATER\n8808\n19202\n"
        "07/04/2024\n07/31/2024\n25,342,318 lbs\n36. LOGS\n"
    )
    assert extract_stamp(text) == ("133008", "10/8/2024")
    assert extract_treatment_start(text) == "7/4/2024"


def test_padded_dates_stay_on_their_line() -> None:
    raw = "1 9 2 0 2\n0 7 / 0 4 / 2 0 2 4\n0 7 / 3 1 / 2 0 2 4\n"
    assert _collapse_padded_dates(raw) == "1 9 2 0 2\n07/04/2024\n07/31/2024\n"
