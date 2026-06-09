"""BOPE review math + workbook population."""
from __future__ import annotations

from etools.core.casing_review.bope import (
    STANDARD_BOPE_RATINGS_PSI,
    build_bope_review,
    proposed_bope_psi,
)
from etools.core.casing_review.domain import CasingDesign, CasingStringDesign


def _string(label, od, set_md, set_tvd, mw, intgrad=0.12):
    return CasingStringDesign(
        label=label, hole_size_in=0.0, od_in=od, set_depth_md_ft=set_md,
        set_depth_tvd_ft=set_tvd, weight_ppf=20.0, grade="J55", collar="STC",
        cement_lead_sacks=None, cement_lead_yield=None, cement_lead_weight_ppg=None,
        cement_tail_sacks=None, cement_tail_yield=None, cement_tail_weight_ppg=None,
        mud_weight_ppg=mw, hole_washout_pct=0.0, internal_gradient_psi_per_ft=intgrad,
        backup_mud_ppg=0.0, internal_mud_ppg=0.0, buoyed=True,
    )


def _design():
    d = CasingDesign(
        company="X", well_name="W", api="1", frac_gradient_psi_per_ft=1.0,
        strings=[
            _string("Surface", 9.625, 2500, 2500, 8.4),
            _string("Intermediate", 7.0, 9193, 8330, 11.5),
            _string("Production", 4.5, 19097, 8330, 14.0),
        ],
    )
    d.finalize()
    return d


def test_proposed_ladder():
    assert proposed_bope_psi(300) == 2000
    assert proposed_bope_psi(792) == 2000
    assert proposed_bope_psi(3981) == 5000
    assert proposed_bope_psi(5064) == 10000
    assert proposed_bope_psi(20000) == STANDARD_BOPE_RATINGS_PSI[-1]
    assert proposed_bope_psi(None) is None


def test_review_values():
    r = build_bope_review(_design())
    surf, inter, prod = r.strings
    # Surface: no previous shoe; BHP = 0.052*2500*8.4 = 1092; MASP gas = 792.
    assert surf.prev_shoe_tvd_ft == 0
    assert round(surf.max_bhp_psi) == 1092
    assert round(surf.masp_gas_psi) == 792
    assert surf.bope_proposed_psi == 2000
    # Previous shoe of each string = prior string's setting TVD.
    assert inter.prev_shoe_tvd_ft == 2500
    assert prod.prev_shoe_tvd_ft == 8330
    # Production governs the operator's max anticipated pressure.
    assert prod.bope_proposed_psi == 10000
    assert round(r.operators_max_anticipated_pressure_psi) == round(prod.masp_gas_psi)
    # All proposed ratings clear their gas MASP.
    assert all(s.adequate_gas for s in r.strings)


def test_missing_tvd_is_safe():
    d = CasingDesign(strings=[_string("Surface", 9.625, 2500, None, 8.4)])
    d.finalize()
    r = build_bope_review(d)
    s = r.strings[0]
    assert s.max_bhp_psi is None and s.bope_proposed_psi is None
    assert r.operators_max_anticipated_pressure_psi is None


def test_pdf_rating_used_for_subsurface_only():
    r = build_bope_review(_design(), bope_system_psi=5000)
    surf, inter, prod = r.strings
    # Surface drills before the stack → always inferred (bold red in the UI).
    assert surf.bope_proposed_from_pdf is False
    # Below-surface strings take the permit-stated rating as-is.
    assert inter.bope_proposed_psi == 5000 and inter.bope_proposed_from_pdf is True
    assert prod.bope_proposed_psi == 5000 and prod.bope_proposed_from_pdf is True


def test_derived_rows_present():
    r = build_bope_review(_design())
    for s in r.strings:
        assert s.required_test_pressure_psi is not None
        assert s.max_pressure_allowed_prev_shoe_psi is not None
