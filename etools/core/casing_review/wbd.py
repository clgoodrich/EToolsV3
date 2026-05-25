"""Vertical Wellbore Diagram renderer.

Replaces the Excel ``Vertical WBD`` sheet's static drawing with a
computed Plotly figure. Reads only the ``CasingDesign`` (and an optional
list of formation tops) — no template, no formulas, no manual fiddling.

The figure is symmetric around x=0; each casing string draws as a pair
of vertical bars (left + right wall) at ±OD/2 from the centerline,
with the cement column overlaid in the annulus and the formation tops
annotated on the right margin.
"""

from __future__ import annotations

from dataclasses import dataclass

import plotly.graph_objects as go

from etools.core.casing_review.domain import CasingDesign


# Colours mirror the engineering-PDF convention.
_CASING_COLOR = "#1f77b4"   # blue — casing wall
_CEMENT_COLOR = "#a86d2c"   # ochre — cement fill
_HOLE_COLOR = "#bbbbbb"     # grey — open-hole side
_FORMATION_COLOR = "#666666"


@dataclass
class FormationMark:
    name: str
    tvd_ft: float


def render_wellbore_figure(
    design: CasingDesign,
    formations: list[FormationMark] | None = None,
    *,
    width_px: int = 480,
    height_px: int = 700,
) -> go.Figure:
    """Return a Plotly Figure for the vertical wellbore."""
    fig = go.Figure()
    if not design.strings:
        fig.update_layout(
            title="No casing strings — load an APD",
            width=width_px,
            height=height_px,
        )
        return fig

    deepest_md = max(s.set_depth_md_ft or 0 for s in design.strings)
    widest_hole = max(s.hole_size_in for s in design.strings if s.hole_size_in)

    # Cement first so casing draws on top.
    for s in design.strings:
        if not s.od_in or not s.hole_size_in:
            continue
        toc = (
            s.top_of_cement_ft
            if isinstance(s.top_of_cement_ft, (int, float))
            else 0
        )
        cement_top = float(toc) if toc != "Surface" else 0.0
        cement_bottom = s.set_depth_md_ft
        if cement_top >= cement_bottom:
            continue
        # Annular cement: from OD/2 to hole/2 on both sides.
        half_od = s.od_in / 2.0
        half_hole = s.hole_size_in / 2.0
        for sign in (-1, 1):
            x_inner = sign * half_od
            x_outer = sign * half_hole
            fig.add_shape(
                type="rect",
                x0=min(x_inner, x_outer),
                x1=max(x_inner, x_outer),
                y0=cement_top,
                y1=cement_bottom,
                fillcolor=_CEMENT_COLOR,
                line=dict(width=0),
                layer="below",
            )

    # Open hole (below cement, inside the hole boundary). Skip for now —
    # showing it cleanly requires per-string-interval logic, and the
    # current figure already conveys the essentials.

    # Casing walls
    for s in design.strings:
        if not s.od_in:
            continue
        half_od = s.od_in / 2.0
        wall_thickness = max(0.05, (s.od_in - (s.id_in or s.od_in * 0.85)) / 2.0)
        for sign in (-1, 1):
            x0 = sign * (half_od - wall_thickness)
            x1 = sign * half_od
            fig.add_shape(
                type="rect",
                x0=min(x0, x1),
                x1=max(x0, x1),
                y0=0,
                y1=s.set_depth_md_ft,
                fillcolor=_CASING_COLOR,
                line=dict(color=_CASING_COLOR, width=0.5),
            )
        # Label the string at its shoe.
        fig.add_annotation(
            x=half_od + 1.5,
            y=s.set_depth_md_ft,
            text=(
                f"{s.label}<br>"
                f"{s.od_in}\" {s.weight_ppf}# {s.grade}/{s.collar or '—'}<br>"
                f"@ {int(s.set_depth_md_ft)} ft MD"
            ),
            showarrow=True,
            arrowhead=2,
            ax=40,
            ay=0,
            align="left",
            font=dict(size=10),
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor=_CASING_COLOR,
        )

    # Formation tops as horizontal dashed lines + right-side labels.
    if formations:
        x_right = widest_hole / 2.0 + 5
        for f in formations:
            if f.tvd_ft is None:
                continue
            fig.add_shape(
                type="line",
                x0=-widest_hole / 2.0 - 1,
                x1=widest_hole / 2.0 + 1,
                y0=f.tvd_ft,
                y1=f.tvd_ft,
                line=dict(color=_FORMATION_COLOR, dash="dash", width=1),
            )
            fig.add_annotation(
                x=x_right,
                y=f.tvd_ft,
                text=f"{f.name} @ {int(f.tvd_ft)}'",
                showarrow=False,
                xanchor="left",
                font=dict(size=9, color=_FORMATION_COLOR),
            )

    fig.update_layout(
        title=f"Vertical Wellbore Diagram — {design.well_name or 'Unnamed'}",
        width=width_px,
        height=height_px,
        margin=dict(l=10, r=140, t=50, b=30),
        xaxis=dict(
            title="Diameter (in)",
            range=[-widest_hole / 2 - 2, widest_hole / 2 + 18],
            zeroline=True,
            zerolinecolor="#999",
        ),
        yaxis=dict(
            title="Depth (ft MD)",
            range=[deepest_md * 1.05, 0],  # inverted: 0 at top
            autorange=False,
        ),
        plot_bgcolor="white",
        showlegend=False,
    )
    return fig
