"""Edit operations on a raw MD/INC/AZI survey table.

All functions are pure — they take the raw DataFrame (repository column
names: ``MeasuredDepth`` / ``Inclination`` / ``Azimuth``) and return a new
one. The UI applies the result to ``state.surveys[citing]`` and re-runs the
post-load pipeline so TVD, coordinates, KOP, clearances, and every tab
cascade from the same single source of truth.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

_MD_TOL_FT = 0.51  # stations are integer-ish feet; half a foot finds "the" row


def _require_finite_md(md: float) -> float:
    """Reject NaN/inf MDs. ``float("nan")`` and ``float("inf")`` both slip
    past a plain ``float()`` parse in the UI, and a non-finite MD silently
    poisons interpolation (all-NaN station) or, via ``_locate``, mutates an
    arbitrary row. Fail loudly instead."""
    md = float(md)
    if not math.isfinite(md):
        raise ValueError("MD must be a finite number")
    return md


def _sorted(raw: pd.DataFrame) -> pd.DataFrame:
    return raw.sort_values("MeasuredDepth").reset_index(drop=True)


def _locate(df: pd.DataFrame, md: float) -> int:
    """Index of the station at ``md`` (within tolerance) or raise."""
    md = _require_finite_md(md)
    deltas = (df["MeasuredDepth"].astype(float) - float(md)).abs()
    idx = int(deltas.idxmin())
    if float(deltas.loc[idx]) > _MD_TOL_FT:
        raise ValueError(f"no survey station at MD {md:,.1f} ft")
    return idx


def interpolate_raw_station(raw: pd.DataFrame, md: float) -> dict[str, float]:
    """Linearly interpolate INC/AZI at ``md`` between the bracketing stations.

    Azimuth interpolates on the unwrapped angle so a 359°→1° crossing
    doesn't sweep backwards through 180°. Out-of-range MDs clamp to the
    first/last station's values.
    """
    if raw.empty:
        raise ValueError("survey is empty")
    md = _require_finite_md(md)
    df = _sorted(raw)
    mds = df["MeasuredDepth"].to_numpy(dtype=float)
    inc = df["Inclination"].to_numpy(dtype=float)
    azi = df["Azimuth"].to_numpy(dtype=float)
    if md <= mds[0]:
        return {"MeasuredDepth": float(md), "Inclination": float(inc[0]), "Azimuth": float(azi[0])}
    if md >= mds[-1]:
        return {"MeasuredDepth": float(md), "Inclination": float(inc[-1]), "Azimuth": float(azi[-1])}
    azi_unwrapped = np.degrees(np.unwrap(np.radians(azi)))
    return {
        "MeasuredDepth": float(md),
        "Inclination": float(np.interp(md, mds, inc)),
        "Azimuth": float(np.interp(md, mds, azi_unwrapped)) % 360.0,
    }


def insert_station(
    raw: pd.DataFrame,
    md: float,
    *,
    inclination: float | None = None,
    azimuth: float | None = None,
) -> pd.DataFrame:
    """Insert a station at ``md``; INC/AZI default to interpolated values.

    Inserting at an existing MD replaces that station.
    """
    station = interpolate_raw_station(raw, md)
    if inclination is not None:
        station["Inclination"] = float(inclination)
    if azimuth is not None:
        station["Azimuth"] = float(azimuth) % 360.0
    out = pd.concat([raw, pd.DataFrame([station])], ignore_index=True)
    # Stable sort keeps the appended row last among equal MDs → it wins.
    return _sorted(out).drop_duplicates(subset="MeasuredDepth", keep="last").reset_index(drop=True)


def update_station(
    raw: pd.DataFrame,
    old_md: float,
    *,
    md: float | None = None,
    inclination: float | None = None,
    azimuth: float | None = None,
) -> pd.DataFrame:
    """Change MD, inclination, and/or azimuth of the station at ``old_md``."""
    df = raw.copy().reset_index(drop=True)
    idx = _locate(df, old_md)
    if md is not None:
        new_md = _require_finite_md(md)
        # Moving a station onto an existing MD must replace that station, not
        # create a second row at the same depth (which process_survey would
        # later drop_duplicates away, silently losing one of the two).
        collision = df.index[
            (df["MeasuredDepth"].astype(float) - new_md).abs() <= _MD_TOL_FT
        ].difference([idx])
        if len(collision):
            df = df.drop(index=collision)
        df.loc[idx, "MeasuredDepth"] = new_md
    if inclination is not None:
        df.loc[idx, "Inclination"] = float(inclination)
    if azimuth is not None:
        df.loc[idx, "Azimuth"] = float(azimuth) % 360.0
    return _sorted(df)


def delete_station(raw: pd.DataFrame, md: float) -> pd.DataFrame:
    df = _sorted(raw)
    idx = _locate(df, md)
    return df.drop(index=idx).reset_index(drop=True)


def displayed_to_native_azimuth(
    value: float,
    *,
    displayed_frame: str,
    native_ref: str | None,
    convergence: float,
    declination: float = 0.0,
) -> float:
    """Convert an azimuth typed in the displayed frame back to the raw
    survey's native north reference.

    welleng conventions: azi_grid = azi_true − convergence,
    azi_magnetic = azi_true − declination.
    """
    if not math.isfinite(value):
        raise ValueError("azimuth must be a finite number")
    azi_true = value if displayed_frame.lower().startswith("t") else value + convergence
    ref = (native_ref or "true").strip().lower()
    if ref.startswith("g"):
        return (azi_true - convergence) % 360.0
    if ref.startswith("m"):
        return (azi_true - declination) % 360.0
    return azi_true % 360.0
