"""Hovering the well path reports that station's MD/inc/azi and footages.

The readout snaps to a real survey station (never interpolated) and its
FNL/FSL/FEL/FWL come from the section that geometrically contains the
point, which is what ``calculate_clearances`` already assigns per station.
"""
from __future__ import annotations

import html
import inspect
import json
from types import SimpleNamespace

import pandas as pd

from etools.models import SurveyFrame
from etools.ui.tabs import casing_review_tab
from etools.ui.tabs.casing_review_tab import (
    _attr,
    _conc_label,
    _stations_payload,
    _wellpath_stations,
    _wellpath_xy_for_section,
)


def _survey_frame(n: int = 5) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "measured_depth": [1000.0 * i for i in range(n)],
            "inclination": [0.0, 12.5, 45.0, 88.4, 90.0][:n],
            "azimuth": [0.0, 170.1, 171.0, 171.2, 171.5][:n],
            "tvd": [1000.0 * i * 0.9 for i in range(n)],
            "easting": [558000.0 + 50 * i for i in range(n)],
            "northing": [4451000.0 + 40 * i for i in range(n)],
        }
    )


def _state_with_processed(df: pd.DataFrame) -> SimpleNamespace:
    proc = SimpleNamespace(points=df)
    result = SimpleNamespace(frames={SurveyFrame.TRUE: proc})
    return SimpleNamespace(processed={"AsDrilled": result}, clearances=None)


def _state_with_clearances(df: pd.DataFrame) -> SimpleNamespace:
    st = _state_with_processed(df)
    cl = df.copy()
    cl["Conc"] = ["2303S02WU"] * len(cl)
    cl["FNL"] = [1240.0 + i for i in range(len(cl))]
    cl["FSL"] = [4040.0 - i for i in range(len(cl))]
    cl["FEL"] = [2310.0 + i for i in range(len(cl))]
    cl["FWL"] = [2970.0 - i for i in range(len(cl))]
    st.clearances = {"AsDrilled": SimpleNamespace(points=cl)}
    return st


# ---- station extraction -------------------------------------------------

def test_stations_carry_md_inclination_and_azimuth():
    st = _state_with_processed(_survey_frame())
    stations = _wellpath_stations(st)
    assert len(stations) == 5
    first = stations[0]
    assert first.md == 0.0
    assert stations[3].md == 3000.0
    assert stations[3].inc == 88.4
    assert stations[3].azi == 171.2


def test_footages_come_from_the_clearance_frame():
    st = _state_with_clearances(_survey_frame())
    stations = _wellpath_stations(st)
    assert stations[0].fnl == 1240.0
    assert stations[0].fsl == 4040.0
    assert stations[0].fel == 2310.0
    assert stations[0].fwl == 2970.0
    assert stations[0].conc == "2303S02WU"


def test_footages_are_none_when_clearances_were_never_run():
    # An APD parsed but Calculate Clearances never pressed: MD/inc/azi are
    # available, footages are not. Must be absent, not zero.
    st = _state_with_processed(_survey_frame())
    stations = _wellpath_stations(st)
    assert all(s.fnl is None and s.conc is None for s in stations)
    assert all(s.md is not None for s in stations)


def test_the_drawn_path_is_unchanged_by_the_hover_work():
    # _wellpath_xy_for_section feeds the visible polyline and the view box.
    # Its output must stay identical or the graphic shifts.
    st = _state_with_clearances(_survey_frame())
    xy = _wellpath_xy_for_section(None, st)
    assert xy == [(558000.0 + 50 * i, 4451000.0 + 40 * i) for i in range(5)]


def test_no_survey_yields_no_stations():
    assert _wellpath_stations(None) == []
    assert _wellpath_stations(SimpleNamespace(processed=None, clearances=None)) == []


# ---- payload ------------------------------------------------------------

def test_payload_is_valid_json_and_round_trips():
    st = _state_with_clearances(_survey_frame())
    payload = _stations_payload(_wellpath_stations(st))
    data = json.loads(payload)
    assert len(data) == 5
    assert data[3]["md"] == 3000.0
    assert data[3]["inc"] == 88.4
    assert data[3]["fnl"] == 1243.0


def test_payload_is_html_attribute_safe_once_escaped():
    # The payload is JSON (so it round-trips); _attr does the escaping that
    # lets it sit inside a double-quoted data-* attribute.
    st = _state_with_clearances(_survey_frame())
    escaped = _attr(_stations_payload(_wellpath_stations(st)))
    assert '"' not in escaped, "a bare quote would terminate the attribute"
    assert "<" not in escaped and ">" not in escaped


def test_escaping_round_trips_back_to_the_same_json():
    st = _state_with_clearances(_survey_frame())
    payload = _stations_payload(_wellpath_stations(st))
    assert html.unescape(_attr(payload)) == payload


def test_payload_omits_missing_footages_rather_than_zeroing_them():
    st = _state_with_processed(_survey_frame())
    data = json.loads(_stations_payload(_wellpath_stations(st)))
    assert "fnl" not in data[0]
    assert data[0]["md"] == 0.0


def test_empty_stations_yield_an_empty_payload():
    assert json.loads(_stations_payload([])) == []


# ---- section label ------------------------------------------------------

def test_conc_decodes_to_a_readable_section_label():
    assert _conc_label("2303S02WU") == "Sec 23  T3S R2W  (Uintah)"


def test_a_salt_lake_baseline_is_named():
    assert _conc_label("0102N03ES").endswith("(Salt Lake)")


def test_an_unreadable_conc_falls_back_to_the_raw_code():
    # Better to show the code than to drop the section entirely.
    assert _conc_label("junk") == "junk"
    assert _conc_label(None) is None


def test_the_payload_carries_the_readable_label_not_the_raw_conc():
    st = _state_with_clearances(_survey_frame())
    data = json.loads(_stations_payload(_wellpath_stations(st)))
    assert data[0]["sec"] == "Sec 23  T3S R2W  (Uintah)"


# ---- projection ---------------------------------------------------------

def test_projection_maps_stations_into_plot_coordinates():
    # The browser measures cursor-to-station distance in SVG user units, so
    # the payload must carry plot coordinates, not UTM.
    st = _state_with_processed(_survey_frame())
    stations = _wellpath_stations(st)
    data = json.loads(_stations_payload(stations, project=lambda x, y: (x - 558000.0, -y)))
    assert data[0]["x"] == 0.0
    assert data[0]["y"] == -4451000.0
    # MD is unaffected by the projection.
    assert data[1]["md"] == 1000.0


# ---- wiring -------------------------------------------------------------

def _plat_svg_source() -> str:
    src = inspect.getsource(casing_review_tab)
    start = src.index("def _render_plat_svg")
    return src[start:src.index("\ndef ", start + 10)]


def test_the_hover_ribbon_is_emitted_over_the_path():
    body = _plat_svg_source()
    assert 'class="well-hover"' in body
    assert "data-stations=" in body
    assert "pointer-events:stroke" in body


def test_the_visible_path_stays_non_interactive():
    # If the drawn polyline accepted pointer events it would sit on top of
    # the hover ribbon and swallow the mousemove.
    body = _plat_svg_source()
    assert "pointer-events:none" in body


def test_the_payload_is_escaped_before_it_reaches_the_attribute():
    assert "_attr(_stations_payload(" in _plat_svg_source()


def test_the_ribbon_and_the_drawn_path_share_one_station_list():
    # Both come from `stations`, so the hover target can never drift from
    # the line the user sees.
    body = _plat_svg_source()
    assert "stations = _wellpath_stations(state)" in body
    assert "well_xy = [(s.x, s.y) for s in stations]" in body


def test_the_javascript_wires_the_ribbon_and_the_markers():
    src = inspect.getsource(casing_review_tab)
    assert "polyline.well-hover" in src
    assert "circle.well-marker" in src
    assert "etoolsStationHtml" in src


def test_missing_footages_are_called_out_rather_than_shown_as_zero():
    src = inspect.getsource(casing_review_tab)
    assert "Calculate Clearances" in src


def test_azimuth_is_labelled_with_its_frame():
    # _survey_points always reads SurveyFrame.TRUE, but the Survey tab can be
    # toggled to Grid. An unlabelled "Azi" invites comparing the two.
    src = inspect.getsource(casing_review_tab)
    assert "Azi (true)" in src
