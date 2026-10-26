"""Rich domain model for a casing-design review.

Holds the input data and exposes computed properties so a single
``CasingDesign`` instance can drive every output sheet (Casing Review,
DataPrint, Vertical WBD, BOPE summary) without re-parsing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# Default minimum design factors used by the Newfield engineering review.
# Pulled from the I1:K9 block of the reference Casing Review sheet.
DEFAULT_MIN_DF = {
    "collapse": 1.125,
    "burst": 1.0,
    "tension_stc": 1.8,
    "tension_ltc": 1.8,
    "tension_btc": 1.6,
    "tension_premium": 1.5,
    "tension_body_yield": 1.6,
}


@dataclass
class CasingStringDesign:
    """One casing string: inputs + computed strength + load + design factors."""

    label: str  # "Surface" / "Intermediate" / "Production" / "Liner"
    hole_size_in: float
    od_in: float
    set_depth_md_ft: float
    set_depth_tvd_ft: float | None  # interpolated from welltrack
    weight_ppf: float
    grade: str
    collar: str | None

    # Top of the string (APD "length top"). 0/None = run from surface; a
    # non-zero value means the string is hung off inside the previous one,
    # i.e. a liner. Drives STRING-block placement — see ``block_index``.
    top_depth_ft: float | None = None
    # TVD at ``top_depth_ft`` (liner top), template DxSurvey!H69. A liner's
    # buoyed tension and neutral point are measured from it.
    top_depth_tvd_ft: float | None = None

    # Cement
    cement_lead_sacks: int | None = None
    cement_lead_yield: float | None = None       # ft^3/sx
    cement_lead_weight_ppg: float | None = None  # density
    cement_tail_sacks: int | None = None
    cement_tail_yield: float | None = None
    cement_tail_weight_ppg: float | None = None

    # Engineering inputs
    mud_weight_ppg: float = 9.0
    hole_washout_pct: float = 10.0  # surface default; deeper rows ~4%
    internal_gradient_psi_per_ft: float = 0.22
    backup_mud_ppg: float = 0.0
    internal_mud_ppg: float = 0.0
    buoyed: bool = True

    # Next-string knobs (for max-shoe-pressure / burst-load coupling). Set
    # by the parent CasingDesign in ``finalize``.
    next_set_depth_md_ft: float | None = None
    next_set_depth_tvd_ft: float | None = None
    next_mud_weight_ppg: float | None = None
    next_string_internal_gradient_psi_per_ft: float | None = None
    # Previous (shallower) string's shoe MD and ID: cement overflowing the
    # open hole rises inside that casing (template Q27).
    prev_set_depth_md_ft: float | None = None
    prev_id_in: float | None = None

    # Strength catalog results (populated by the engine).
    collapse_psi: float | None = None
    burst_psi: float | None = None
    joint_klbs: float | None = None
    body_klbs: float | None = None
    id_in: float | None = None

    # Which STRING N block of the Casing Review template this string occupies
    # (0-based: 0 → STRING 1 at row 10, … 3 → STRING 4 at row 55). Assigned by
    # the engine. This is deliberately NOT the string's position in
    # ``CasingDesign.strings`` — a production *liner* always occupies STRING 4,
    # leaving STRING 3 empty, which is how the hand-made reviews are laid out.
    # Everything except the workbook writer iterates the strings list in
    # sequence and should ignore this field. ``None`` means "unassigned" (a
    # design built by hand rather than by the engine); the writer then falls
    # back to list position. Do NOT default this to 0 — that would put every
    # such string in STRING 1.
    block_index: int | None = None

    @property
    def is_liner(self) -> bool:
        """True when the string hangs off inside the previous one rather than
        running from surface (APD 'length top' > 0)."""
        return bool(self.top_depth_ft)

    # ----- Computed -----
    @property
    def cement_total_volume_ft3(self) -> float:
        """Lead + tail cement volume in ft³ (sacks * yield)."""
        v = 0.0
        if self.cement_lead_sacks and self.cement_lead_yield:
            v += self.cement_lead_sacks * self.cement_lead_yield
        if self.cement_tail_sacks and self.cement_tail_yield:
            v += self.cement_tail_sacks * self.cement_tail_yield
        return v

    @property
    def annular_capacity_ft3_per_ft(self) -> float:
        """Annular volume per foot, including hole-washout factor.

        Uses the spreadsheet's formula: ((hole*(1+washout%/100))^2 - OD^2) / 183.35
        """
        wash = 1.0 + self.hole_washout_pct / 100.0
        hole_effective = wash * self.hole_size_in
        cap = (hole_effective**2 - self.od_in**2) / 183.35
        # A physically impossible geometry (OD ≥ effective hole) yields a
        # negative "capacity". Clamp to 0 so callers using this directly don't
        # get a nonsense negative; ``cement_height_ft`` already treats 0 as
        # "no annulus" and returns None.
        return cap if cap > 0.0 else 0.0

    @property
    def cement_height_ft(self) -> float | None:
        """Height covered by the lead+tail cement in the annulus.

        Template Q27/Q42/Q57: cement fills the open hole up to the previous
        shoe at the washed-out capacity, and any excess rises inside the
        previous casing at ``(prev_ID² − OD²)/183.35`` (no washout):

            MIN(P/capOH, shoe − prev_shoe)
              + MAX(P − capOH·(shoe − prev_shoe), 0) / capCased

        The surface string (no previous casing) is plain ``P/capOH``.
        """
        cap = self.annular_capacity_ft3_per_ft
        if cap <= 0:
            return None
        vol = self.cement_total_volume_ft3
        if self.prev_set_depth_md_ft is None or not self.prev_id_in:
            return vol / cap
        cap_cased = (self.prev_id_in**2 - self.od_in**2) / 183.35
        if cap_cased <= 0:
            return vol / cap
        oh_len = max(self.set_depth_md_ft - self.prev_set_depth_md_ft, 0.0)
        return min(vol / cap, oh_len) + max(vol - cap * oh_len, 0.0) / cap_cased

    @property
    def top_of_cement_ft(self) -> float | str | None:
        """TOC = string set depth − cement height.

        "Surface" if the cement reaches grade; for a liner, "TOL" once it
        reaches the liner top (template R57).
        """
        h = self.cement_height_ft
        if h is None:
            return None
        toc = self.set_depth_md_ft - h
        if self.is_liner and toc <= (self.top_depth_ft or 0.0):
            return "TOL"
        return "Surface" if toc <= 0 else toc

    # Frac gradient (psi/ft) the engineer used for frac-initiation
    # pressure caps. Stored on the string so each one can use a different
    # design assumption; defaults to the design-wide value at finalize time.
    frac_gradient_psi_per_ft: float = 1.0

    @property
    def masp_psi(self) -> float | None:
        """Maximum Anticipated Surface Pressure with a gas-to-surface kick.

        Matches the reference spreadsheet's S-column formula:
            MASP = 0.05194806 * MW * TVD  -  internal_gradient * TVD
        Read it as: hydrostatic mud pressure at the shoe minus the
        backpressure of the fluid column displacing back up the inside
        of the casing.
        """
        if self.set_depth_tvd_ft is None:
            return None
        return (
            0.05194806 * self.mud_weight_ppg * self.set_depth_tvd_ft
            - self.internal_gradient_psi_per_ft * self.set_depth_tvd_ft
        )

    @property
    def collapse_load_psi(self) -> float | None:
        """Hydrostatic collapse load: 0.05194806 * (MW - backup_mud) * TVD."""
        if self.set_depth_tvd_ft is None:
            return None
        return 0.05194806 * (self.mud_weight_ppg - self.backup_mud_ppg) * self.set_depth_tvd_ft

    @property
    def collapse_df(self) -> float | None:
        if not self.collapse_psi or not self.collapse_load_psi:
            return None
        return self.collapse_psi / self.collapse_load_psi

    @property
    def burst_load_psi(self) -> float | None:
        """Burst load at the casing shoe.

        Reproduces the X-column formula from the reference workbook when
        backup-mud = 0 (the typical case):

            burst_load = MAX(
                hydrostatic,                                # gas kick to surface
                MIN(
                    frac_initiation_at_shoe,                # frac-grad capped
                    next_shoe_pressure - internal_grad_drop # max pressure shoe sees
                                                            # from a deeper kick
                )
            )

        With no deeper string the next-shoe term collapses out.
        """
        if self.set_depth_tvd_ft is None:
            return None
        hydrostatic = 0.05194806 * self.mud_weight_ppg * self.set_depth_tvd_ft
        frac_init = self.frac_gradient_psi_per_ft * self.set_depth_tvd_ft
        # The template's footer L (max pressure at shoe) is all TVD: next
        # BHP = next MW · next TVD · K, less the next string's internal
        # gradient over the TVD between shoes. With no deeper string L is
        # this shoe's own hydrostatic, so the load is hydrostatic, not the
        # frac-initiation pressure.
        next_tvd = (
            self.next_set_depth_tvd_ft
            if self.next_set_depth_tvd_ft is not None
            else self.next_set_depth_md_ft
        )
        shoe_cap = hydrostatic
        if (
            next_tvd is not None
            and self.next_mud_weight_ppg is not None
            and self.next_string_internal_gradient_psi_per_ft is not None
        ):
            next_shoe_bhp = 0.05194806 * self.next_mud_weight_ppg * next_tvd
            depth_delta = next_tvd - self.set_depth_tvd_ft
            shoe_cap = (
                next_shoe_bhp
                - self.next_string_internal_gradient_psi_per_ft * depth_delta
            )
        return max(hydrostatic, min(frac_init, shoe_cap))

    @property
    def burst_df(self) -> float | None:
        if not self.burst_psi or not self.burst_load_psi:
            return None
        return self.burst_psi / self.burst_load_psi

    @property
    def tension_air_klbs(self) -> float | None:
        """Tension at top of string in air = weight × hung length / 1000.

        A liner hangs from its top, so its length is shoe − top (AH57).
        """
        if self.set_depth_md_ft is None:
            return None
        length = self.set_depth_md_ft - (self.top_depth_ft or 0.0)
        return self.weight_ppf * length / 1000.0

    def _vertical_column_ft(self) -> float:
        """Vertical height of the hung string: shoe TVD − top TVD."""
        tvd = self.set_depth_tvd_ft
        if tvd is None:
            tvd = self.set_depth_md_ft
        top = self.top_depth_tvd_ft
        if top is None:
            top = self.top_depth_ft or 0.0
        return tvd - top

    @property
    def tension_buoyed_klbs(self) -> float | None:
        """Buoyed tension by pressure-area at TVD (template AI/AD):

            (wL − 0.05194806 · MW · TVD · π/4·(OD² − ID²)) / 1000

        On a horizontal the bottom pressure acts at TVD, not MD; the old
        ``air × (1 − MW/65.4)`` overstated buoyancy and so the tension DF.
        Falls back to that buoyancy factor when the ID is unknown.
        """
        air = self.tension_air_klbs
        if air is None:
            return None
        if not self.id_in:
            return air * (1.0 - self.mud_weight_ppg / 65.4)
        area = math.pi / 4.0 * (self.od_in**2 - self.id_in**2)
        p_bottom = 0.05194806 * self.mud_weight_ppg * self._vertical_column_ft()
        return air - p_bottom * area / 1000.0

    @property
    def tension_df(self) -> float | None:
        """Tension design factor using joint strength (worst of joint/body)."""
        if self.joint_klbs is None:
            return None
        load = self.tension_buoyed_klbs if self.buoyed else self.tension_air_klbs
        if not load:
            return None
        return self.joint_klbs / load

    @property
    def neutral_point_ft(self) -> float | None:
        """Depth below which the string is in compression (template AB):
        ``TVD·(1 − MW/65.4)``. A liner's is measured from its top and offset
        by the top MD: ``(TVD − TOL_TVD)·(1 − MW/65.4) + TOL`` (AB57)."""
        if self.set_depth_md_ft is None:
            return None
        return self._vertical_column_ft() * (1.0 - self.mud_weight_ppg / 65.4) + (
            self.top_depth_ft or 0.0
        )

    def tension_df_threshold(self) -> float:
        """Minimum acceptable tension DF for this connection type."""
        if not self.collar:
            return DEFAULT_MIN_DF["tension_btc"]
        c = self.collar.upper()
        if c == "STC":
            return DEFAULT_MIN_DF["tension_stc"]
        if c == "LTC":
            return DEFAULT_MIN_DF["tension_ltc"]
        if c == "BTC":
            return DEFAULT_MIN_DF["tension_btc"]
        return DEFAULT_MIN_DF["tension_premium"]

    def design_passes(self, df_overrides: dict | None = None) -> dict[str, bool]:
        """Return ``{"collapse": bool, "burst": bool, "tension": bool}``."""
        df = dict(DEFAULT_MIN_DF)
        if df_overrides:
            df.update(df_overrides)
        return {
            "collapse": (self.collapse_df or 0) >= df["collapse"],
            "burst": (self.burst_df or 0) >= df["burst"],
            "tension": (self.tension_df or 0) >= self.tension_df_threshold(),
        }


@dataclass
class CasingDesign:
    """One well's complete casing design."""

    company: str | None = None
    well_name: str | None = None
    api: str | None = None
    frac_gradient_psi_per_ft: float = 1.0
    strings: list[CasingStringDesign] = field(default_factory=list)

    def finalize(self) -> None:
        """Cross-link each string's ``next_*`` slots so MASP / burst-load
        formulas can see the deeper string. Must be called after the
        strings list is fully populated."""
        for i, s in enumerate(self.strings):
            s.frac_gradient_psi_per_ft = self.frac_gradient_psi_per_ft
            nxt = self.strings[i + 1] if i + 1 < len(self.strings) else None
            prev = self.strings[i - 1] if i > 0 else None
            s.prev_set_depth_md_ft = prev.set_depth_md_ft if prev else None
            s.prev_id_in = prev.id_in if prev else None
            if nxt is not None:
                s.next_set_depth_tvd_ft = nxt.set_depth_tvd_ft
                s.next_set_depth_md_ft = nxt.set_depth_md_ft
                s.next_mud_weight_ppg = nxt.mud_weight_ppg
                s.next_string_internal_gradient_psi_per_ft = nxt.internal_gradient_psi_per_ft
