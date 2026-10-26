"""Regression tests for APD / WCR / survey-PDF field extraction bugs.

The APD expectations come from the hand-made reference Casing Review for
Myton City UT 16-23 3-2-25-36-7H (``tests/APD/Casing Review_43013537270000_*``)
and from what the permit itself prints.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from etools.core.pdf import apd_parser, parser as survey_parser
from etools.core.pdf.wcr_parser import _extract_header as wcr_extract_header
from etools.models import APDPdfData, WCRPdfData

MYTON = Path(__file__).parent / "fixtures" / "apd" / "application_43013537270000.pdf"


@pytest.fixture(scope="module")
def myton() -> APDPdfData:
    return apd_parser.parse_apd_pdf(MYTON, mode="rules", use_llm=False)


def test_apd_slant_reads_the_filled_radio(myton: APDPdfData) -> None:
    assert myton.slant == "HORIZONTAL"  # used to always be "VERTICAL"


def test_apd_formation_tops_match_reference_sheet(myton: APDPdfData) -> None:
    tops = [(f.name, f.md_ft) for f in myton.formations if f.name != "BMSGW"]
    assert tops == [
        ("Uinta", 0.0),
        ("Green River", 3135.0),
        ("Garden Gulch", 5854.0),
        ("Uteland Butte", 8238.0),
    ]


def test_apd_frac_gradient_is_the_printed_14_ppg(myton: APDPdfData) -> None:
    # Was 1.0, read from the "1" in the 4 1/2" casing size.
    assert myton.frac_gradient_psi_per_ft == pytest.approx(14 * 0.05194806, abs=1e-4)


def test_apd_frac_gradient_ignores_prose() -> None:
    data = APDPdfData()
    apd_parser._extract_frac_gradient(
        "per the frac gradient of the casing shoe. The design \nuses 8 joints\n", data
    )
    assert data.frac_gradient_psi_per_ft is None


def test_apd_frac_gradient_prose_statement() -> None:
    data = APDPdfData()
    apd_parser._extract_frac_gradient(
        "Frac gradient at surface casing shoe = 10.5 ppg\n"
        "Frac gradient at intermediate casing shoe = 12 ppg\n",
        data,
    )
    assert data.frac_gradient_psi_per_ft == pytest.approx(12 * 0.05194806, abs=1e-4)


@pytest.mark.parametrize(
    "cell,grade,collar",
    [("J-55 ST&C", "J-55", "STC"), ("N-80 LT&C", "N-80", "LTC"),
     ("N-80 Buttress", "N-80", "BTC"), ("P-110 Other", "P-110", None),
     ("P-110 BTC", "P-110", "BTC")],
)
def test_apd_grade_and_collar(cell: str, grade: str, collar: str | None) -> None:
    m = apd_parser._GRADE_THREAD_RE.search(cell)
    assert m.group(1).strip() == grade
    assert apd_parser._normalize_collar(m.group(2)) == collar


def test_wcr_blank_tvd_does_not_read_next_section_number() -> None:
    data = WCRPdfData()
    wcr_extract_header(
        "24. TOTAL DEPTH\n      MD 18676          TVD 8950\n"
        "25. PLUGGED BACK TOTAL DEPTH\n      MD 18616          TVD \n"
        "26. CURRENT WELL STATUS\n",
        data,
    )
    assert (data.total_md_ft, data.total_tvd_ft) == (18676.0, 8950.0)
    assert (data.pbtd_md_ft, data.pbtd_tvd_ft) == (18616.0, None)


def test_survey_latlon_needs_value_on_the_label_line() -> None:
    text = "Name\nTVD\n+N/-S\n+E/-W\nLatitude\nLongitude\n0.0\n39.0758\n"
    assert survey_parser._extract_lat(text) is None
    assert survey_parser._extract_lon(text) is None
    assert survey_parser._extract_lat("Latitude: 39.059335\n") == pytest.approx(39.059335)
