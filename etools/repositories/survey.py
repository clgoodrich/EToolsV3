"""SurveyRepository — raw MD/INC/AZI rows from DirectionalSurveyData."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from etools.db import get_engine
from etools.logging_setup import get_logger

log = get_logger(__name__)


_DATA_COLUMNS_UNQUALIFIED = """
    MeasuredDepth, Inclination, Azimuth,
    DoglegRate, VerticalSection,
    NorthOffset, EastOffset, TrueVerticalDepth, TrueVerticalElevationCalc,
    LatitudeCalc AS Latitude, LongitudeCalc AS Longitude,
    X, Y, UTMZone, DirectionalPointNote
""".strip()

_DATA_COLUMNS_QUALIFIED = """
    d.MeasuredDepth, d.Inclination, d.Azimuth,
    d.DoglegRate, d.VerticalSection,
    d.NorthOffset, d.EastOffset, d.TrueVerticalDepth, d.TrueVerticalElevationCalc,
    d.LatitudeCalc AS Latitude, d.LongitudeCalc AS Longitude,
    d.X, d.Y, d.UTMZone, d.DirectionalPointNote
""".strip()


def canonical_citing_type(value) -> str:
    """Map a DB ``CitingType`` onto the app's two keys.

    The column is free text: ``ASDRILLED`` / ``Asdrilled`` / ``PLANNED`` /
    ``planned`` all occur alongside ``AsDrilled`` / ``Planned``. Every picker
    looks up the exact ``"AsDrilled"`` / ``"Planned"`` keys, so an
    upper-case upload read as "no drilled survey" and fell back to the plan.
    """
    s = str(value or "").strip()
    low = s.lower()
    if "drill" in low:
        return "AsDrilled"
    if low.startswith("plan"):
        return "Planned"
    return s


class SurveyRepository:
    def __init__(self, engine=None) -> None:
        self.engine = engine or get_engine()

    def get_points_by_header_pkey(self, header_pkey: int) -> pd.DataFrame:
        """All survey points for a given DirectionalSurveyHeader.PKey."""
        sql = text(
            f"SELECT {_DATA_COLUMNS_UNQUALIFIED} "
            "FROM DirectionalSurveyData "
            "WHERE DirectionalSurveyHeaderKey = :pkey "
            "ORDER BY MeasuredDepth"
        )
        with self.engine.connect() as cn:
            df = pd.read_sql_query(sql, cn, params={"pkey": int(header_pkey)})
        log.info("survey.points", header_pkey=header_pkey, rows=len(df))
        return df

    def get_points_by_api_lateral(
        self, api: str, lateral: str = "0000", citing_type: str | None = None
    ) -> dict[str, pd.DataFrame]:
        """Returns {citing_type: dataframe} — one frame per planned/drilled header.

        Each frame carries its header's azimuth reference in
        ``frame.attrs["north_reference"]``.

        Keys are canonical (``"AsDrilled"`` / ``"Planned"``). When several
        headers share a citing type (re-uploads), only the newest one's
        stations are returned — concatenating them interleaved two different
        surveys into one zig-zagging trajectory.
        """
        params: dict[str, object] = {"api": api, "lateral": lateral}
        cond = "h.APINumber = :api AND h.LateralName = :lateral"

        sql = text(
            f"SELECT h.CitingType, h.PKey AS HeaderPKey, h.UploadDateTime AS HeaderUpload, "
            "h.NorthReference AS HeaderNorthRef, "
            f"{_DATA_COLUMNS_QUALIFIED} "
            "FROM DirectionalSurveyData d "
            "JOIN DirectionalSurveyHeader h "
            "  ON d.DirectionalSurveyHeaderKey = h.PKey "
            f"WHERE {cond} "
            "ORDER BY h.CitingType, d.MeasuredDepth"
        )
        with self.engine.connect() as cn:
            df = pd.read_sql_query(sql, cn, params=params)

        out: dict[str, pd.DataFrame] = {}
        if df.empty:
            return out
        df["CitingType"] = df["CitingType"].map(canonical_citing_type)
        if citing_type:
            df = df[df["CitingType"] == canonical_citing_type(citing_type)]
        for ct, group in df.groupby("CitingType"):
            newest = newest_header_pkey(
                group[["HeaderPKey", "HeaderUpload"]].drop_duplicates().itertuples(index=False)
            )
            if group["HeaderPKey"].nunique() > 1:
                log.warning(
                    "survey.duplicate_headers",
                    api=api, lateral=lateral, citing=ct,
                    headers=sorted(int(p) for p in group["HeaderPKey"].unique()),
                    kept=newest,
                )
            group = group[group["HeaderPKey"] == newest]
            frame = group.drop(
                columns=["CitingType", "HeaderPKey", "HeaderUpload", "HeaderNorthRef"]
            ).reset_index(drop=True)
            # The azimuth reference travels with the stations, so consumers
            # that only get the frame (WCR, APD/WCR promote) stop assuming
            # "grid" for a true-north survey.
            nref = group["HeaderNorthRef"].iloc[0]
            frame.attrs["north_reference"] = None if pd.isna(nref) else str(nref)
            out[str(ct)] = frame
        return out


def newest_header_pkey(rows) -> int:
    """PKey of the newest of ``(pkey, upload_datetime)`` rows (upload time,
    then PKey as the tie-break / fallback when the time is missing)."""

    def key(r):
        pkey, uploaded = r[0], r[1]
        ts = pd.Timestamp(uploaded) if uploaded is not None and not pd.isna(uploaded) else pd.Timestamp.min
        return (ts, int(pkey))

    return int(max(rows, key=key)[0])
