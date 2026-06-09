"""BOPE (Blowout-Preventer Equipment) review.

Replicates the workbook's ``BOPE`` sheet exactly — same inputs, same
per-string "Calculations" block, same formulas (all off the casing string's
TVD) — so the app's BOPE tab and the written sheet show identical numbers.

Header inputs (BOPE sheet rows 5-11, columns C/D/E/F = the casing strings):
    Casing Size (")                     = string OD
    Setting Depth (TVD)                 = string set-depth TVD
    Previous Shoe Setting Depth (TVD)   = prior string's setting TVD (surface→0)
    Max Mud Weight (ppg)                = string mud weight
    BOPE Proposed (psi)                 = permit-stated rating, else inferred
    Casing Internal Yield (psi)         = string burst strength
    Operators Max Anticipated Pressure  = max gas MASP across strings

Per-string "Calculations" block (rows 13-21):
    Max BHP [psi]            = 0.052 * Setting Depth * MW
    MASP (Gas) [psi]         = Max BHP - 0.12 * Setting Depth
    MASP (Gas/Mud) [psi]     = Max BHP - 0.22 * Setting Depth
    Pressure At Previous Shoe= Max BHP - 0.22 * (Setting Depth - Previous Shoe)
    Required Casing/BOPE Test Pressure
    *Max Pressure Allowed @ Previous Casing Shoe
plus the three YES/NO adequacy checks.
"""
from __future__ import annotations

from dataclasses import dataclass

from etools.core.casing_review.domain import CasingDesign, CasingStringDesign

# API standard BOP stack working-pressure ratings (psi): 2M/3M/5M/10M/15M.
STANDARD_BOPE_RATINGS_PSI: tuple[int, ...] = (2000, 3000, 5000, 10000, 15000)

# BOPE-sheet constants (match the worksheet cells exactly).
_BHP_GRAD = 0.052       # psi/ft/ppg — mud hydrostatic (C14 uses 0.052)
_GAS_GRAD = 0.12        # psi/ft — gas column backup
_GAS_MUD_GRAD = 0.22    # psi/ft — gas/mud column backup
_TEST_YIELD_FRAC = 0.70  # casing/BOPE test = 70% of internal yield


def proposed_bope_psi(masp_psi: float | None) -> int | None:
    """Smallest standard stack rating that exceeds ``masp_psi``."""
    if masp_psi is None:
        return None
    for r in STANDARD_BOPE_RATINGS_PSI:
        if r > masp_psi:
            return r
    return STANDARD_BOPE_RATINGS_PSI[-1]


def _min_skip_none(*vals: float | None) -> float | None:
    nums = [v for v in vals if v is not None]
    return min(nums) if nums else None


@dataclass
class BOPEStringReview:
    label: str
    od_in: float | None
    setting_depth_tvd_ft: float | None
    prev_shoe_tvd_ft: float
    mud_weight_ppg: float | None
    max_bhp_psi: float | None
    masp_gas_psi: float | None
    masp_gas_mud_psi: float | None
    pressure_at_prev_shoe_psi: float | None
    bope_proposed_psi: int | float | None
    bope_proposed_from_pdf: bool
    internal_yield_psi: float | None
    adequate_gas: bool | None
    adequate_gas_mud: bool | None
    hold_full_at_prev_shoe: bool | None
    required_test_pressure_psi: float | None = None
    max_pressure_allowed_prev_shoe_psi: float | None = None


@dataclass
class BOPEReview:
    strings: list[BOPEStringReview]
    operators_max_anticipated_pressure_psi: float | None
    equivalent_mud_weight_ppg: float | None


def _string_review(
    s: CasingStringDesign,
    prev_shoe_tvd: float,
    *,
    is_surface: bool,
    pdf_psi: float | None,
) -> BOPEStringReview:
    tvd = s.set_depth_tvd_ft
    mw = s.mud_weight_ppg
    if tvd is None or mw is None:
        max_bhp = masp_gas = masp_gas_mud = press_prev = None
    else:
        max_bhp = _BHP_GRAD * tvd * mw
        masp_gas = max_bhp - _GAS_GRAD * tvd
        masp_gas_mud = max_bhp - _GAS_MUD_GRAD * tvd
        press_prev = max_bhp - _GAS_MUD_GRAD * (tvd - prev_shoe_tvd)

    # The permit's BOP rating applies below the surface casing (Onshore Order
    # 2 — installed before drilling out the surface shoe). Surface drilling
    # predates the stack, so the surface rating is always inferred.
    if pdf_psi is not None and not is_surface:
        proposed: int | float | None = pdf_psi
        from_pdf = True
    else:
        proposed = proposed_bope_psi(masp_gas)
        from_pdf = False

    yield_psi = s.burst_psi
    return BOPEStringReview(
        label=s.label,
        od_in=s.od_in,
        setting_depth_tvd_ft=tvd,
        prev_shoe_tvd_ft=prev_shoe_tvd,
        mud_weight_ppg=mw,
        max_bhp_psi=max_bhp,
        masp_gas_psi=masp_gas,
        masp_gas_mud_psi=masp_gas_mud,
        pressure_at_prev_shoe_psi=press_prev,
        bope_proposed_psi=proposed,
        bope_proposed_from_pdf=from_pdf,
        internal_yield_psi=yield_psi,
        adequate_gas=(proposed > masp_gas) if (proposed and masp_gas is not None) else None,
        adequate_gas_mud=(proposed > masp_gas_mud) if (proposed and masp_gas_mud is not None) else None,
        hold_full_at_prev_shoe=(prev_shoe_tvd > press_prev) if press_prev is not None else None,
    )


def build_bope_review(
    design: CasingDesign, *, bope_system_psi: float | None = None
) -> BOPEReview:
    """Compute the per-string BOPE review for a finalized casing design.

    ``bope_system_psi`` is the permit-stated BOP rating (``APDPdfData.
    bope_system_psi``). When given it is used as-is for the strings drilled
    with the stack (below surface); otherwise every rating is inferred.
    """
    rows: list[BOPEStringReview] = []
    prev_shoe = 0.0  # surface string has no previous casing shoe
    for idx, s in enumerate(design.strings):
        rows.append(
            _string_review(s, prev_shoe, is_surface=idx == 0, pdf_psi=bope_system_psi)
        )
        if s.set_depth_tvd_ft is not None:
            prev_shoe = s.set_depth_tvd_ft

    # Second pass — the two derived rows that need cross-string context.
    for i, r in enumerate(rows):
        nxt = rows[i + 1].bope_proposed_psi if i + 1 < len(rows) else None
        test_yield = (
            _TEST_YIELD_FRAC * r.internal_yield_psi
            if r.internal_yield_psi is not None else None
        )
        # Required Casing/BOPE Test Pressure (C20): if a deeper string exists,
        # the smaller of {this setting depth, 70%·yield, next string's rating};
        # otherwise {this rating, setting depth, 70%·yield}.
        if nxt:
            r.required_test_pressure_psi = _min_skip_none(
                r.setting_depth_tvd_ft, test_yield, nxt
            )
        else:
            r.required_test_pressure_psi = _min_skip_none(
                r.bope_proposed_psi, r.setting_depth_tvd_ft, test_yield
            )
        # *Max Pressure Allowed @ Previous Casing Shoe (C21): if full pressure
        # can't be held, the smaller of {previous shoe, pressure at prev shoe};
        # otherwise the previous-shoe depth.
        if r.hold_full_at_prev_shoe is False:
            r.max_pressure_allowed_prev_shoe_psi = _min_skip_none(
                r.prev_shoe_tvd_ft, r.pressure_at_prev_shoe_psi
            )
        else:
            r.max_pressure_allowed_prev_shoe_psi = r.prev_shoe_tvd_ft

    masps = [r.masp_gas_psi for r in rows if r.masp_gas_psi is not None]
    op_max = max(masps) if masps else None
    tvds = [r.setting_depth_tvd_ft for r in rows if r.setting_depth_tvd_ft]
    eq_mw = (op_max / (_BHP_GRAD * max(tvds))) if (op_max and tvds) else None
    return BOPEReview(
        strings=rows,
        operators_max_anticipated_pressure_psi=op_max,
        equivalent_mud_weight_ppg=eq_mw,
    )
