"""Edge cases at the ends of a survey, across north, and on section lines."""
from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from etools.core.casing_review.engine import (
    CasingDesignEngine,
    welltrack_from_processed_survey,
)
from etools.core.plat import locate_points
from etools.core.survey.processor import (
    interpolate_at_md,
    process_survey,
    project_to_md,
)
from etools.models import APDCasingString, APDPdfData, SurveyFrame


def _points():
    return pd.DataFrame(
        {
            "measured_depth": [0.0, 500.0, 1000.0],
            "tvd": [0.0, 500.0, 990.0],
            "azimuth": [0.0, 359.0, 1.0],
        }
    )


def test_md_past_last_station_raises():
    with pytest.raises(ValueError, match="past the last survey station"):
        interpolate_at_md(_points(), 1200.0)


def test_md_at_last_station_within_rounding_is_allowed():
    assert interpolate_at_md(_points(), 1000.3)["tvd"] == 990.0


def test_azimuth_interpolates_the_short_way_across_north():
    assert interpolate_at_md(_points(), 750.0)["azimuth"] == pytest.approx(0.0)


def test_project_to_md_extends_on_last_inc_azi():
    raw = pd.DataFrame(
        {"MeasuredDepth": [0.0, 1000.0, 2000.0], "Inclination": [0.0, 45.0, 90.0],
         "Azimuth": [0.0, 90.0, 90.0]}
    )
    raw.attrs["north_reference"] = "true"
    out = project_to_md(raw, 2100.0)
    assert out.iloc[-1].tolist() == [2100.0, 90.0, 90.0]
    assert out.attrs["north_reference"] == "true"
    assert project_to_md(raw, 2000.2) is raw


def test_point_on_a_section_line_gets_a_section():
    secs = gpd.GeoDataFrame(
        {"Conc": ["0101S01WU", "0201S01WU"], "label": ["a", "b"]},
        geometry=[box(0, 0, 100, 100), box(100, 0, 200, 100)],
        crs="EPSG:32612",
    )
    pts = pd.DataFrame({"easting": [100.0, 50.0, 0.0], "northing": [50.0, 50.0, 0.0]})
    out = locate_points(pts, secs)
    assert out["Conc"].notna().all()
    assert len(out) == 3


def _apd(collar: str) -> APDPdfData:
    return APDPdfData(
        casing=[
            APDCasingString(
                tag="Prod", hole_size_in=8.75, casing_size_in=5.5,
                length_top_ft=0.0, length_bottom_ft=10000.0,
                weight_ppf=20.0, grade="P-110", collar=collar,
            )
        ]
    )


def test_uncatalogued_connection_leaves_joint_strength_unresolved():
    s = CasingDesignEngine().build(_apd("TXP")).strings[0]
    # Pipe-body ratings still come from the catalog ...
    assert s.burst_psi and s.collapse_psi
    # ... but not another connection's joint strength (LTC 548 / BTC 667).
    assert s.joint_klbs is None


def test_catalogued_connection_keeps_its_joint_strength():
    s = CasingDesignEngine().build(_apd("BTC")).strings[0]
    assert s.joint_klbs == 667.0


def test_welltrack_from_processed_survey_reads_rows():
    raw = pd.DataFrame(
        {"MeasuredDepth": [0.0, 1000.0, 2000.0], "Inclination": [0.0, 0.0, 30.0],
         "Azimuth": [0.0, 0.0, 90.0]}
    )
    frames = process_survey(
        raw, surface_lat=40.0, surface_lon=-110.0, surface_elevation_ft=5000.0,
        north_reference="true", citing_type="Planned", api="4300000000", lateral="0000",
    )

    class _Result:
        pass

    r = _Result()
    r.frames = frames
    track = welltrack_from_processed_survey(r)
    assert [p.md_ft for p in track] == [0.0, 1000.0, 2000.0]
    assert track[1].tvd_ft == pytest.approx(1000.0)
    assert frames[SurveyFrame.TRUE] is not None
