"""WellRepository — read-only access to well/operator/location records.

All queries use SQLAlchemy ``text()`` with bound parameters; no f-string SQL.
The legacy code keyed wells off ``tblAPD.LateralName`` which doesn't exist in
this schema. We use ``DirectionalSurveyHeader`` as the source of truth for
(API, lateral) → well identity.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from etools.db import get_engine
from etools.logging_setup import get_logger
from etools.models import WellHeader
from etools.repositories.survey import canonical_citing_type, newest_header_pkey

log = get_logger(__name__)


_HEADER_COLUMNS = """
    PKey, APINumber, LateralName, WellNameNumber, OperatorName,
    CitingType, DirectionalSurveyCompany, DirectionalSurveyType,
    SurveySurfaceElevation, SurfaceElevationReference,
    NorthReference, iFGridConvergence, iFGridScaleFactor,
    SurfaceLatitude, SurfaceLongitude, X AS SurfaceX, Y AS SurfaceY,
    UTMZone, WellSurfaceLocationPLSS,
    UploadFileName, UploadDateTime
""".strip()


def _row_to_header(row: pd.Series) -> WellHeader:
    return WellHeader(
        pkey=int(row["PKey"]),
        api=str(row["APINumber"]).strip(),
        lateral=str(row["LateralName"]).strip(),
        well_name=row.get("WellNameNumber"),
        operator=row.get("OperatorName"),
        citing_type=canonical_citing_type(row.get("CitingType")),
        survey_company=row.get("DirectionalSurveyCompany"),
        survey_type=row.get("DirectionalSurveyType"),
        surface_elevation=row.get("SurveySurfaceElevation"),
        elevation_reference=row.get("SurfaceElevationReference"),
        north_reference=row.get("NorthReference"),
        grid_convergence=row.get("iFGridConvergence"),
        grid_scale_factor=row.get("iFGridScaleFactor"),
        surface_lat=row.get("SurfaceLatitude"),
        surface_lon=row.get("SurfaceLongitude"),
        surface_x=row.get("SurfaceX"),
        surface_y=row.get("SurfaceY"),
        utm_zone=row.get("UTMZone"),
        plss_location=row.get("WellSurfaceLocationPLSS"),
        upload_filename=row.get("UploadFileName"),
        upload_datetime=row.get("UploadDateTime"),
    )


class WellRepository:
    def __init__(self, engine=None) -> None:
        self.engine = engine or get_engine()

    def list_headers(self, api: str, lateral: str = "0000") -> list[WellHeader]:
        """All survey headers for a given (API, lateral). Multiple = planned + drilled."""
        sql = text(
            f"SELECT {_HEADER_COLUMNS} "
            "FROM DirectionalSurveyHeader "
            "WHERE APINumber = :api AND LateralName = :lateral"
        )
        with self.engine.connect() as cn:
            df = pd.read_sql_query(sql, cn, params={"api": api, "lateral": lateral})
        log.info("well.headers", api=api, lateral=lateral, rows=len(df))
        headers = [_row_to_header(r) for _, r in df.iterrows()]
        # One header per citing type — the newest, matching the survey the
        # SurveyRepository returns for it.
        by_type: dict[str, list[WellHeader]] = {}
        for h in headers:
            by_type.setdefault(h.citing_type, []).append(h)
        keep = {
            newest_header_pkey((h.pkey, h.upload_datetime) for h in group)
            for group in by_type.values()
        }
        return [h for h in headers if h.pkey in keep]
