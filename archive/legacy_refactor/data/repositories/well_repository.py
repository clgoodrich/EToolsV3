"""
Well repository for EToolsV3.

This module provides data access for well-related information from the SQL Server database.
"""

from typing import Optional
import pandas as pd

from data.repositories.base_repository import BaseRepository
from data.models.well import WellLocation, WellInfo, CasingString, WellConstruction
from utils.errors import WellNotFoundError, InvalidAPINumberError, DatabaseQueryError


class WellRepository(BaseRepository):
    """Repository for well data access."""

    def get_well_info(self, api: str, lateral: str = '0000') -> WellInfo:
        """
        Get general well information.

        Args:
            api: 10-digit API number.
            lateral: Lateral name/identifier.

        Returns:
            WellInfo object.

        Raises:
            InvalidAPINumberError: If API format is invalid.
            WellNotFoundError: If well not found.
            DatabaseQueryError: If query fails.
        """
        api = self._sanitize_api_number(api)

        query = """
            SELECT
                ta.APDNo,
                ta.Well_Nm as WellName,
                dsh.WellNameNumber,
                dsh.OperatorName,
                ta.API_WellNo as APINumber,
                ta.Proposed_Depth_MD,
                ta.Proposed_Depth_TVD
            FROM [dbo].[tblAPD] ta
            LEFT JOIN DirectionalSurveyHeader dsh
                ON LEFT(ta.API_WellNo, 10) = dsh.APINumber
            WHERE ta.API_WellNo = :api_lateral
                AND dsh.LateralName = :lateral
        """

        params = {'api_lateral': f"{api}{lateral}", 'lateral': lateral}
        result = self._execute_query(query, params, "get_well_info")

        if result.empty:
            raise WellNotFoundError(api, lateral)

        row = result.iloc[0]
        return WellInfo(
            api_number=api,
            well_name=row.get('WellName'),
            well_number=row.get('WellNameNumber'),
            operator_name=row.get('OperatorName'),
            apd_number=row.get('APDNo'),
            proposed_depth_md=row.get('Proposed_Depth_MD'),
            proposed_depth_tvd=row.get('Proposed_Depth_TVD')
        )

    def get_well_location(self, api: str, lateral: str = '0000') -> WellLocation:
        """
        Get well location data (surface and bottomhole coordinates).

        Args:
            api: 10-digit API number.
            lateral: Lateral name/identifier.

        Returns:
            WellLocation object.

        Raises:
            InvalidAPINumberError: If API format is invalid.
            WellNotFoundError: If well location not found.
            DatabaseQueryError: If query fails.
        """
        api = self._sanitize_api_number(api)

        # First get APD number
        apd_query = """
            SELECT APDNo
            FROM [dbo].[tblAPD]
            WHERE API_WellNo = :api_lateral
        """
        apd_result = self._execute_query(
            apd_query,
            {'api_lateral': f"{api}{lateral}"},
            "get_apd_number"
        )

        if apd_result.empty:
            raise WellNotFoundError(api, lateral)

        apd_no = apd_result.iloc[0]['APDNo']

        # Get location data
        loc_query = """
            SELECT
                [Wh_Sec] as Section,
                [Wh_Twpn] as Township,
                [Wh_Twpd] as TownshipDirection,
                [Wh_RngN] as Range,
                [Wh_RngD] as RangeDirection,
                [Wh_Pm] as Baseline,
                [Wh_FtNS] as FNSL,
                [Wh_Ns] as FNSLDirection,
                [Wh_FtEW] as FEWL,
                [Wh_EW] as FEWLDirection,
                [Zone_Name] as ZoneName,
                [Wh_Qtr] as Quarter,
                [Wh_X] as SurfaceEasting,
                [Wh_Y] as SurfaceNorthing,
                [Bh_X] as BHEasting,
                [Bh_Y] as BHNorthing
            FROM [dbo].[tblAPDLoc]
            WHERE APDNO = :apd_no
        """

        loc_result = self._execute_query(loc_query, {'apd_no': apd_no}, "get_well_location")

        if loc_result.empty:
            # Try alternative query without lateral
            raise WellNotFoundError(api, lateral)

        row = loc_result.iloc[0]

        # Strip string columns if needed
        def strip_val(val):
            return val.strip() if isinstance(val, str) else val

        return WellLocation(
            api_number=api,
            section=strip_val(row.get('Section')),
            township=strip_val(row.get('Township')),
            township_direction=strip_val(row.get('TownshipDirection')),
            range=strip_val(row.get('Range')),
            range_direction=strip_val(row.get('RangeDirection')),
            baseline=strip_val(row.get('Baseline')),
            quarter=strip_val(row.get('Quarter')),
            fnsl=float(row['FNSL']) if row.get('FNSL') else None,
            fnsl_direction=strip_val(row.get('FNSLDirection')),
            fewl=float(row['FEWL']) if row.get('FEWL') else None,
            fewl_direction=strip_val(row.get('FEWLDirection')),
            zone_name=strip_val(row.get('ZoneName')),
            surface_easting=float(row['SurfaceEasting']) if row.get('SurfaceEasting') else None,
            surface_northing=float(row['SurfaceNorthing']) if row.get('SurfaceNorthing') else None,
            bh_easting=float(row['BHEasting']) if row.get('BHEasting') else None,
            bh_northing=float(row['BHNorthing']) if row.get('BHNorthing') else None
        )

    def get_drilled_depths(self, api: str) -> pd.DataFrame:
        """
        Get drilled casing depths for a well.

        Args:
            api: 10-digit API number.

        Returns:
            DataFrame with Feature and CasingBottom columns.

        Raises:
            InvalidAPINumberError: If API format is invalid.
            DatabaseQueryError: If query fails.
        """
        api = self._sanitize_api_number(api)

        query = """
            SELECT
                cc.Feature,
                cc.CasingBottom
            FROM Well w
            LEFT JOIN Construct c ON c.WellKey = w.PKey
            LEFT JOIN ConstructCasing cc ON cc.ConstructKey = c.PKey
            WHERE w.WellID = :api
                AND Weight IS NOT NULL
                AND cc.Feature != 'Hole'
        """

        result = self._execute_query(query, {'api': api}, "get_drilled_depths")

        # Strip string columns and convert CasingBottom to numeric
        if not result.empty:
            result = result.map(lambda x: x.strip() if isinstance(x, str) else x)
            result['CasingBottom'] = pd.to_numeric(result['CasingBottom'], errors='coerce')
            result = result.dropna(subset=['CasingBottom'])
            result = result.sort_values('CasingBottom')

        return result

    def get_casing_data(self, api: str) -> WellConstruction:
        """
        Get complete casing construction data for a well.

        Args:
            api: 10-digit API number.

        Returns:
            WellConstruction object with all casing strings.

        Raises:
            InvalidAPINumberError: If API format is invalid.
            DatabaseQueryError: If query fails.
        """
        api = self._sanitize_api_number(api)

        query = """
            SELECT
                cc.Feature,
                cc.CasingDiameter,
                cc.Weight,
                cc.Grade,
                cc.CasingTop,
                cc.CasingBottom,
                cc.ConnectionType,
                cc.CementTop,
                cc.InternalYield,
                cc.Collapse,
                cc.JointStrength,
                cc.BodyYield,
                cc.ID as InnerDiameter,
                cc.OD as OuterDiameter,
                cc.Drift,
                cc.WallThickness
            FROM Well w
            LEFT JOIN Construct c ON c.WellKey = w.PKey
            LEFT JOIN ConstructCasing cc ON cc.ConstructKey = c.PKey
            WHERE w.WellID = :api
                AND cc.Feature IS NOT NULL
            ORDER BY cc.CasingBottom
        """

        result = self._execute_query(query, {'api': api}, "get_casing_data")

        casing_strings = []
        for _, row in result.iterrows():
            casing_string = CasingString(
                feature=row['Feature'],
                diameter=float(row['CasingDiameter']) if row.get('CasingDiameter') else 0.0,
                weight=float(row['Weight']) if row.get('Weight') else 0.0,
                grade=row.get('Grade', ''),
                top_depth=float(row['CasingTop']) if row.get('CasingTop') else 0.0,
                bottom_depth=float(row['CasingBottom']) if row.get('CasingBottom') else 0.0,
                connection_type=row.get('ConnectionType'),
                cement_top=float(row['CementTop']) if row.get('CementTop') else None,
                internal_yield=float(row['InternalYield']) if row.get('InternalYield') else None,
                collapse=float(row['Collapse']) if row.get('Collapse') else None,
                joint_strength=float(row['JointStrength']) if row.get('JointStrength') else None,
                body_yield=float(row['BodyYield']) if row.get('BodyYield') else None,
                id=float(row['InnerDiameter']) if row.get('InnerDiameter') else None,
                od=float(row['OuterDiameter']) if row.get('OuterDiameter') else None,
                drift=float(row['Drift']) if row.get('Drift') else None,
                wall_thickness=float(row['WallThickness']) if row.get('WallThickness') else None
            )
            casing_strings.append(casing_string)

        return WellConstruction(
            api_number=api,
            casing_strings=casing_strings,
            total_depth=casing_strings[-1].bottom_depth if casing_strings else None
        )

    def well_exists(self, api: str, lateral: str = '0000') -> bool:
        """
        Check if a well exists in the database.

        Args:
            api: 10-digit API number.
            lateral: Lateral name/identifier.

        Returns:
            True if well exists, False otherwise.
        """
        try:
            api = self._sanitize_api_number(api)

            query = """
                SELECT COUNT(*) as count
                FROM [dbo].[tblAPD]
                WHERE API_WellNo = :api_lateral
            """

            count = self._execute_scalar(
                query,
                {'api_lateral': f"{api}{lateral}"},
                "well_exists"
            )

            return count > 0

        except Exception:
            return False

    def get_max_measured_depth(self, api: str, lateral: str, citing_type: str = 'Planned') -> Optional[float]:
        """
        Get maximum measured depth from directional survey data.

        Args:
            api: 10-digit API number.
            lateral: Lateral name.
            citing_type: Survey citing type ('Planned', 'Drilled', etc.).

        Returns:
            Maximum measured depth, or None if not found.
        """
        api = self._sanitize_api_number(api)

        query = """
            SELECT MAX(MeasuredDepth) AS MaxMeasuredDepth
            FROM DirectionalSurveyHeader dsh
            JOIN DirectionalSurveyData dsd ON dsh.PKey = dsd.DirectionalSurveyHeaderKey
            WHERE dsh.APINumber = :api
                AND dsh.LateralName = :lateral
                AND CitingType = :citing_type
        """

        result = self._execute_scalar(
            query,
            {'api': api, 'lateral': lateral, 'citing_type': citing_type},
            "get_max_measured_depth"
        )

        return float(result) if result else None
