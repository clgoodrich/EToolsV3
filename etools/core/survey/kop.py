"""Kick-off point and landing-point detection.

Implements a consensus of five methods for KOP detection (rate-of-change,
piecewise regression, change-point, DBSCAN clustering, threshold) and a
straightforward sustained-inclination check for the landing point.

Inputs use **degrees** for inclination throughout, matching the rest of the
processed-survey pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.signal import medfilt
from scipy.stats import linregress
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler

from etools.logging_setup import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class KOPResult:
    md: float | None
    confidence: float
    method: str
    candidates: dict[str, float]


_METHOD_ORDER = ("piecewise_regression", "changepoint", "rate_of_change", "clustering", "threshold")
_METHOD_WEIGHTS = {
    "rate_of_change": 0.25,
    "piecewise_regression": 0.30,
    "changepoint": 0.25,
    "clustering": 0.15,
    "threshold": 0.05,
}


def detect_kop(
    survey: pd.DataFrame,
    *,
    md_col: str = "measured_depth",
    inc_col: str = "inclination",
    vertical_threshold_deg: float = 2.0,
    window: int = 5,
    min_sustained: int = 3,
    consensus_tolerance_ft: float = 200.0,
    confidence_threshold: float = 0.6,
) -> KOPResult:
    """Run five detection methods, then pick a winner via consensus.

    The legacy implementation (main_project_detect_kop.determine_kickoff_point)
    is the spec; this is a tightened port.
    """
    if survey.empty:
        return KOPResult(md=None, confidence=0.0, method="none", candidates={})

    df = survey.sort_values(md_col).reset_index(drop=True)

    # Duplicate MDs make np.gradient divide by zero and emit NaN at those
    # stations. Every candidate test is a `> threshold` comparison and
    # `nan > x` is False, so the affected detection methods dropped out
    # silently -- a survey with one duplicated station returned a KOP backed
    # by 1 of 5 voters instead of 5, with nothing saying so.
    before = len(df)
    df = df.drop_duplicates(subset=md_col, keep="first").reset_index(drop=True)
    if len(df) < before:
        log.warning(
            "kop.duplicate_md_dropped", dropped=before - len(df), kept=len(df)
        )

    # medfilt zero-pads (with a UserWarning) when the kernel exceeds the
    # signal length, which silently produces garbage rather than raising.
    kernel = max(3, window | 1)
    if len(df) < kernel:
        log.warning("kop.survey_too_short", stations=len(df), kernel=kernel)
        return KOPResult(
            md=None, confidence=0.0, method="insufficient_data", candidates={}
        )

    inc = df[inc_col].to_numpy(dtype=float)
    md = df[md_col].to_numpy(dtype=float)

    # Median-filter to suppress single-point noise spikes; rolling stats for ROC.
    smoothed = medfilt(inc, kernel_size=kernel)
    grad = np.gradient(smoothed, md, edge_order=2)
    grad_roll = pd.Series(grad).rolling(window, center=True).mean().bfill().ffill().to_numpy()
    grad_std = pd.Series(grad).rolling(window, center=True).std().bfill().ffill().to_numpy()

    candidates = {
        "rate_of_change": _kop_rate_of_change(md, grad_roll, grad_std, min_sustained),
        "piecewise_regression": _kop_piecewise(md, smoothed),
        "changepoint": _kop_changepoint(md, smoothed, grad_roll),
        "clustering": _kop_clustering(md, smoothed, grad),
        "threshold": _kop_threshold(md, smoothed, vertical_threshold_deg),
    }
    valid = {k: v for k, v in candidates.items() if v is not None}
    if not valid:
        return KOPResult(md=None, confidence=0.0, method="none", candidates={})

    # Hierarchical consensus.
    mds = np.array(list(valid.values()))
    for method in _METHOD_ORDER:
        if method not in valid:
            continue
        primary = valid[method]
        agree = int(np.sum(np.abs(mds - primary) < consensus_tolerance_ft))
        confidence = agree / len(valid)
        if confidence >= confidence_threshold:
            return KOPResult(md=primary, confidence=confidence, method=method, candidates=valid)

    # DBSCAN consensus across all candidates.
    if len(mds) >= 3:
        labels = DBSCAN(eps=15, min_samples=2).fit(mds.reshape(-1, 1)).labels_
        if np.any(labels != -1):
            uniq = labels[labels != -1]
            best = max(set(uniq), key=lambda lbl: int(np.sum(uniq == lbl)))
            cluster_md = float(np.mean(mds[labels == best]))
            confidence = float(np.sum(labels == best)) / len(mds)
            return KOPResult(
                md=cluster_md,
                confidence=confidence,
                method="consensus_cluster",
                candidates=valid,
            )

    # Final fallback: weighted average.
    num = sum(v * _METHOD_WEIGHTS.get(k, 0.1) for k, v in valid.items())
    den = sum(_METHOD_WEIGHTS.get(k, 0.1) for k in valid)
    return KOPResult(
        md=num / den if den else float(np.median(mds)),
        confidence=0.5,
        method="weighted_average",
        candidates=valid,
    )


def detect_kop_simple(
    survey: pd.DataFrame,
    *,
    md_col: str = "measured_depth",
    inc_col: str = "inclination",
    vertical_threshold_deg: float = 3.0,
    crossing_inc_deg: float = 8.0,
    sustained_inc_deg: float = 10.0,
    sustained_count: int = 5,
) -> float | None:
    """Linearly-interpolated MD where the well leaves vertical and begins to
    build inclination.

    Algorithm:
        1. Find the last station whose inclination is below
           ``vertical_threshold_deg`` AND whose nearest forward window of
           ``sustained_count`` stations reaches at least
           ``sustained_inc_deg``.
        2. Walk forward from that station looking for the first segment
           where inclination crosses ``crossing_inc_deg``; return the
           linearly-interpolated MD at that crossing.

    Empirically (e.g. the Javelin South Moon 5-31-32-C4-3H reference WCR),
    matching the operator's published Control_Point requires interpolating
    to an INC threshold of ~8°. Snapping to the last vertical station
    underestimates the MD by 100–150 ft when the section boundary is near
    the kickoff.
    """
    if survey.empty:
        return None
    df = survey.sort_values(md_col).reset_index(drop=True)
    inc = df[inc_col].to_numpy(dtype=float)
    md = df[md_col].to_numpy(dtype=float)
    n = len(inc)
    if n < sustained_count + 1:
        return None

    anchor_idx: int | None = None
    for i in range(n - sustained_count):
        if inc[i] <= vertical_threshold_deg:
            window_max = float(inc[i + 1 : i + 1 + sustained_count].max())
            if window_max >= sustained_inc_deg:
                anchor_idx = i
    if anchor_idx is None:
        return None

    # Walk forward from the anchor, find first interval that brackets the
    # crossing inclination, and linearly interpolate the MD.
    for j in range(anchor_idx, n - 1):
        lo_inc, hi_inc = inc[j], inc[j + 1]
        if lo_inc <= crossing_inc_deg <= hi_inc:
            span = hi_inc - lo_inc
            if span == 0:
                return float(md[j])
            t = (crossing_inc_deg - lo_inc) / span
            return float(md[j] + t * (md[j + 1] - md[j]))
        if lo_inc > crossing_inc_deg:
            # Already above crossing — return this station.
            return float(md[j])

    # No crossing found — fall back to the anchor itself.
    return float(md[anchor_idx])


def detect_kop_backprojection(
    survey: pd.DataFrame,
    *,
    md_col: str = "measured_depth",
    inc_col: str = "inclination",
    vertical_threshold_deg: float = 3.0,
    sustained_inc_deg: float = 10.0,
    sustained_count: int = 5,
    build_fit_max_deg: float = 40.0,
    min_fit_points: int = 3,
) -> KOPResult | None:
    """Geometric KOP via build-arc back-projection.

    The kick-off point is, by definition, where the wellbore leaves vertical
    and the build arc begins — i.e. where inclination is still zero at the
    start of the build. This estimator reconstructs that point directly:

        1. Anchor on the last station still vertical
           (``inc <= vertical_threshold_deg``) that is immediately followed by
           a sustained build (the next ``sustained_count`` stations reach
           ``sustained_inc_deg``).
        2. Fit a straight line to the *early*, near-linear part of the build
           (stations from the anchor up to ``build_fit_max_deg``).
        3. Solve that line for ``inclination = 0`` — the MD where the build,
           extrapolated back, leaves vertical.

    Unlike :func:`detect_kop` (which detects where the build is already
    *obvious* and so lands 100-300 ft deep), this is the textbook
    source-independent definition: it returns the same geometric KOP whether
    the data is the planned trajectory or the as-drilled survey, because both
    share the build geometry.

    Returns ``None`` when there is no clean vertical→build transition to fit
    (too few stations, no anchor, flat/negative build, or a back-projection
    that falls outside the plausible band) — the caller should then fall back
    to :func:`detect_kop`.
    """
    if survey is None or getattr(survey, "empty", True):
        return None
    if md_col not in survey or inc_col not in survey:
        return None
    df = survey.sort_values(md_col).reset_index(drop=True)
    inc = df[inc_col].to_numpy(dtype=float)
    md = df[md_col].to_numpy(dtype=float)
    n = len(inc)
    if n < sustained_count + 1:
        return None

    # Anchor: the LAST vertical station that kicks into a sustained build.
    anchor: int | None = None
    for i in range(n - sustained_count):
        if inc[i] <= vertical_threshold_deg:
            if float(inc[i + 1 : i + 1 + sustained_count].max()) >= sustained_inc_deg:
                anchor = i
    if anchor is None:
        return None

    # Collect the early build window (near-linear part of the arc).
    xs: list[float] = []
    ys: list[float] = []
    for j in range(anchor, n):
        if inc[j] > build_fit_max_deg:
            break
        xs.append(float(md[j]))
        ys.append(float(inc[j]))

    if len(xs) >= min_fit_points:
        fit = linregress(xs, ys)
        slope, intercept, r = fit.slope, fit.intercept, fit.rvalue
        if slope <= 0:
            return None
        kop_md = -intercept / slope
        confidence = float(min(1.0, max(0.0, r * r)))
        method = "build_backprojection"
    else:
        # Too few early-build stations to regress — interpolate the single
        # segment straddling the anchor instead (still a back-projection to
        # the geometric start, just two-point).
        lo_i, hi_i = anchor, min(anchor + 1, n - 1)
        if hi_i == lo_i or inc[hi_i] == inc[lo_i]:
            return None
        slope = (inc[hi_i] - inc[lo_i]) / (md[hi_i] - md[lo_i])
        if slope <= 0:
            return None
        kop_md = md[lo_i] - inc[lo_i] / slope
        confidence = 0.4
        method = "build_backprojection_2pt"

    # Plausibility: the KOP must sit between the surface and where the build
    # has clearly started (a little past the anchor). Reject otherwise so the
    # caller falls back to the statistical detector.
    upper = float(md[min(anchor + sustained_count, n - 1)])
    if not (float(md[0]) - 1.0 <= kop_md <= upper + 1.0):
        return None

    return KOPResult(
        md=float(kop_md),
        confidence=confidence,
        method=method,
        candidates={method: float(kop_md)},
    )


def detect_landing_point(
    survey: pd.DataFrame,
    kop_md: float | None = None,
    *,
    md_col: str = "measured_depth",
    inc_col: str = "inclination",
    horizontal_threshold_deg: float = 85.0,
    min_sustained: int = 5,
) -> float | None:
    """First MD after KOP where inclination stays ≥ horizontal_threshold for N points."""
    if survey.empty:
        return None
    df = survey.sort_values(md_col).reset_index(drop=True)
    if kop_md is not None:
        df = df[df[md_col] >= kop_md].reset_index(drop=True)
    if df.empty:
        return None

    horizontal = (df[inc_col] >= horizontal_threshold_deg).to_numpy()
    for i in range(len(horizontal) - min_sustained + 1):
        if horizontal[i : i + min_sustained].all():
            return float(df[md_col].iloc[i])
    return None


# ---------------------------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------------------------


def _kop_rate_of_change(md, grad_roll, grad_std, min_sustained) -> float | None:
    threshold = float(np.nanmedian(grad_std)) * 2
    if not np.isfinite(threshold) or threshold == 0:
        threshold = float(np.nanstd(grad_roll)) or 1e-6
    n = len(md)
    for i in range(n - min_sustained):
        if np.all(grad_roll[i : i + min_sustained] > threshold):
            return float(md[i])
    return None


def _kop_piecewise(md, inc) -> float | None:
    """Split point minimizing the total OLS residual of two linear fits.

    Mathematically identical to fitting ``linregress`` on ``[:i]`` and ``[i:]``
    for every candidate ``i`` and taking the argmin of the summed residual sum
    of squares — but computed in O(n) via prefix sums instead of O(n²), so a
    high-frequency 10k-point survey no longer blocks the UI for ~15 s.

    For points on a segment, the OLS residual sum of squares is
    ``Syy − Sxy²/Sxx`` (centered moments), each obtainable in O(1) from
    cumulative sums.
    """
    n = len(md)
    if n < 10:
        return None
    start = max(3, int(n * 0.10))
    end = min(n - 3, int(n * 0.70))
    if start >= end:
        return None

    x = np.asarray(md, dtype=float)
    y = np.asarray(inc, dtype=float)
    # Prefix sums of length n+1: c*[k] = sum over the first k elements.
    cx = np.concatenate(([0.0], np.cumsum(x)))
    cy = np.concatenate(([0.0], np.cumsum(y)))
    cxx = np.concatenate(([0.0], np.cumsum(x * x)))
    cyy = np.concatenate(([0.0], np.cumsum(y * y)))
    cxy = np.concatenate(([0.0], np.cumsum(x * y)))

    def _seg_sse(k, sx, sy, sxx, syy, sxy):
        """Residual SSE of the OLS fit over segments with these moments."""
        sxx_c = sxx - sx * sx / k
        syy_c = syy - sy * sy / k
        sxy_c = sxy - sx * sy / k
        # When x is constant on the segment (sxx_c<=0) the best fit is the mean
        # → SSE = syy_c; guard the divide so those entries contribute 0 there.
        ratio = np.divide(
            sxy_c * sxy_c, sxx_c, out=np.zeros_like(sxy_c), where=sxx_c > 0
        )
        return syy_c - ratio

    i = np.arange(start, end)
    kL = i.astype(float)
    kR = (n - i).astype(float)
    errL = _seg_sse(kL, cx[i], cy[i], cxx[i], cyy[i], cxy[i])
    errR = _seg_sse(
        kR, cx[n] - cx[i], cy[n] - cy[i], cxx[n] - cxx[i], cyy[n] - cyy[i], cxy[n] - cxy[i]
    )
    total = errL + errR
    best_idx = int(i[int(np.argmin(total))])
    return float(md[best_idx])


def _kop_changepoint(md, inc, grad_roll) -> float | None:
    """Lightweight change-point: gradient peaks above mean. Skips ruptures dependency."""
    from scipy.signal import find_peaks

    if len(grad_roll) < 5:
        return None
    height = float(np.nanmean(grad_roll))
    peaks, _ = find_peaks(grad_roll, height=height, distance=5)
    return float(md[peaks[0]]) if len(peaks) else None


def _kop_clustering(md, inc, grad) -> float | None:
    if len(md) < 6:
        return None
    try:
        x = StandardScaler().fit_transform(np.column_stack([inc, grad]))
        labels = DBSCAN(eps=0.5, min_samples=3).fit(x).labels_
        first = labels[0]
        for i in range(1, len(labels)):
            if labels[i] != first and labels[i] != -1:
                return float(md[max(0, i - 1)])
    except Exception as exc:
        # One of five consensus voters dropping out used to leave no trace at
        # all, silently shifting the consensus KOP.
        log.warning("kop.clustering_failed", error=str(exc))
        return None
    return None


def _kop_threshold(md, inc, threshold_deg: float) -> float | None:
    n = len(inc)
    for i in range(n - 2):
        if inc[i] > threshold_deg and inc[i + 1] > threshold_deg and inc[i + 2] > threshold_deg:
            return float(md[i])
    return None
