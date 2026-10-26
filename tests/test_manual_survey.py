"""Typed / pasted surveys: paste parsing and validation."""

from __future__ import annotations

import pytest

from etools.core.survey.manual import build_manual_survey, parse_pasted_rows


def test_excel_block_without_header() -> None:
    text = "0\t0\t0\r\n1,500\t0.5\t212.3\r\n7765.5\t12.25\t181\r\n"
    assert parse_pasted_rows(text) == [
        (0.0, 0.0, 0.0), (1500.0, 0.5, 212.3), (7765.5, 12.25, 181.0)
    ]


def test_excel_header_picks_columns_by_name() -> None:
    # A full survey export: the MD / Inc / Azi columns aren't the first three.
    text = (
        "Station\tMeasured Depth\tTVD\tInc\tAzi\tNorth\n"
        "1\t0\t0\t0\t0\t0\n"
        "2\t100\t99.9\t1.5\t45\t1.3\n"
    )
    assert parse_pasted_rows(text) == [(0.0, 0.0, 0.0), (100.0, 1.5, 45.0)]


def test_text_copied_from_a_pdf_or_csv() -> None:
    text = "MD Inc Azi\n100.00 0.25 310.10\n200,1.5,45\nPage 2 of 9\n"
    assert parse_pasted_rows(text) == [(100.0, 0.25, 310.1), (200.0, 1.5, 45.0)]


def test_csv_with_three_digit_azimuths() -> None:
    # The thousands-separator rule used to glue "1.5,245.3" into one cell.
    text = "MD,Inc,Azi\n1000,1.5,245.3\n2000,90,180\n"
    assert parse_pasted_rows(text) == [(1000.0, 1.5, 245.3), (2000.0, 90.0, 180.0)]
    spaced = "1,500.00 3.40 140.00 1,350.00\n"
    assert parse_pasted_rows(spaced) == [(1500.0, 3.4, 140.0)]


def test_build_sorts_skips_blanks_and_keeps_reference() -> None:
    df = build_manual_survey(
        [("200", "1.5", "45"), (None, None, None), (0, 0, 0), ("", "", "")], "true"
    )
    assert df["MeasuredDepth"].tolist() == [0.0, 200.0]
    assert df.attrs["north_reference"] == "true"
    assert list(df.columns) == ["MeasuredDepth", "Inclination", "Azimuth"]


@pytest.mark.parametrize(
    "rows,ref,msg",
    [
        ([(0, 0, 0), (100, 1, None)], "grid", "Row 2"),
        ([(0, 0, 0), (100, 200, 0)], "grid", "inclination"),
        ([(0, 0, 0), (100, 1, 400)], "grid", "azimuth"),
        ([(0, 0, 0), (0, 1, 10)], "grid", "twice"),
        ([(0, 0, 0)], "grid", "at least two"),
        ([(0, 0, 0), (100, 1, 10)], "", "True or Grid"),
    ],
)
def test_build_rejects_bad_rows(rows, ref, msg) -> None:
    with pytest.raises(ValueError, match=msg):
        build_manual_survey(rows, ref)
