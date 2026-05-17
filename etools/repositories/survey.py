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
        """Returns {citing_type: dataframe} — one frame per planned/drilled header."""
        params: dict[str, object] = {"api": api, "lateral": lateral}
        cond = "h.APINumber = :api AND h.LateralName = :lateral"
        if citing_type:
            cond += " AND h.CitingType = :citing_type"
            params["citing_type"] = citing_type

        sql = text(
            f"SELECT h.CitingType, h.PKey AS HeaderPKey, {_DATA_COLUMNS_QUALIFIED} "
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
        for ct, group in df.groupby("CitingType"):
            out[str(ct)] = group.drop(columns=["CitingType", "HeaderPKey"]).reset_index(drop=True)
        return out
