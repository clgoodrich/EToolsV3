"""The spatial join assumes a CRS rather than checking one; say so, and
make the all-miss case loud."""
from __future__ import annotations

import inspect

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from etools.core.plat import locator


def test_crs_assumption_is_documented_at_the_assignment():
    src = inspect.getsource(locator.locate_points)
    assert "crs=sections.crs" in src
    lowered = src.lower()
    # The comment wraps across lines, so match on single words rather than a
    # phrase that line-wrapping can split.
    assert "reproject" in lowered, (
        "the forced CRS assignment must say it does not reproject"
    )


def test_locator_logs_the_match_rate():
    src = inspect.getsource(locator.locate_points)
    assert "matched" in src


def _sections():
    poly = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    return gpd.GeoDataFrame(
        {"Conc": ["2303S02WU"], "label": ["Sec 23"], "geometry": [poly]},
        crs="EPSG:26912",
    )


class _RecordingLog:
    """structlog does not route through stdlib logging here, so caplog sees
    nothing. Record the calls directly instead."""

    def __init__(self):
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def warning(self, event, **kw):
        self.warnings.append(event)

    def info(self, event, **kw):
        self.infos.append(event)

    def debug(self, event, **kw):
        pass


def test_every_point_missing_is_warned_not_just_info(monkeypatch):
    # A gross CRS mismatch (degrees where metres are expected) puts every
    # point outside every section. That is indistinguishable in the output
    # from "this well is off-plat", so it must be loud in the log.
    rec = _RecordingLog()
    monkeypatch.setattr(locator, "log", rec)
    pts = pd.DataFrame({"easting": [-110.35, -110.36], "northing": [40.27, 40.28]})
    out = locator.locate_points(
        pts, _sections(), easting_col="easting", northing_col="northing"
    )
    assert out["Conc"].isna().all()
    assert "plat.locate.no_matches" in rec.warnings, (
        f"all-miss join was not warned; warnings={rec.warnings}"
    )


def test_a_normal_join_still_matches_and_does_not_warn(monkeypatch):
    rec = _RecordingLog()
    monkeypatch.setattr(locator, "log", rec)
    pts = pd.DataFrame({"easting": [500.0, 600.0], "northing": [500.0, 600.0]})
    out = locator.locate_points(
        pts, _sections(), easting_col="easting", northing_col="northing"
    )
    assert (out["Conc"] == "2303S02WU").all()
    assert "plat.locate.no_matches" not in rec.warnings
