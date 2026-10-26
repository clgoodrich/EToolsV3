"""Casing domain values the writer pre-fills over template formulas must equal
what those formulas compute (Casing Review X/Q/R/AB/AC/AD, rows 27/42/57/69).

Each expected value is the template formula evaluated by hand; the cell is
named next to it.
"""

from __future__ import annotations

import math

import pytest

from etools.core.casing_review.domain import CasingDesign, CasingStringDesign
from etools.core.casing_review.sections import SectionDefinition, SegmentData

K = 0.05194806


def _s(label, md, tvd, **kw) -> CasingStringDesign:
    base = dict(
        label=label, hole_size_in=8.75, od_in=7.0, set_depth_md_ft=md,
        set_depth_tvd_ft=tvd, weight_ppf=26, grade="P-110", collar="LTC",
    )
    base.update(kw)
    return CasingStringDesign(**base)


def test_burst_load_uses_next_tvd_and_last_string_is_hydrostatic() -> None:
    inter = _s("Intermediate", 8000, 8000, mud_weight_ppg=9.5)
    prod = _s("Production", 20000, 10000, mud_weight_ppg=10.0)
    CasingDesign(frac_gradient_psi_per_ft=1.0, strings=[inter, prod]).finalize()
    # X27 = MAX(K·MW·TVD, MIN(I39, L39)); L39 = F39 − (B49 − B34)·B51
    l_int = 10.0 * 10000 * K - (10000 - 8000) * 0.22
    assert inter.burst_load_psi == pytest.approx(max(K * 9.5 * 8000, min(8000, l_int)))
    # Last string: L = TVD·MW·K, so X = hydrostatic (not frac initiation).
    assert prod.burst_load_psi == pytest.approx(K * 10.0 * 10000)


def test_buoyed_tension_and_neutral_point_use_tvd() -> None:
    s = _s("Production", 20000, 10000, od_in=5.5, weight_ppf=20, id_in=4.778,
           mud_weight_ppg=10.0, joint_klbs=548)
    area = math.pi / 4 * (5.5**2 - 4.778**2)
    # AI = wL − 0.05194806·MW·TVD·As ; AD = AI/1000 ; AB = TVD·(1 − MW/65.4)
    expected = (20 * 20000 - K * 10.0 * 10000 * area) / 1000
    assert s.tension_air_klbs == pytest.approx(400.0)
    assert s.tension_buoyed_klbs == pytest.approx(expected)
    assert s.tension_df == pytest.approx(548 / expected)
    assert s.neutral_point_ft == pytest.approx(10000 * (1 - 10.0 / 65.4))


def test_liner_tension_and_neutral_point_hang_from_tol() -> None:
    s = _s("Liner", 19000, 9850, od_in=4.5, weight_ppf=11.6, id_in=4.0,
           mud_weight_ppg=10.0, top_depth_ft=8700, top_depth_tvd_ft=8600)
    area = math.pi / 4 * (4.5**2 - 4.0**2)
    # AH57 = E57·(MD − TOL) ; AG57 = K·MW·(TVD − TOL_TVD) ; AB57 = (…)·BF + TOL
    assert s.tension_air_klbs == pytest.approx(11.6 * (19000 - 8700) / 1000)
    assert s.tension_buoyed_klbs == pytest.approx(
        (11.6 * (19000 - 8700) - K * 10.0 * (9850 - 8600) * area) / 1000
    )
    assert s.neutral_point_ft == pytest.approx((9850 - 8600) * (1 - 10 / 65.4) + 8700)


def test_cement_height_caps_open_hole_at_previous_shoe() -> None:
    surf = _s("Surface", 2500, 2500, hole_size_in=12.25, od_in=9.625, id_in=8.921)
    inter = _s("Intermediate", 9000, 9000, hole_washout_pct=4.0,
               cement_lead_sacks=600, cement_lead_yield=2.0,
               cement_tail_sacks=300, cement_tail_yield=1.2)
    CasingDesign(strings=[surf, inter]).finalize()
    vol = 600 * 2.0 + 300 * 1.2
    cap_oh = ((8.75 * 1.04) ** 2 - 7.0**2) / 183.35
    cap_cased = (8.921**2 - 7.0**2) / 183.35
    oh = 9000 - 2500
    # Q27 = MIN(P/capOH, D34 − D19) + MAX(P − capOH·(D34 − D19), 0)/capCased
    q = min(vol / cap_oh, oh) + max(vol - cap_oh * oh, 0) / cap_cased
    assert inter.cement_height_ft == pytest.approx(q)
    assert inter.top_of_cement_ft == pytest.approx(9000 - q)


def test_liner_toc_reports_tol_when_cement_reaches_the_top() -> None:
    s = _s("Liner", 19000, 9850, od_in=4.5, top_depth_ft=8700,
           cement_tail_sacks=5000, cement_tail_yield=1.2)
    assert s.top_of_cement_ft == "TOL"


def test_bearing_only_segment_override_keeps_default_length() -> None:
    sd = SectionDefinition.__new__(SectionDefinition)
    sd.segments = {"N1": SegmentData(length_ft=1320.0, degrees=89, minutes=59,
                                     seconds=0, alignment=1, north_ref="T")}
    sd.segment_overrides = {"N1": SegmentData(degrees=88)}
    eff = sd.effective_segment("N1")
    assert eff.length_ft == 1320.0
    assert eff.degrees == 88
    assert eff.minutes == 59
