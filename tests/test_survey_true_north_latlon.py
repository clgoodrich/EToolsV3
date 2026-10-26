"""Station lat/lon must follow TRUE azimuth. welleng's n/e offsets are in the
grid frame; un-projecting them unrotated swung every station about the SHL by
the grid convergence (~1.1° in the Uintah Basin, ~200 ft on a 2-mile lateral)."""

from __future__ import annotations

import pandas as pd
import pytest
from pyproj import Geod

from etools.core.survey.processor import process_survey
from etools.models import SurveyFrame


@pytest.mark.parametrize("north_ref,azi", [("True", 180.0), ("True", 90.0), ("Grid", 0.0)])
def test_bhl_bearing_matches_true_azimuth(north_ref: str, azi: float) -> None:
    lat, lon = 40.10, -109.80
    raw = pd.DataFrame({
        "MeasuredDepth": [0, 7000, 8000, 18560],
        "Inclination": [0, 0, 90, 90],
        "Azimuth": [azi] * 4,
    })
    out = process_survey(raw, surface_lat=lat, surface_lon=lon, surface_elevation_ft=5000,
                         north_reference=north_ref, citing_type="Planned", api="1", lateral="0")
    bhl = out[SurveyFrame.TRUE].points.iloc[-1]
    bearing, _, _ = Geod(ellps="WGS84").inv(lon, lat, bhl.lon, bhl.lat)
    assert bearing % 360 == pytest.approx(bhl.azimuth % 360, abs=0.01)
