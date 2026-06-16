"""Map & Viz tab — 2D Leaflet map + 3D Plotly trajectory + section summary.

2D map interactivity: every drawn layer is non-interactive so all clicks
land on the map itself; a single click handler then hit-tests in order —
station reticule → well path → section polygon — and opens a Leaflet popup
(station name / MD-INC-AZI-TVD + in-section footages / plat label).
"""

from __future__ import annotations

import math
from typing import Callable

import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from nicegui import ui
from shapely.geometry import Point as ShpPoint

from etools.core.coordinates import dms_to_decimal, latlon_to_utm, utm_to_latlon
from etools.models import SurveyFrame
from etools.ui.state import AppState

_SECTION_COLORS = ["#4f46e5", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#84cc16"]
_BUFFER_COLORS = {100: "#dc2626", 330: "#f59e0b", 500: "#6b7280"}


def render_viz_tab(state: AppState) -> Callable[[], None]:
    with ui.column().classes("p-4 gap-3 w-full"):
        header_label = ui.label("Calculate clearances first.").classes("text-gray-500 italic")

        controls = ui.row().classes("gap-3 items-center")
        with controls:
            ui.label("Citing:").classes("text-sm")
            citing_select = (
                ui.select(options=[], on_change=lambda _: rerender())
                .props("dense outlined")
                .classes("w-40")
            )
            ui.label("Frame:").classes("text-sm")
            frame_state: dict[str, SurveyFrame] = {"value": SurveyFrame.TRUE}
            ui.toggle(
                {SurveyFrame.TRUE.value: "True", SurveyFrame.GRID.value: "Grid"},
                value=SurveyFrame.TRUE.value,
                on_change=lambda e: (
                    frame_state.__setitem__("value", SurveyFrame(e.value)),
                    rerender(),
                ),
            ).props("dense")
            ui.label("Setbacks:").classes("text-sm ml-4")
            buffer_state: dict[int, bool] = {100: False, 330: False, 500: False}

            def _toggle_buffer(dist: int, value: bool) -> None:
                buffer_state[dist] = value
                rerender()

            for _dist in (100, 330, 500):
                ui.checkbox(
                    f"{_dist} ft",
                    value=False,
                    on_change=lambda e, d=_dist: _toggle_buffer(d, e.value),
                ).props("dense").tooltip(f"Dashed ring {_dist} ft inside each section boundary")
            status = ui.label("").classes("text-sm text-gray-500 ml-2")
        controls.set_visibility(False)

        with ui.tabs().classes("w-full") as sub_tabs:
            tab_map = ui.tab("2D Map", icon="map")
            tab_3d = ui.tab("3D Trajectory", icon="view_in_ar")

        with ui.tab_panels(sub_tabs, value=tab_map).classes("w-full"):
            with ui.tab_panel(tab_map):
                map_widget = ui.leaflet(center=(40.27, -110.35), zoom=12).classes("w-full").style("height: 600px")
                with ui.row().classes("gap-2 items-center mt-2 flex-wrap"):
                    ui.toggle(
                        {"streets": "Streets", "satellite": "Satellite"},
                        value="streets",
                        on_change=lambda e: set_basemap(e.value),
                    ).props("dense no-caps").tooltip("Switch between the street map and aerial imagery")
                    point_lat_input = ui.input(
                        "Lat / Easting", placeholder="40.2701 or 555200"
                    ).props("dense outlined").classes("w-44 font-mono")
                    point_lon_input = ui.input(
                        "Lon / Northing", placeholder="-110.3502 or 4458447"
                    ).props("dense outlined").classes("w-44 font-mono")
                    point_name_input = ui.input("Label", placeholder="Pad corner").props(
                        "dense outlined"
                    ).classes("w-40")
                    ui.button("Add point", icon="add_location", on_click=lambda: add_custom_point())
                    ui.button(
                        "Clear points", icon="layers_clear", on_click=lambda: clear_custom_points()
                    ).props("flat")
                points_box = ui.column().classes("gap-0 w-full max-w-2xl")
            with ui.tab_panel(tab_3d):
                plot_widget = ui.plotly({}).classes("w-full").style("height: 600px")

    map_layers: list = []  # tracks Leaflet layer IDs so we can clear them between renders
    custom_points: list[dict] = []  # user-added markers; survive rerenders
    # Snapshot of the last render, used by the map-click hit-tester.
    render_cache: dict = {
        "sections_wgs84": None,
        "cr_points": None,
        "frame_points": None,
        "stations": [],
    }

    def _station_html(imin: int, title: str | None = None) -> str:
        """Full readout for station ``imin`` of the clearance points:
        MD / Inc / Azi / TVD + section + in-section footages."""
        crp = render_cache["cr_points"]
        row = crp.iloc[imin]
        # Honor the frame toggle for the azimuth readout.
        fp = render_cache.get("frame_points")
        azi = row.get("azimuth")
        if fp is not None and len(fp) == len(crp):
            azi = fp.iloc[imin].get("azimuth", azi)
        parts = []
        if title:
            parts.append(f"<b>{title}</b>")
        parts.append(f"<b>MD {row['measured_depth']:,.0f} ft</b>")
        inc = row.get("inclination")
        line = []
        if pd.notna(inc):
            line.append(f"Inc {float(inc):.2f}°")
        if pd.notna(azi):
            line.append(f"Azi {float(azi):.2f}°")
        if line:
            parts.append(" · ".join(line))
        tvd = row.get("tvd")
        if pd.notna(tvd):
            parts.append(f"TVD {float(tvd):,.0f} ft")
        label = row.get("label")
        if label:
            parts.append(f"Sec {label}")
        foots = []
        for k in ("FNL", "FSL", "FEL", "FWL"):
            v = row.get(k)
            if pd.notna(v):
                foots.append(f"{k} {float(v):,.0f}")
        if foots:
            parts.append(" · ".join(foots[:2]))
            if len(foots) > 2:
                parts.append(" · ".join(foots[2:]))
        return "<br>".join(parts)

    def on_map_click(e) -> None:
        latlng = (e.args or {}).get("latlng") or {}
        lat, lon = latlng.get("lat"), latlng.get("lng")
        if lat is None or lon is None:
            return
        # Pixel-based tolerance: ~12 px at the current zoom level.
        try:
            zoom = float(map_widget.zoom or 13)
        except Exception:
            zoom = 13.0
        m_per_px = 40075016.686 * abs(math.cos(math.radians(lat))) / (256 * 2 ** zoom)
        tol_m = max(12 * m_per_px, 15.0)
        m_lat = 111_320.0
        m_lon = 111_320.0 * math.cos(math.radians(lat))

        def _popup(html: str) -> None:
            map_widget.run_map_method("openPopup", html, [lat, lon])

        crp = render_cache.get("cr_points")
        have_crp = crp is not None and not crp.empty and {"lat", "lon"} <= set(crp.columns)

        # 1) Station / custom-point reticules first (tightest target).
        stations = render_cache.get("stations") or []
        if stations:
            best = min(
                stations,
                key=lambda s: math.hypot((s["lat"] - lat) * m_lat, (s["lon"] - lon) * m_lon),
            )
            d = math.hypot((best["lat"] - lat) * m_lat, (best["lon"] - lon) * m_lon)
            if d <= tol_m * 1.4:
                if best["md"] is not None and have_crp:
                    imin = int(
                        (crp["measured_depth"] - best["md"]).abs().to_numpy().argmin()
                    )
                    _popup(_station_html(imin, title=best["label"]))
                else:
                    _popup(f"<b>{best['label']}</b><br>{lat:.5f}, {lon:.5f}")
                return

        # 2) The well path → full station readout incl. in-section footages.
        if have_crp:
            d = np.hypot(
                (crp["lat"].to_numpy(dtype=float) - lat) * m_lat,
                (crp["lon"].to_numpy(dtype=float) - lon) * m_lon,
            )
            imin = int(np.nanargmin(d))
            if float(d[imin]) <= tol_m:
                _popup(_station_html(imin))
                return

        # 3) Inside a section polygon → plat identity.
        sections = render_cache.get("sections_wgs84")
        if sections is not None and not sections.empty:
            pt = ShpPoint(lon, lat)
            for _, sec in sections.iterrows():
                try:
                    if sec.geometry.contains(pt):
                        _popup(f"<b>Section {sec.get('label') or sec.get('Conc')}</b>")
                        return
                except Exception:
                    continue

    map_widget.on("map-click", on_map_click)

    def add_custom_point() -> None:
        try:
            a = dms_to_decimal(point_lat_input.value or "")
            b = dms_to_decimal(point_lon_input.value or "")
        except ValueError as exc:
            ui.notify(f"Coordinate parse failed: {exc}", type="warning")
            return
        # Lat/lon detected by magnitude; bigger numbers are UTM 12N metres.
        if abs(a) <= 90 and abs(b) <= 180:
            lat, lon = a, b
            e, n, _zone, _letter = latlon_to_utm(lat, lon)
        else:
            e, n = a, b
            lat, lon = utm_to_latlon(e, n, 12, "N")
        label = (point_name_input.value or "").strip() or f"Point {len(custom_points) + 1}"
        custom_points.append({"label": label, "easting": e, "northing": n, "lat": lat, "lon": lon})
        point_lat_input.value = ""
        point_lon_input.value = ""
        point_name_input.value = ""
        _render_points_box()
        rerender()

    def clear_custom_points() -> None:
        custom_points.clear()
        _render_points_box()
        rerender()

    def _render_points_box() -> None:
        points_box.clear()
        with points_box:
            for i, p in enumerate(custom_points):
                with ui.row().classes("items-center gap-3 border-b py-0.5 w-full text-sm"):
                    ui.label(p["label"]).classes("w-32 font-medium")
                    ui.label(f"E {p['easting']:,.1f}  N {p['northing']:,.1f}").classes("font-mono")
                    ui.label(f"{p['lat']:.5f}, {p['lon']:.5f}").classes("font-mono text-gray-500")

                    def _remove(idx: int = i) -> None:
                        custom_points.pop(idx)
                        _render_points_box()
                        rerender()

                    ui.button(icon="close", on_click=_remove).props("flat dense size=sm")

    # Aerial-imagery basemap, toggled on top of the default OSM streets layer.
    # Esri World Imagery uses {z}/{y}/{x} tile order. The layer lives in
    # Leaflet's tilePane (beneath every vector overlay), so the well path,
    # section polygons and reticules stay visible over it; it also survives
    # clear_map() since only tracked overlay layers are removed there.
    basemap_state: dict = {"satellite": None}

    def set_basemap(kind: str) -> None:
        if kind == "satellite" and basemap_state["satellite"] is None:
            basemap_state["satellite"] = map_widget.tile_layer(
                url_template=(
                    "https://server.arcgisonline.com/ArcGIS/rest/services/"
                    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
                ),
                options={
                    "maxZoom": 19,
                    "attribution": (
                        "Imagery &copy; Esri, Maxar, Earthstar Geographics, "
                        "and the GIS User Community"
                    ),
                },
            )
        elif kind != "satellite" and basemap_state["satellite"] is not None:
            try:
                map_widget.remove_layer(basemap_state["satellite"])
            except Exception:
                pass
            basemap_state["satellite"] = None

    def clear_map() -> None:
        for layer_id in map_layers:
            try:
                map_widget.remove_layer(layer_id)
            except Exception:
                pass
        map_layers.clear()

    def rerender() -> None:
        if not state.clearances:
            controls.set_visibility(False)
            header_label.visible = True
            return
        header_label.visible = False
        controls.set_visibility(True)

        citing = citing_select.value
        cr = state.clearances.get(citing)
        sr = state.processed.get(citing)
        if cr is None or sr is None:
            return

        ps = sr.frames[frame_state["value"]]
        points = ps.points

        # ----- 2D Leaflet -----
        clear_map()
        # Prefer state.section_definitions when populated — that's the
        # authoritative model the Casing Review SHL/BHL section tabs edit.
        # Falls back to the raw clearance polygons when no SectionDefinitions
        # are seeded (e.g. a section that isn't in the Grid Numbers DB).
        sections_source = _sections_from_state(state, cr)
        sections_wgs84 = _project_to_wgs84(sections_source)
        for i, (_, sec) in enumerate(sections_wgs84.iterrows()):
            color = _SECTION_COLORS[i % len(_SECTION_COLORS)]
            geom = sec.geometry
            rings = _polygon_rings(geom)
            for ring in rings:
                map_layers.append(
                    map_widget.generic_layer(
                        name="polygon",
                        args=[
                            ring,
                            {
                                "color": color,
                                "weight": 2,
                                "fillOpacity": 0.05,
                                "fillColor": color,
                                # Clicks must pass through to the map so the
                                # single map-click handler can hit-test.
                                "interactive": False,
                            },
                        ],
                    )
                )

        # Setback buffer rings — drawn N ft inside each section boundary.
        # Buffer in the projected CRS (metres), then reproject for Leaflet.
        active_buffers = [d for d, on in buffer_state.items() if on]
        if active_buffers and not sections_source.empty:
            for dist_ft in active_buffers:
                inset = sections_source.copy()
                inset["geometry"] = inset.geometry.buffer(-dist_ft * 0.3048)
                inset = inset[~inset.geometry.is_empty]
                if inset.empty:
                    continue
                for ring in _polygon_rings_of_frame(_project_to_wgs84(inset)):
                    map_layers.append(
                        map_widget.generic_layer(
                            name="polyline",
                            args=[
                                ring,
                                {
                                    "color": _BUFFER_COLORS.get(dist_ft, "#6b7280"),
                                    "weight": 1.5,
                                    "dashArray": "6 6",
                                    "interactive": False,
                                },
                            ],
                        )
                    )

        # Trajectory polyline (lat/lon already in points)
        latlngs = list(zip(points["lat"].tolist(), points["lon"].tolist()))
        if latlngs:
            map_layers.append(
                map_widget.generic_layer(
                    name="polyline",
                    args=[latlngs, {"color": "#dc2626", "weight": 3, "interactive": False}],
                )
            )

        # Station + custom-point reticules (circle markers, not pins).
        stations: list[dict] = []
        for label, md in _significant_mds(sr).items():
            row = points.iloc[(points["measured_depth"] - md).abs().idxmin()]
            stations.append(
                {"label": label, "md": md, "lat": float(row["lat"]), "lon": float(row["lon"])}
            )
        for p in custom_points:
            stations.append({"label": p["label"], "md": None, "lat": p["lat"], "lon": p["lon"]})
        for s in stations:
            is_custom = s["md"] is None
            map_layers.append(
                map_widget.generic_layer(
                    name="circleMarker",
                    args=[
                        [s["lat"], s["lon"]],
                        {
                            "radius": 7,
                            "color": "#b45309" if is_custom else "#1d4ed8",
                            "weight": 2.5,
                            "fillColor": "#ffffff",
                            "fillOpacity": 0.85,
                            "interactive": False,
                        },
                    ],
                )
            )

        # Cache what the click handler needs to hit-test this render.
        render_cache["sections_wgs84"] = sections_wgs84
        render_cache["cr_points"] = cr.points
        render_cache["frame_points"] = points
        render_cache["stations"] = stations

        # Center on SHL — but only when the displayed well actually changed.
        # Re-renders triggered by setback toggles, custom points, or the
        # frame switch must leave the user's pan/zoom alone.
        shl = points.iloc[0]
        center_key = (citing, round(float(shl["lat"]), 6), round(float(shl["lon"]), 6))
        if render_cache.get("centered_key") != center_key:
            render_cache["centered_key"] = center_key
            map_widget.set_center((float(shl["lat"]), float(shl["lon"])))
            map_widget.set_zoom(13)

        # ----- 3D Plotly -----
        plot_widget.update_figure(_make_3d_figure(points, sr, cr))
        status.text = (
            f"{len(points)} pts · {points['Conc'].nunique() if 'Conc' in points else cr.points['Conc'].nunique()} sections"
        )

    def refresh() -> None:
        if not state.clearances:
            header_label.text = "Calculate clearances first."
            header_label.visible = True
            controls.set_visibility(False)
            clear_map()
            return
        opts = sorted(state.clearances.keys())
        citing_select.options = opts
        if not citing_select.value or citing_select.value not in opts:
            citing_select.value = opts[0]
        citing_select.update()
        rerender()

    return refresh


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sections_from_state(state: AppState, cr) -> gpd.GeoDataFrame:
    """Return the polygon GeoDataFrame to render on the map.

    If ``state.section_definitions`` is populated, use the resolved polygons
    (which honor any user-entered per-segment / corner overrides from the
    Casing Review SHL/BHL section tabs). Per-Conc fallback to ``cr.sections``
    when a section isn't in the Grid Numbers DB.
    """
    if not state.section_definitions:
        return cr.sections
    raw = cr.sections
    if raw is None or raw.empty:
        return raw
    rows = []
    for _, sec in raw.iterrows():
        conc = sec.get("Conc")
        sd = state.section_definitions.get(conc) if conc else None
        if sd is not None:
            try:
                geom = sd.resolve_polygon()
            except Exception:
                geom = sec.geometry
        else:
            geom = sec.geometry
        rows.append({"Conc": conc, "label": sec.get("label", conc), "geometry": geom})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=raw.crs)


def _project_to_wgs84(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf
    if gdf.crs and str(gdf.crs).upper() != "EPSG:4326":
        return gdf.to_crs("EPSG:4326")
    return gdf


def _polygon_rings(geom) -> list[list[tuple[float, float]]]:
    """Return a list of [(lat, lon), ...] rings for either Polygon or MultiPolygon."""
    rings: list[list[tuple[float, float]]] = []
    # A None/empty geometry (e.g. resolve_polygon fell through with no
    # fallback) must not crash the whole map render — just contribute no rings.
    if geom is None or getattr(geom, "is_empty", False):
        return rings
    if geom.geom_type == "Polygon":
        rings.append([(y, x) for x, y in geom.exterior.coords])
    elif geom.geom_type == "MultiPolygon":
        for poly in geom.geoms:
            rings.append([(y, x) for x, y in poly.exterior.coords])
    return rings


def _polygon_rings_of_frame(gdf: gpd.GeoDataFrame) -> list[list[tuple[float, float]]]:
    rings: list[list[tuple[float, float]]] = []
    for geom in gdf.geometry:
        rings.extend(_polygon_rings(geom))
    return rings


def _significant_mds(sr) -> dict[str, float]:
    out: dict[str, float] = {"SHL": float(sr.frames[SurveyFrame.TRUE].points["measured_depth"].iloc[0])}
    if sr.kop.md is not None:
        out["KOP"] = float(sr.kop.md)
    if sr.landing_md is not None:
        out["Landing"] = float(sr.landing_md)
    out["BHL"] = float(sr.frames[SurveyFrame.TRUE].points["measured_depth"].iloc[-1])
    return out


def _make_3d_figure(points: pd.DataFrame, sr, cr=None) -> go.Figure:
    """3D wellbore in NEV (north / east / depth) space.

    When the clearance result aligns with the trajectory, the hover box also
    reports the PLSS section each station sits in and its FNL/FSL/FEL/FWL.
    """
    fig = go.Figure()
    base_cols = [points["measured_depth"], points["inclination"], points["azimuth"], points["tvd"]]
    hover = (
        "MD: %{customdata[0]:.1f} ft<br>"
        "Inc: %{customdata[1]:.2f}°<br>"
        "Azi: %{customdata[2]:.2f}°<br>"
        "TVD: %{customdata[3]:.1f} ft<br>"
        "N: %{y:.1f} ft  E: %{x:.1f} ft"
    )

    crp = getattr(cr, "points", None)
    foot_cols = ("FNL", "FSL", "FEL", "FWL")
    if (
        crp is not None
        and len(crp) == len(points)
        and "label" in crp.columns
        and all(c in crp.columns for c in foot_cols)
    ):
        def _fmt(series: pd.Series) -> np.ndarray:
            return np.array(
                [f"{float(v):,.0f}" if pd.notna(v) else "—" for v in series], dtype=object
            )

        base_cols.append(crp["label"].fillna("—").astype(str).to_numpy(dtype=object))
        base_cols.extend(_fmt(crp[c]) for c in foot_cols)
        hover += (
            "<br>Sec %{customdata[4]}"
            "<br>FNL %{customdata[5]} · FSL %{customdata[6]}"
            "<br>FEL %{customdata[7]} · FWL %{customdata[8]}"
        )

    fig.add_trace(
        go.Scatter3d(
            x=points["e_offset"],
            y=points["n_offset"],
            z=-points["tvd"],
            mode="lines",
            line=dict(color="#dc2626", width=4),
            name="Wellbore",
            hovertemplate=hover + "<extra></extra>",
            customdata=np.column_stack(base_cols),
        )
    )
    # Significant stations
    for label, md in _significant_mds(sr).items():
        idx = (points["measured_depth"] - md).abs().idxmin()
        row = points.loc[idx]
        fig.add_trace(
            go.Scatter3d(
                x=[row["e_offset"]], y=[row["n_offset"]], z=[-row["tvd"]],
                mode="markers+text",
                marker=dict(size=6, color="#1d4ed8"),
                text=[label],
                textposition="top center",
                name=label,
                showlegend=False,
            )
        )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        scene=dict(
            xaxis_title="East offset (ft)",
            yaxis_title="North offset (ft)",
            zaxis_title="Depth below SHL (ft)",
            aspectmode="data",
        ),
    )
    return fig
