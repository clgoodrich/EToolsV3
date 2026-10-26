"""Casing Review TVDs from an MD / Inc / Azi survey (PDF or typed)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from etools.core.casing_review.engine import CasingDesignEngine, welltrack_from_dataframe
from etools.core.pdf.apd_parser import parse_apd_pdf
from etools.core.pdf.survey_table import survey_from_pdf

APD = Path(__file__).parent / "fixtures" / "apd" / "application_43013537270000.pdf"


def test_vertical_then_build_by_minimum_curvature() -> None:
    df = pd.DataFrame(
        {"MeasuredDepth": [0, 1000, 2000], "Inclination": [0, 0, 90], "Azimuth": [0, 0, 0]}
    )
    wt = welltrack_from_dataframe(df)
    assert [round(p.tvd_ft, 1) for p in wt] == [0.0, 1000.0, round(1000 + 2000 / 3.14159265, 1)]


@pytest.mark.skipif(not APD.exists(), reason="fixture APD missing")
def test_apd_plan_tvds_match_the_hand_made_review() -> None:
    # These used to be the straight-hole estimate (1900 / 7650): the plan has
    # no TVD column, so the survey was silently dropped. The hand-made 7H
    # review has B19 = 1894.19 and B34 = 8237.92.
    apd = parse_apd_pdf(APD, mode="rules")
    design = CasingDesignEngine().build(apd, welltrack=welltrack_from_dataframe(survey_from_pdf(APD)))
    tvd = {s.label: s.set_depth_tvd_ft for s in design.strings}
    assert tvd["Surface"] == pytest.approx(1894.19, abs=0.5)
    assert tvd["Intermediate"] == pytest.approx(8237.92, abs=0.5)
    assert tvd["Production"] == pytest.approx(7649.93, abs=0.5)
