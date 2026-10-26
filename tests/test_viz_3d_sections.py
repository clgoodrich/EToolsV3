"""3-D trajectory: PLSS section outlines are drawn at the surface in the same
grid-north offset frame as the wellbore, so a polygon corner placed on a
station's lat/lon plots exactly at that station's (e_offset, n_offset)."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from etools.core.survey.processor import latlon_to_offsets, process_survey
from etools.models import SurveyFrame
from etools.ui.tabs.viz_tab import _add_surface_sections

LAT0, LON0 = 40.10, -109.80


@pytest.fixture(scope="module")
def processed():
    raw = pd.DataFrame({
        "MeasuredDepth": [0, 6000, 7000, 12000, 17000],
        "Inclination": [0, 0, 90, 90, 90],
        "Azimuth": [135, 135, 135, 135, 135],
    })
    out = process_survey(raw, surface_lat=LAT0, surface_lon=LON0, surface_elevation_ft=5000,
                         north_reference="True", citing_type="Planned", api="1", lateral="0")
    return out[SurveyFrame.TRUE]


def test_latlon_to_offsets_inverts_station_placement(processed) -> None:
    pts = processed.points
    n, e = latlon_to_offsets(pts["lat"], pts["lon"], LAT0, LON0, processed.convergence_angle)
    assert np.allclose(n, pts["n_offset"], atol=0.05)
    assert np.allclose(e, pts["e_offset"], atol=0.05)


def test_section_outline_sits_at_surface_on_the_well_frame(processed) -> None:
    import plotly.graph_objects as go

    pts = processed.points
    corners = [(pts["lon"].iloc[i], pts["lat"].iloc[i]) for i in (0, 2, 4)]
    sections = gpd.GeoDataFrame(
        [{"Conc": "X", "label": "36-3S-2W", "geometry": Polygon(corners)}],
        geometry="geometry", crs="EPSG:4326",
    )
    fig = go.Figure()
    _add_surface_sections(fig, sections, (LAT0, LON0), processed.convergence_angle)
    outline = next(t for t in fig.data if t.mode == "lines")
    assert set(np.asarray(outline.z)) == {0.0}
    for k, i in enumerate((0, 2, 4)):
        assert outline.x[k] == pytest.approx(pts["e_offset"].iloc[i], abs=0.05)
        assert outline.y[k] == pytest.approx(pts["n_offset"].iloc[i], abs=0.05)
    label = next(t for t in fig.data if t.mode == "text")
    assert list(label.text) == ["36-3S-2W"]


def test_no_sections_or_origin_adds_nothing() -> None:
    import plotly.graph_objects as go

    fig = go.Figure()
    _add_surface_sections(fig, None, (LAT0, LON0), 1.0)
    _add_surface_sections(fig, gpd.GeoDataFrame(geometry=[]), (LAT0, LON0), 1.0)
    _add_surface_sections(fig, None, (None, None), 1.0)
    assert len(fig.data) == 0


def test_only_crossed_sections_are_drawn() -> None:
    from types import SimpleNamespace

    from etools.ui.tabs.viz_tab import _sections_crossed

    sq = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    secs = gpd.GeoDataFrame(
        [{"Conc": c, "label": c, "geometry": sq} for c in ("A", "B", "C")],
        geometry="geometry", crs="EPSG:4326",
    )
    cr = SimpleNamespace(points=pd.DataFrame({"Conc": ["A", "A", "C", None]}))
    assert list(_sections_crossed(secs, cr)["Conc"]) == ["A", "C"]
    # Nothing matched (or no clearance points) -> fall back to all sections.
    assert len(_sections_crossed(secs, SimpleNamespace(points=pd.DataFrame({"Conc": ["Z"]})))) == 3
    assert len(_sections_crossed(secs, None)) == 3
