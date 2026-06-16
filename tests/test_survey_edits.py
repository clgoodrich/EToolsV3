"""Raw-survey edit operations — interpolate/insert/update/delete + azimuth frames."""
from __future__ import annotations

import pandas as pd
import pytest

from etools.core.survey.edits import (
    delete_station,
    displayed_to_native_azimuth,
    insert_station,
    interpolate_raw_station,
    update_station,
)


def _raw() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "MeasuredDepth": [0.0, 100.0, 200.0, 300.0],
            "Inclination": [0.0, 10.0, 30.0, 90.0],
            "Azimuth": [0.0, 350.0, 10.0, 20.0],
        }
    )


def test_interpolate_midpoint_and_wraparound() -> None:
    s = interpolate_raw_station(_raw(), 150.0)
    assert s["MeasuredDepth"] == 150.0
    assert s["Inclination"] == pytest.approx(20.0)
    # 350° → 10° crosses north: midpoint is 0°, not 180°.
    assert s["Azimuth"] == pytest.approx(0.0, abs=1e-9)


def test_interpolate_clamps_out_of_range() -> None:
    assert interpolate_raw_station(_raw(), 9999)["Inclination"] == 90.0
    assert interpolate_raw_station(_raw(), -5)["Inclination"] == 0.0


def test_insert_station_sorted_and_replaces_duplicates() -> None:
    out = insert_station(_raw(), 150.0)
    assert list(out["MeasuredDepth"]) == [0, 100, 150, 200, 300]
    assert out.loc[2, "Inclination"] == pytest.approx(20.0)
    # Inserting at an existing MD replaces the station.
    out2 = insert_station(_raw(), 200.0, inclination=45.0)
    assert len(out2) == 4
    assert out2.loc[2, "Inclination"] == 45.0


def test_update_and_delete_station() -> None:
    out = update_station(_raw(), 200.0, inclination=33.3, azimuth=361.0)
    assert out.loc[2, "Inclination"] == 33.3
    assert out.loc[2, "Azimuth"] == pytest.approx(1.0)
    # MD change re-sorts.
    out = update_station(_raw(), 100.0, md=250.0)
    assert list(out["MeasuredDepth"]) == [0, 200, 250, 300]

    out = delete_station(_raw(), 100.0)
    assert list(out["MeasuredDepth"]) == [0, 200, 300]

    with pytest.raises(ValueError):
        delete_station(_raw(), 123.0)  # nothing within tolerance
    with pytest.raises(ValueError):
        update_station(_raw(), 5.0, inclination=1.0)


def test_update_md_onto_existing_station_collapses() -> None:
    # Moving MD 100 onto the existing MD 200 must replace it — not leave two
    # rows at 200 for process_survey to silently drop_duplicates away.
    out = update_station(_raw(), 100.0, md=200.0)
    assert list(out["MeasuredDepth"]) == [0, 200, 300]
    assert not out["MeasuredDepth"].duplicated().any()
    # The edited (moved) station wins: it carried MD 100's inclination (10.0).
    assert out.loc[out["MeasuredDepth"] == 200.0, "Inclination"].iloc[0] == 10.0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_edit_ops_reject_non_finite_md(bad) -> None:
    # float("nan")/float("inf") slip past a plain float() parse; every MD-taking
    # edit op must reject them instead of poisoning the survey.
    with pytest.raises(ValueError):
        interpolate_raw_station(_raw(), bad)
    with pytest.raises(ValueError):
        insert_station(_raw(), bad)
    with pytest.raises(ValueError):
        delete_station(_raw(), bad)
    with pytest.raises(ValueError):
        update_station(_raw(), bad, inclination=5.0)
    with pytest.raises(ValueError):
        update_station(_raw(), 100.0, md=bad)


def test_displayed_to_native_azimuth() -> None:
    # True-referenced survey, edited in the True frame: identity.
    assert displayed_to_native_azimuth(
        90.0, displayed_frame="true", native_ref="true", convergence=1.5
    ) == pytest.approx(90.0)
    # Grid-referenced survey edited in the True frame: subtract convergence.
    assert displayed_to_native_azimuth(
        90.0, displayed_frame="true", native_ref="grid", convergence=1.5
    ) == pytest.approx(88.5)
    # Grid frame display of a grid survey: identity (add then subtract).
    assert displayed_to_native_azimuth(
        90.0, displayed_frame="grid", native_ref="grid", convergence=1.5
    ) == pytest.approx(90.0)
    # Magnetic native: subtract declination from true.
    assert displayed_to_native_azimuth(
        90.0, displayed_frame="true", native_ref="magnetic", convergence=1.5, declination=10.0
    ) == pytest.approx(80.0)
