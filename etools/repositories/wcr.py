"""WCRRepository — well info + casing + perforations for WCR generation.

Reads from ``tblAPDWCRWellInfo`` (joined with ``tblAPD`` and
``DirectionalSurveyHeader`` for operator/well-name resolution),
``vwDM_ConstructCasingCement``, and ``vwDM_ConstructPerf``.

All queries use SQLAlchemy ``text()`` with bound parameters.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from etools.db import get_engine
from etools.logging_setup import get_logger
from etools.models import WCRBundle, WCRWellInfo

log = get_logger(__name__)


_CASING_FEATURE_ORDER = (
    "Hole",
    "Conductor Pipe",
    "Surface Casing",
    "Intermediate Casing",
    "Production Casing",
    "Production Casing 2",
    "Tubing",
    "DV/Stage Tool",
)


class WCRRepository:
    def __init__(self, engine=None) -> None:
        self.engine = engine or get_engine()

    def get_bundle(self, api: str, lateral: str = "0000") -> WCRBundle:
        """Fetch every WCR-relevant record for (API, lateral) in one call."""
        info = self._get_well_info(api, lateral)
        casing = self._get_casing(api)
        perfs = self._get_perforations(api)
        log.info(
            "wcr.bundle",
            api=api,
            lateral=lateral,
            has_info=info is not None,
            casing_rows=len(casing),
            perf_rows=len(perfs),
        )
        return WCRBundle(info=info, casing=casing, perforations=perfs)

    def get_latest_wcr_submission(self, api: str) -> dict | None:
        """SundryNo + SubmitDate of the most recent WCR sundry for this API.

        Feeds the personal tracking workbook (date-filed / days-to-process).
        Returns None when the well has no sundry records.
        """
        sql = text(
            """
            SELECT TOP 1 wi.SundryNo, tas.SubmitDate, ta.Well_Nm
            FROM tblAPDWCRWellInfo wi
            INNER JOIN tblAPD ta        ON wi.APDNo = ta.APDNo
            INNER JOIN tblAPDSundry tas ON ta.API_WellNo = tas.APINO
            WHERE LEFT(ta.API_WellNo, 10) = :api
            ORDER BY tas.SubmitDate DESC
            """
        )
        with self.engine.connect() as cn:
            df = pd.read_sql_query(sql, cn, params={"api": api[:10]})
        if df.empty:
            return None
        row = df.iloc[0]
        return {
            "sundry_no": row.get("SundryNo"),
            "submit_date": _to_dt(row.get("SubmitDate")),
            "well_name": row.get("Well_Nm"),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_well_info(self, api: str, lateral: str) -> WCRWellInfo | None:
        sql = text(
            """
            SELECT
                ta.API_WellNo,
                ta.Well_Nm,
                dsh.OperatorName,
                ta.OpNo,
                wi.WorkType, wi.WellType, wi.WellStatus,
                wi.SpudRigDate, wi.RotaryRigDate, wi.TDReachedDate,
                wi.CompletedOrAbandonedDate,
                wi.FieldNo, wi.CountyNo,
                ta.Proposed_Depth_TVD AS ProposedTVD,
                ta.Proposed_Depth_MD  AS ProposedMD,
                ta.Elevation,
                ta.Slant,
                wi.SurfaceOwner,
                wi.MineralLeaseType,
                wi.MineralLeaseNumber,
                ta.Legal_Description,
                wi.APDNo
            FROM tblAPDWCRWellInfo wi
            INNER JOIN tblAPD ta              ON wi.APDNo = ta.APDNo
            LEFT  JOIN DirectionalSurveyHeader dsh
                   ON LEFT(ta.API_WellNo, 10) = dsh.APINumber
                  AND dsh.LateralName = :lateral
            WHERE ta.API_WellNo = :full_api
            """
        )
        full_api = f"{api}{lateral}"
        with self.engine.connect() as cn:
            df = pd.read_sql_query(sql, cn, params={"full_api": full_api, "lateral": lateral})
        if df.empty:
            return None
        row = df.drop_duplicates().iloc[0]
        return WCRWellInfo(
            api_well_no=str(row["API_WellNo"]),
            well_name=row.get("Well_Nm"),
            operator=row.get("OperatorName"),
            operator_no=str(row["OpNo"]) if pd.notna(row.get("OpNo")) else None,
            work_type=row.get("WorkType"),
            well_type=row.get("WellType"),
            well_status=row.get("WellStatus"),
            slant=row.get("Slant"),
            field_no=int(row["FieldNo"]) if pd.notna(row.get("FieldNo")) else None,
            county_no=int(row["CountyNo"]) if pd.notna(row.get("CountyNo")) else None,
            proposed_tvd_ft=_to_float(row.get("ProposedTVD")),
            proposed_md_ft=_to_float(row.get("ProposedMD")),
            elevation_ft=_to_float(row.get("Elevation")),
            spud_date=_to_dt(row.get("SpudRigDate")),
            rotary_date=_to_dt(row.get("RotaryRigDate")),
            td_date=_to_dt(row.get("TDReachedDate")),
            completion_date=_to_dt(row.get("CompletedOrAbandonedDate")),
            surface_owner=row.get("SurfaceOwner"),
            mineral_lease_type=row.get("MineralLeaseType"),
            mineral_lease_number=row.get("MineralLeaseNumber"),
            legal_description=row.get("Legal_Description"),
            apd_no=int(row["APDNo"]) if pd.notna(row.get("APDNo")) else None,
        )

    def _get_casing(self, api: str) -> pd.DataFrame:
        # NB: the view's PKey is the CONSTRUCT key, not the well key —
        # joining it straight onto well.PKey silently returns another
        # well's strings whenever the integers collide.
        sql = text(
            """
            SELECT Feature, [Top] AS Top_MD, Bottom AS Bottom_MD,
                   Diam AS Diameter, [Weight], Grade, [Connection Type] AS ConnectionType,
                   [Cement Top] AS CementTop, [Cement Bottom] AS CementBottom,
                   [Cement Type] AS CementType,
                   Sacks, Yield, [Cement Weight] AS CementWeight
            FROM well w
            INNER JOIN construct c ON c.WellKey = w.PKey
            INNER JOIN vwDM_ConstructCasingCement vw ON vw.PKey = c.PKey
            WHERE w.WellID = :api
              AND Feature IS NOT NULL
            """
        )
        with self.engine.connect() as cn:
            df = pd.read_sql_query(sql, cn, params={"api": api})
        if df.empty:
            return df

        df = df.drop_duplicates(keep="first")
        dropped = sorted(set(df["Feature"]) - set(_CASING_FEATURE_ORDER))
        if dropped:
            log.info("wcr.casing.unknown_features_dropped", api=api, features=dropped)
        df = df[df["Feature"].isin(_CASING_FEATURE_ORDER)]
        df["Feature"] = pd.Categorical(df["Feature"], categories=_CASING_FEATURE_ORDER, ordered=True)
        df = df.sort_values(["Feature", "Bottom_MD"]).reset_index(drop=True)
        return df

    def _get_perforations(self, api: str) -> pd.DataFrame:
        sql = text(
            """
            SELECT MD, TVD, [Top] AS Top_MD, Bottom AS Bottom_MD,
                   [Zone Type] AS ZoneType, Formation, Producing,
                   TDS, [Perf Date] AS PerfDate, Status, Comments
            FROM well w
            INNER JOIN construct c ON c.WellKey = w.PKey
            INNER JOIN vwDM_ConstructPerf vp ON vp.PKey = c.PKey
            WHERE w.WellID = :api
            ORDER BY MD
            """
        )
        with self.engine.connect() as cn:
            df = pd.read_sql_query(sql, cn, params={"api": api})
        return df.drop_duplicates(keep="first").reset_index(drop=True)


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


def _to_float(value) -> float | None:
    return float(value) if value is not None and pd.notna(value) else None


def _to_dt(value):
    if value is None or pd.isna(value):
        return None
    return pd.to_datetime(value).to_pydatetime()
