"""Rich domain model for a casing-design review.

Holds the input data and exposes computed properties so a single
``CasingDesign`` instance can drive every output sheet (Casing Review,
DataPrint, Vertical WBD, BOPE summary) without re-parsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


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
    next_mud_weight_ppg: float | None = None
    next_string_internal_gradient_psi_per_ft: float | None = None

    # Strength catalog results (populated by the engine).
    collapse_psi: float | None = None
    burst_psi: float | None = None
    joint_klbs: float | None = None
    body_klbs: float | None = None
    id_in: float | None = None

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
        return (hole_effective**2 - self.od_in**2) / 183.35

    @property
    def cement_height_ft(self) -> float | None:
        """Vertical height covered by the lead+tail cement in the annulus."""
        cap = self.annular_capacity_ft3_per_ft
        if cap <= 0:
            return None
        return self.cement_total_volume_ft3 / cap

    @property
    def top_of_cement_ft(self) -> float | str | None:
        """TOC = string set depth − cement height; "Surface" if above grade."""
        h = self.cement_height_ft
        if h is None:
            return None
        toc = self.set_depth_md_ft - h
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
        next_shoe_cap = None
        if (
            self.next_set_depth_md_ft is not None
            and self.next_mud_weight_ppg is not None
            and self.next_string_internal_gradient_psi_per_ft is not None
        ):
            next_shoe_bhp = (
                0.05194806
                * self.next_mud_weight_ppg
                * self.next_set_depth_md_ft
            )
            depth_delta = self.next_set_depth_md_ft - self.set_depth_tvd_ft
            next_shoe_cap = (
                next_shoe_bhp
                - self.next_string_internal_gradient_psi_per_ft * depth_delta
            )
        if next_shoe_cap is None:
            kick_cap = frac_init
        else:
            kick_cap = min(frac_init, next_shoe_cap)
        return max(hydrostatic, kick_cap)

    @property
    def burst_df(self) -> float | None:
        if not self.burst_psi or not self.burst_load_psi:
            return None
        return self.burst_psi / self.burst_load_psi

    @property
    def tension_air_klbs(self) -> float | None:
        """Tension at top of string in air = weight × length / 1000."""
        if self.set_depth_md_ft is None:
            return None
        return self.weight_ppf * self.set_depth_md_ft / 1000.0

    @property
    def tension_buoyed_klbs(self) -> float | None:
        """Buoyed tension = air × (1 - MW/65.4)."""
        air = self.tension_air_klbs
        if air is None:
            return None
        return air * (1.0 - self.mud_weight_ppg / 65.4)

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
        """Depth below which the string is in compression (rough estimate)."""
        if self.set_depth_md_ft is None:
            return None
        return self.set_depth_md_ft * (1.0 - self.mud_weight_ppg / 65.4)

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
            if nxt is not None:
                s.next_set_depth_md_ft = nxt.set_depth_md_ft
                s.next_mud_weight_ppg = nxt.mud_weight_ppg
                s.next_string_internal_gradient_psi_per_ft = nxt.internal_gradient_psi_per_ft
