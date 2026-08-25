"""KOP detection must degrade honestly on thin or malformed surveys."""
from __future__ import annotations

import warnings

import pandas as pd

from etools.core.survey.kop import detect_kop


def _survey(mds, incs):
    return pd.DataFrame(
        {"measured_depth": mds, "inclination": incs, "azimuth": [0.0] * len(mds)}
    )


def _normal_survey():
    mds = [float(x) for x in range(0, 3000, 100)]
    incs = [0.0] * 10 + [float(i * 6) for i in range(1, 21)]
    return _survey(mds, incs)


def test_empty_survey_reports_none():
    r = detect_kop(_survey([], []))
    assert r.md is None
    assert r.method == "none"


def test_survey_shorter_than_the_kernel_reports_insufficient_data():
    r = detect_kop(_survey([0.0, 50.0], [0.0, 0.5]))
    assert r.md is None
    assert r.method == "insufficient_data"
    assert r.confidence == 0.0


def test_thin_survey_emits_no_scipy_padding_or_divide_warnings():
    # medfilt zero-pads (UserWarning) when the kernel exceeds the signal
    # length, and np.gradient then divides by zero -- silently producing
    # garbage rather than admitting the survey is too thin to analyse.
    thin = _survey([0.0, 100.0, 200.0], [0.0, 1.0, 2.0])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        detect_kop(thin)
    kinds = {w.category.__name__ for w in caught}
    assert "UserWarning" not in kinds, f"scipy padding warning still raised: {kinds}"
    assert "RuntimeWarning" not in kinds, f"divide-by-zero still raised: {kinds}"


def test_a_duplicate_station_no_longer_perturbs_the_analysis():
    """A re-surveyed depth must not change the answer.

    Before the dedupe, np.gradient divided by the zero MD span and wrote NaN
    into the gradient array (verified: 2 of 17 values). Every candidate test
    is a `> threshold` comparison and `nan > x` is False, so those stations
    were silently excluded from the analysis. Whether that flips the final
    KOP depends on where the duplicate falls; what is guaranteed now is that
    a duplicated station gives exactly the same result as the clean survey.
    """
    mds = [float(x) for x in range(0, 1600, 100)]
    incs = [0.0, 0.2, 0.4, 0.6, 1.0, 6.0, 14.0, 24.0,
            36.0, 48.0, 60.0, 70.0, 78.0, 84.0, 88.0, 90.0]
    clean = detect_kop(_survey(mds, incs))

    # the same well, re-surveyed once at 500 ft mid-build
    dup_mds = mds[:6] + [500.0] + mds[6:]
    dup_incs = incs[:6] + [6.2] + incs[6:]
    dup = detect_kop(_survey(dup_mds, dup_incs))

    assert dup.md == clean.md
    assert dup.method == clean.method
    assert dup.candidates == clean.candidates


def test_duplicate_measured_depths_emit_no_divide_warning():
    mds = [0.0, 100.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
    incs = [0.0, 0.5, 0.6, 1.0, 12.0, 30.0, 55.0, 80.0]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        detect_kop(_survey(mds, incs))
    assert "RuntimeWarning" not in {w.category.__name__ for w in caught}


def test_a_normal_survey_is_completely_unchanged():
    # Pins the pre-existing result exactly: this fix must not move any real
    # well's KOP.
    r = detect_kop(_normal_survey())
    assert r.md == 1000.0
    assert r.method == "piecewise_regression"
    assert r.confidence == 0.8
    assert r.candidates == {
        "rate_of_change": 900.0,
        "piecewise_regression": 1000.0,
        "changepoint": 1800.0,
        "clustering": 900.0,
        "threshold": 1000.0,
    }
