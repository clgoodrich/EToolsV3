from GUISurveyTab import ClearanceProcess
from DXSurveys import SurveyProcess
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks
import time
from shapely.geometry import Polygon
from shapely.affinity import translate
from pyproj import Proj, Geod, Transformer, transform
import sqlite3
import pandas as pd
import pyodbc
import numpy as np
import welleng.clearance
import welleng as we
import ModuleAgnostic as ma
from shapely.geometry import Point, LineString, MultiPoint, Polygon
import math
import copy
import utm
import os
import os
from sqlalchemy import create_engine
from urllib.parse import quote_plus
from functools import lru_cache
import logging
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
import geopandas as gpd


class DatabaseManager:
    def __init__(self):
        # Initialize the connection
        self.connector = SQLConnector()
        self.engine = self.connector.get_engine()

        # Create a session factory
        self.Session = sessionmaker(bind=self.engine)

    @contextmanager
    def get_session(self):
        """Context manager for database sessions"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    # Example 1: Raw SQL query
    def execute_raw_query(self, query, params=None):
        with self.engine.connect() as connection:
            result = connection.execute(query, params or {})
            return result.fetchall()

    # Example 2: Query using pandas
    def query_to_dataframe(self, query):
        return pd.read_sql_query(query, self.engine)

    # Example 3: Execute with parameters
    def get_well_data(self, well_id):
        query = """
        SELECT *
        FROM Wells
        WHERE WellID = :well_id
        """
        return self.execute_raw_query(query, {'well_id': well_id})


class SQLConnector:
    def __init__(self, login_file="logininfo.txt"):
        self.login_file = login_file
        self.logger = logging.getLogger(__name__)
        self.engine = self._create_sql_connection()

    def _parse_credentials(self, content):
        """Parse username and password from file content."""
        try:
            lines = content.strip().split('\n')
            return {
                'user': lines[0].split('=')[1].strip(),
                'password': lines[1].split('=')[1].strip()
            }
        except (IndexError, KeyError) as e:
            self.logger.error(f"Error parsing credentials: {e}")
            return None

    def _get_credentials(self):
        """Read credentials from file."""
        try:
            file_path = os.path.join(os.getcwd(), self.login_file)
            with open(file_path, 'r') as file:
                content = file.read()
            return self._parse_credentials(content)
        except FileNotFoundError:
            self.logger.warning(f"Credentials file not found: {self.login_file}")
            return None

    @lru_cache(maxsize=1)
    def _create_connection_string(self):
        """Create connection string with caching."""
        credentials = self._get_credentials()
        # print(credentials)
        # print(foo)
        credentials = {}
        if credentials:
            # Production connection
            params = {
                'driver': '{SQL Server}',
                'server': 'oilgas-sql-prod.ogm.utah.gov',
                'database': 'UTRBDMSNET',
                'uid': credentials['user'],
                'pwd': credentials['password']
            }

            conn_str = (
                "DRIVER={driver};"
                "SERVER={server};"
                "DATABASE={database};"
                "UID={uid};"
                "PWD={pwd}"
            ).format(**params)
            # print('conn', [conn_str])
        else:
            # Fallback to local connection
            conn_str = (
                "Driver={SQL Server};"
                r"Server=CGDESKTOP\SQLEXPRESS;"
                "Database=UTRBDMSNET;"
                "Trusted_Connection=yes;"
            )
        # print('con_str', conn_str)
        return quote_plus(conn_str)

    def _create_sql_connection(self):
        """Create SQLAlchemy engine."""
        try:
            connection_string = self._create_connection_string()
            # print(f"mssql+pyodbc:///?odbc_connect={connection_string}")
            return create_engine(
                f"mssql+pyodbc:///?odbc_connect={connection_string}",
                pool_pre_ping=True,
                pool_recycle=3600
            )
        except Exception as e:
            self.logger.error(f"Failed to create SQL connection: {e}")
            raise

    def get_engine(self):
        """Return SQLAlchemy engine instance."""
        return self.engine



class SQLQueriesClass:
    def __init__(self):
        self.well_elevation = None
        self.base_dx_df_drilled_original = None
        self.base_dx_df_planned_original = None
        self.base_dx_df_original = None
        self.base_dx_df = None
        self.base_dx_df_drilled = None
        self.base_dx_df_planned = None
        self.convergence_angle = None

    # def sqlConnect(self):
    #
    #     def getPWAndUser(file):
    #         lines = file.split('\n')
    #         pw = lines[1][10:].strip()
    #         user = lines[0][7:].strip()
    #         return user, pw
    #
    #     path = os.getcwd()
    #     file_path = os.path.join(path, "logininfo.txt")
    #     with open(file_path, 'r') as file:
    #         file_content = file.read()
    #     username, password = getPWAndUser(file_content)
    #     file_content = []
    #     # server = 'oilgas-sql-prod.ogm.utah.gov'
    #     # database = 'UTRBDMSNET'
    #     if file_content:
    #         server = 'oilgas-sql-prod.ogm.utah.gov'
    #         username = 'USERNAME'
    #         password = 'PASSWORD'
    #         database = 'UTRBDMSNET'
    #         params = urllib.parse.quote_plus('DRIVER={SQL Server};'
    #                                          'SERVER=' + server + ';'
    #                                                               'DATABASE=' + database + ';'
    #                                                                                        'UID=' + username + ';'
    #                                                                                                            'PWD=' + password)
    #     else:
    #         params = (
    #             "Driver={SQL Server};"
    #             r"Server=CGDESKTOP\SQLEXPRESS;"
    #             "Database=UTRBDMSNET;"
    #             "Trusted_Connection = yes;")
    #     self.engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")
    #
    #
    # def sqlQueryOpen(self):
    #     pass
    #
    # def sqlQueryClose(self):

    def sqlGetCasingStrengths(self):
        path = r'C:\Work\Databases'
        apd_data_dir = os.path.join(path, 'CasingStrength.db')
        conn_db = sqlite3.connect(apd_data_dir)
        query = "Select * from CasingStrengths"
        self.casing_strength_df = pd.read_sql(query, conn_db)
        self.casing_strength_df = self.casing_strength_df.map(self.strip_if_string)
        self.casing_strength_df['CasingDiameter'] = self.casing_strength_df['CasingDiameter'].astype(float)
        self.casing_strength_df['NominalWeight'] = self.casing_strength_df['NominalWeight'].astype(float)
        self.casing_strength_df = self.casing_strength_df.drop(self.casing_strength_df.columns[0], axis=1)
        conn_db.close()

        self.addCasingStrengthData()

    def addCasingStrengthData(self):
        # self.casing_strength_df.loc[len(self.casing_strength_df)] = ['value1', 'value2', 'value3']
        columns = self.casing_strength_df.columns
        new_rows = [
            [5.5, 19, 'P-110', 10170, 13320, 'BTC', 680, 680, 0.335, 4.83, 4.705, None],
            [5.5, 23, 'P-110', 14540, 14530, 'BTC', 729, 729, 0.415, 4.67, 4.545, None],
            [5.5, 24.5, 'P-110', 11470, 13200, 'BTC', 774, 774, 0.4, 5.2, 5.075, None],
            [5.5, 20, 'P-110', 12300, 14360, 'BTC', 729, 729, 0.361, 4.778, 4.653, None],
            [5.5, 20, 'P-110', 12300, 14360, 'Wedge 441', 594, 729, 0.361, 4.778, 4.653, None],
            [5.5, 23, 'HCP-110', 16220, 16510, 'TCBC-HT', 829, 829, 0.415, 5.383, 4.545, None],
            [5.0, 18, 'P-110', 14820, 15840, 'EC Anacond', 593, 593, 0.362, 4.196, 4.151, None],
            [9.625, 40, 'HCL-80', 3870, 5750, 'GBCD', 947, 916, 0.395, 8.835, 8.679, None],
            [5, 18, 'P-110', 13470, 13940, 'Wedge 625', 531, 580, 0.362, 4.276, 4.151, None],
            [4.5, 13.5, 'P-110', 10690, 12410, 'Wedge 625', 384, 422, 0.29, 3.92, 3.795, None]
        ]
        new_df = pd.DataFrame(new_rows, columns=columns)
        self.casing_strength_df = pd.concat([self.casing_strength_df, new_df], ignore_index=True)
    def casingMainsqlCall(self):
        out_tblAPDLoc, shl, bhl = self.sqlLocation()
        out_tblAPDLoc = ma.removeDupesListOfLists(out_tblAPDLoc)
        out_tblAPDWellStrings = self.sqlRetrieveBOPE()
        self.shl, self.bhl = shl, bhl

        self.casing_lst, self.depths, self.cond_bttm, self.first_line, self.tsr_data = self.organizeTheValues(
            out_tblAPDWellStrings, out_tblAPDLoc)

        for i in range(len(self.casing_lst)):
            self.casing_lst[i][3] = int(float(self.casing_lst[i][3]))
            self.casing_lst[i][8] = str(int(float(self.casing_lst[i][8])))
            self.casing_lst[i][11] = str(int(float(self.casing_lst[i][11])))
            self.casing_lst[i].append('CEMENT')
            if len(self.casing_lst[i]) == 17:
                self.casing_lst[i][-2] = int(float(self.casing_lst[i][-2]))
        for i in range(len(self.casing_lst)):
            if len(self.casing_lst[i]) == 16:
                self.casing_mud_weights.append(self.casing_lst[i][-2])
            elif len(self.casing_lst[i]) == 17:
                self.casing_mud_weights.append(self.casing_lst[i][-3])

    def getDrilledDepths(self):
        def update_last_row(dataframe, new_value):
            # Update CasingBottom
            dataframe.loc[dataframe.index[-1], 'CasingBottom'] = np.int32(float(new_value))
            # dataframe.loc[dataframe.index[-1], 'CasingBottom'] = np.int32(float(new_value))
            # Update Interval
            previous_bottom = dataframe.loc[dataframe.index[-2], 'CasingBottom']
            # dataframe.loc[dataframe.index[-1], 'Interval'] = pd.Interval(previous_bottom, new_value, closed='right')
            dataframe.loc[dataframe.index[-1], 'Interval'] = pd.Interval(
                left=np.int64(previous_bottom),
                right=np.int64(new_value),
                closed='right'
            )
            return dataframe

        api = self.ui.well_api_val.text()
        query_drilled = f"""select cc.Feature, cc.CasingBottom
            FROM Well w 
            left join Construct c ON c.WellKey = w.PKey
            left join ConstructCasing cc on cc.ConstructKey = c.PKey
            WHERE w.WellID = '{api}' and Weight is not Null and cc.Feature != 'Hole'
            """

        try:
            self.drilled_depths = pd.read_sql_query(query_drilled, self.engine)
            self.drilled_depths = self.drilled_depths.map(self.strip_if_string)
            self.drilled_depths['CasingBottom'] = pd.to_numeric(self.drilled_depths['CasingBottom'], errors='coerce')
            self.drilled_depths.iloc[-1, self.drilled_depths.columns.get_loc('CasingBottom')] = \
                self.drilled_depths['CasingBottom'].iloc[-1] + 200
            # Drop any rows where CasingBottom is not a number
            self.drilled_depths = self.drilled_depths.dropna(subset=['CasingBottom'])
            # Sort the dataframe by CasingBottom
            self.drilled_depths = self.drilled_depths.sort_values('CasingBottom')
            # Create the intervals
            self.drilled_depths['Interval'] = pd.IntervalIndex.from_arrays(
                [0] + self.drilled_depths['CasingBottom'].tolist()[:-1], self.drilled_depths['CasingBottom'],
                closed='right')
        except IndexError:
            def getDepth(api):
                lateral_num = self.ui.lateral_name_line_edit.text()
                if lateral_num == '':
                    lateral_num = '0000'
                try:
                    query = f"""SELECT MAX(MeasuredDepth) AS MaxMeasuredDepth
                     FROM DirectionalSurveyHeader dsh
                     JOIN DirectionalSurveyData dsd ON dsh.PKey = dsd.DirectionalSurveyHeaderKey
                     WHERE dsh.APINumber = '{api}' and CitingType = 'Planned' and dsh.LateralName = '{lateral_num}'"""
                    output = float(pd.read_sql_query(query, self.engine)['MaxMeasuredDepth'].unique()[0])
                except TypeError:
                    query_prop = f"""select Proposed_Depth_MD 
                         from [dbo].[tblAPD]
                         where API_WellNo  = '{api}0000'"""
                    output = float(pd.read_sql_query(query_prop, self.engine)['Proposed_Depth_MD'].unique()[0])
                return output

            depth = float(getDepth(api))

            if depth > 0:
                self.drilled_depths = self.planned_depths
                # max_val = self.base_dx_df_drilled['MeasuredDepths'].tail(1)
                self.drilled_depths = update_last_row(self.drilled_depths, depth)
                pass

    def sqlLocation(self):
        api = self.ui.well_api_val.text()
        query = f"""SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = '{api}0000'"""
        apdNo = pd.read_sql_query(query, self.engine)['APDNo'].unique()[0]
        query = f"""select [Wh_Sec], [Wh_Twpn] , [Wh_Twpd], [Wh_RngN], [Wh_RngD], [Wh_Pm], [Wh_FtNS], [Wh_Ns], [Wh_FtEW], [Wh_EW], [Zone_Name],[Wh_Qtr],[Wh_X],[Wh_Y], [Bh_X], [Bh_Y], [Wh_Pm] from [dbo].[tblAPDLoc] where APDNO = '{apdNo}'"""

        self.loc_df = pd.read_sql_query(query, self.engine)
        self.loc_df = self.loc_df.map(self.strip_if_string)

        line = self.loc_df.to_numpy().tolist()
        line = [[str(i) for i in j] for j in line]
        shl, bhl = [line[0][-5], line[0][-4]], [line[0][-3], line[0][-2]]
        line = [i[:-4] for i in line]

        self.tsr_data_db = line
        df_test = [{'Section': i[0], 'Township': i[1], 'Township Direction': i[2], 'Range': i[3],
                    'Range Direction': i[4], 'Baseline': i[5], 'FNSL': i[6], 'FNSL Dir': i[7], 'FEWL': i[8],
                    'FEWL Dir': i[9], 'Label': i[10]} for i in line]
        self.tsr_db = pd.DataFrame(df_test,
                                   columns=['Section', 'Township', 'Township Direction', 'Range', 'Range Direction',
                                            'Baseline', 'FNSL', 'FNSL Dir', 'FEWL', 'FEWL Dir', 'Label'])

        return line, shl, bhl

    def sqlRetrieveCasingData(self):

        api = self.ui.well_api_val.text()
        query = f"""SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = '{api}0000'"""
        apdNo = pd.read_sql_query(query, self.engine)['APDNo'].unique()[0]
        query = f"""select distinct w.Csg_String, HoleDia, Dia, ToC, BoC, p.Weight, p.Grade, p.ConnectionType, Sacks, Yield, c.Weight, Max_Mud_Wt, Top_ 
        from tblAPDWellStrings w 
        join tblAPDWellCementCls c on c.APDNO = w.APDNO 
        inner join tblAPDWellStringPipe p on p.APDNO = c.APDNO 
        where c.APDNO = '{apdNo}' AND UPPER(w.Csg_String) LIKE UPPER(c.Csg_String) AND UPPER(w.Csg_String) LIKE UPPER(p.Csg_String)"""
        self.casing_df = pd.read_sql_query(query, self.engine)
        self.casing_df = self.casing_df.map(self.strip_if_string)

        self.well_nm = pd.read_sql_query(query, self.engine)['Well_Nm'].unique()[0]

    def sqlRetrieveBOPE(self):
        def editDepthDF(df):
            df = df.rename(columns={'Bot': 'CasingBottom', 'Csg_String': 'Feature'})
            df['CasingBottom'] = pd.to_numeric(df['CasingBottom'], errors='coerce')
            df = df.drop_duplicates(
                keep="first")
            df.iloc[-1, df.columns.get_loc('CasingBottom')] = df['CasingBottom'].iloc[-1] + 200
            # Drop any rows where CasingBottom is not a number
            df = df.dropna(subset=['CasingBottom'])

            # Sort the dataframe by CasingBottom
            df = df.sort_values('CasingBottom')
            # Sort the dataframe by CasingBottom

            # Create the intervals
            df['Interval'] = pd.IntervalIndex.from_arrays(
                [0] + df['CasingBottom'].tolist()[:-1],
                df['CasingBottom'],
                closed='right')
            return df

        def bope_process(query):
            proper_order = ['Cond', 'Surf', 'I1', 'Prod', 'P2', 'L1']
            df = pd.read_sql_query(query, self.engine)
            df = df.map(self.strip_if_string)
            line = df.to_numpy().tolist()
            for i in range(len(line)):
                if len(str(line[i][5])) > 4:
                    line[i][5] = str(round(float(line[i][5]), 2))
                if len(str(line[i][-4])) > 4:
                    line[i][-4] = str(round(float(line[i][-4]), 2))
            line = [[str(i) for i in j] for j in line]

            line = ma.reorderListByStringOrder(proper_order, line, 0)

            return line, df

        def getDepth(api):
            lateral_num = self.ui.lateral_name_line_edit.text()
            if lateral_num == '':
                lateral_num = '0000'
            try:
                query = f"""SELECT MAX(MeasuredDepth) AS MaxMeasuredDepth
                FROM DirectionalSurveyHeader dsh
                JOIN DirectionalSurveyData dsd ON dsh.PKey = dsd.DirectionalSurveyHeaderKey
                WHERE dsh.APINumber = '{api}' and CitingType = 'Planned' and dsh.LateralName = '{lateral_num}'"""

                output = float(pd.read_sql_query(query, self.engine)['MaxMeasuredDepth'].unique()[0])
            except TypeError:
                query_prop = f"""select Proposed_Depth_MD 
                    from [dbo].[tblAPD]
                    where API_WellNo  = '{api}0000'"""
                output = float(pd.read_sql_query(query_prop, self.engine)['Proposed_Depth_MD'].unique()[0])
            return output

        api = self.ui.well_api_val.text()
        query = f"""SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = '{api}0000'"""
        apdNo = pd.read_sql_query(query, self.engine)['APDNo'].unique()[0]
        query_depth = f"""select Proposed_Depth_MD from tblAPDLoc
            where APDNO = '{apdNo}' and Proposed_Depth_MD > 0"""
        # depth = str(pd.read_sql_query(query_depth, self.engine)['Proposed_Depth_MD'].unique()[0])
        depth = float(getDepth(api))
        query1 = f"""select distinct w.Csg_String, HoleDia, Dia, ToC, w.Bot, p.Weight, p.Grade, p.ConnectionType, Sacks, Yield, c.Weight, Max_Mud_Wt, Top_ 
        from tblAPDWellStrings w 
        join tblAPDWellCementCls c on c.APDNO = w.APDNO 
        inner join tblAPDWellStringPipe p on p.APDNO = c.APDNO 
        where c.APDNO = '{apdNo}' AND UPPER(w.Csg_String) LIKE UPPER(c.Csg_String) AND UPPER(w.Csg_String) LIKE UPPER(p.Csg_String)"""
        # self.getBetterCasingData()
        query2 = f"""select distinct w.Csg_String, HoleDia, Dia, ToC, c.BoC, p.Weight, p.Grade, p.ConnectionType, Sacks, Yield, c.Weight, Max_Mud_Wt, Top_ 
        from tblAPDWellStrings w 
        join tblAPDWellCementCls c on c.APDNO = w.APDNO 
        inner join tblAPDWellStringPipe p on p.APDNO = c.APDNO 
        where c.APDNO = '{apdNo}' AND UPPER(w.Csg_String) LIKE UPPER(c.Csg_String) AND UPPER(w.Csg_String) LIKE UPPER(p.Csg_String)"""

        query3 = f"""select distinct w.Csg_String, HoleDia, Dia, ToC, p.Bot, p.Weight, p.Grade, p.ConnectionType, Sacks, Yield, c.Weight, Max_Mud_Wt, Top_ 
        from tblAPDWellStrings w 
        join tblAPDWellCementCls c on c.APDNO = w.APDNO 
        inner join tblAPDWellStringPipe p on p.APDNO = c.APDNO 
        where c.APDNO = '{apdNo}' AND UPPER(w.Csg_String) LIKE UPPER(c.Csg_String) AND UPPER(w.Csg_String) LIKE UPPER(p.Csg_String)"""

        line1, df1 = bope_process(query1)
        line2, df2 = bope_process(query2)
        line3, df3 = bope_process(query3)
        depths1 = [i[4] for i in line1]
        depths2 = [i[4] for i in line2]
        depths3 = [i[4] for i in line3]
        for i in depths1:
            if math.isclose(float(i), depth, abs_tol=2):
                self.planned_depths = editDepthDF(df1.iloc[:, [0, 4]])
                self.casing_df = df1
                return line1

        for i in depths2:
            if math.isclose(float(i), depth, abs_tol=2):
                self.planned_depths = editDepthDF(df2.iloc[:, [0, 4]])
                self.casing_df = df2
                return line2

        for i in depths3:
            if math.isclose(float(i), depth, abs_tol=2):
                self.planned_depths = editDepthDF(df3.iloc[:, [0, 4]])
                self.casing_df = df3
                return line3
        if math.isclose(float(depths1[-1]), float(depths2[-1]), abs_tol=2) and math.isclose(float(depths1[-1]),
                                                                                            float(depths3[-1]),
                                                                                            abs_tol=2):
            self.planned_depths = editDepthDF(df1.iloc[:, [0, 4]])
            self.casing_df = df1
            return line1

    def strip_if_string(self, value):
        return value.strip() if isinstance(value, str) else value

    def sqlRetrieveWellInfo(self):
        def update_xy(row):
            if row['LocType'] == 'SURF':
                return pd.Series({'X': output['Wh_X'].iloc[0], 'Y': output['Wh_Y'].iloc[0]})
            elif row['LocType'] == 'BH':
                return pd.Series({'X': output['Bh_X'].iloc[0], 'Y': output['Bh_Y'].iloc[0]})
            else:
                return pd.Series({'X': row['X'], 'Y': row['Y']})

        def is_valid_number(x):
            return pd.notnull(x) and np.isreal(x) and x > 400000

        def findBHLSHLIfErrored():
            query = f"""select Wh_X, Wh_Y, Bh_X, Bh_Y
                from [dbo].[tblAPDLoc] 
                where APDNO = {self.apdNo} and Zone_Name = 'Proposed Depth'"""
            output = pd.read_sql_query(query, self.engine)
            return output

        lateral_num = self.ui.lateral_name_line_edit.text()
        if lateral_num == '':
            lateral_num = '0000'
        api = self.ui.well_api_val.text()
        query = f"""select County, l.X, l.Y, NorthReference, CitingType, LocType, Sec, Township, TownshipDir, Range, 
        RangeDir, PM, OperatorName FROM Well w left join Construct c ON c.WellKey = w.PKey left join loc l ON l.ConstructKey = 
        c.pkey left join [LocExt] le ON le.lockey = l.Pkey left join [dbo].[DirectionalSurveyHeader] dsh on 
        dsh.APINumber = w.WellID
                WHERE WellID = '{api}' and LocType in ('BH', 'SURF')
                and dsh.LateralName = '{lateral_num}'
                ORDER BY CitingType"""
        print(query)
        self.base_well_df = pd.read_sql_query(query, self.engine)
        self.base_well_df = self.base_well_df.map(self.strip_if_string)
        filtered_df = self.base_well_df[
            (self.base_well_df['LocType'].isin(['BH', 'SURF'])) &
            (self.base_well_df['CitingType'].isin(['Planned', 'planned', 'PLANNED']))]
        invalid_x = filtered_df[~filtered_df['X'].apply(is_valid_number)]
        invalid_y = filtered_df[~filtered_df['Y'].apply(is_valid_number)]
        invalid_rows = pd.concat([invalid_x, invalid_y]).drop_duplicates()
        if not invalid_rows.empty:
            output = findBHLSHLIfErrored()
            self.base_well_df[['X', 'Y']] = self.base_well_df.apply(update_xy, axis=1)
            self.base_well_df = self.base_well_df[self.base_well_df['X'].apply(is_valid_number) &
                                                  self.base_well_df['Y'].apply(is_valid_number)]
        print(self.base_well_df)
        self.base_well_df['Lat'], self.base_well_df['Lon'] = zip(
            *self.base_well_df.apply(lambda row: utm.to_latlon(row['X'], row['Y'], 12, 'T'), axis=1))
        try:
            self.base_well_df['CitingType'] = self.base_well_df['CitingType'].apply(lambda x: x.lower())
        except AttributeError:
            if self.base_well_df['CitingType'].unique().tolist() is None:
                print("sdfjsdkjhdsfkj")
        self.base_well_df['CitingType'] = self.base_well_df['CitingType'].replace('asdrilled', 'AsDrilled')
        self.base_well_df['CitingType'] = self.base_well_df['CitingType'].replace('planned', 'Planned')

        county = self.base_well_df['County'].unique()[0].tolist()
        sp_zone = ma.findSPZone(ma.countyDict(county))
        lat, lon = self.base_well_df['Lat'].iloc[0], self.base_well_df['Lon'].iloc[0]
        self.convergence_angle = ma.convAngleSP(sp_zone, [float(lat), float(lon)])

    def findAPDNo(self):
        api = self.ui.well_api_val.text()
        query = f"""SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = '{api}0000'"""
        self.apdNo = self.db.query_to_dataframe(query)['APDNo'].unique()[0]
        self.name_db = self.db.query_to_dataframe(query)['Well_Nm'].unique()[0]


    def findAPDNo2(self):
        api = self.ui.well_api_val.text()
        query = f"""SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = '{api}0000'"""
        # apdNo = pd.read_sql_query(query, self.engine)['APDNo'].unique()[0]
        # API = API + "0000"
        # query = 'SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = ?'
        # output_tblAPD = cursor.execute(query, API).fetchall()
        # output_tblAPD = self.fixer(output_tblAPD)[0]
        self.apdNo = pd.read_sql_query(query, self.engine)['APDNo'].unique()[0]
        self.name_db = pd.read_sql_query(query, self.engine)['Well_Nm'].unique()[0]
        print('apdno', self.apdNo)

    def retrievePlatData(self):
        path_used_db = r'C:\Work\Databases'
        apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
        conn_db = sqlite3.connect(apd_data_dir)
        cursor = conn_db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        # Print all table names
        print("Tables in the database:")
        for table in tables:
            print(f"- {table[0]}")



        # print(self.base_well_dfko)
        needed_wells = self.base_well_df[['Sec', 'Township', 'TownshipDir', 'Range', 'RangeDir', 'PM']].drop_duplicates(
            keep="first")

        needed_wells["Township"] = needed_wells["Township"].astype(float).astype(int).astype(str).astype(str)
        needed_wells["Range"] = needed_wells["Range"].astype(float).astype(int).astype(str).astype(str)
        needed_wells['Sec'] = needed_wells['Sec'].astype(str)
        query = f"""SELECT * FROM BaseData WHERE """
        conditions = []
        for _, row in needed_wells.iterrows():
            condition = f"""(SECTION = '{row['Sec']}' AND TOWNSHIP = '{row['Township']}' AND Township_D = '{row['TownshipDir']}' AND RANGE = '{row['Range']}' AND Range_D = '{row['RangeDir']}' AND Baseline = '{row['PM']}')"""
            conditions.append(condition)
        query += ' OR '.join(conditions)
        self.plat_df = pd.read_sql(query, conn_db)

        self.plat_df = self.plat_df.map(self.strip_if_string)

        self.plat_df = ma.geometryTransform(self.plat_df)

        self.plat_df, self.all_plats_adjacent = self.makeSureAllPlatsAreFoundByCheckingAdjacentPlats(conn_db, self.plat_df)

        conn_db.close()


    def sqlGetNameAPDNo(self):
        api = self.ui.well_api_val.text()
        query = f"""SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = '{api}0000'"""
        df = self.db.query_to_dataframe(query)
        # df = pd.read_sql_query(query, self.engine)
        self.apdNo = df['APDNo'].unique()[0]

        self.well_name = df['Well_Nm'].unique()[0]

    # def getAllPlatsReally(self, conn_db):
    #     def find_nearby_polygons(point, polygons, distance):
    #         # Create a buffer around the point
    #         buffer = point.buffer(distance)
    #
    #         # Find polygons that intersect with the buffer
    #         nearby = polygons[polygons.intersects(buffer)]
    #
    #         # Return the IDs of nearby polygons
    #         return nearby.index.tolist()
    #
    #     query = f"""SELECT * FROM BaseData"""
    #     all_plat_df = pd.read_sql(query, conn_db)
    #     point = self.base_dx_df['shp_pt'].tolist()[0]
    #     all_plat_df['min_distance'] = np.vectorize(ma.equationDistance)(all_plat_df['Easting'], all_plat_df['Northing'],
    #                                                                     point.x, point.y)
    #     conc_lst = all_plat_df[all_plat_df['min_distance'] < 5000]['Conc'].unique().tolist()
    #     used_concs = all_plat_df[all_plat_df['Conc'].isin(conc_lst)]
    #     used_concs_df = ma.geometryTransform(used_concs)
    #     self.plat_df = pd.concat([self.plat_df, used_concs_df], ignore_index=True).drop_duplicates(
    #         keep="first")
    #     self.plat_df = self.plat_df.map(self.strip_if_string)

    def matchPlatAndSurveyData(self):
        def find_conc(point):
            for idx, row in self.all_plats_adjacent.iterrows():
                # for idx, row in self.plat_df.iterrows():
                if row['geometry'].contains(point):
                    return row['Conc']
            return None  # Return None if no matching polygon is found

        used_conc_drilled, used_conc_planned = [], []
        self.plat_df['geometry'] = self.plat_df['geometry'].apply(lambda x: x if isinstance(x, Polygon) else None)
        self.plat_df = self.plat_df.dropna(subset=['geometry'])
        if len(self.base_dx_df_drilled) > 0:
            self.base_dx_df_drilled['Conc'] = self.base_dx_df_drilled['shp_pt'].apply(find_conc)
            self.base_dx_df_drilled, self.drilled_footages = self.testClearance(self.base_dx_df_drilled, self.plat_df)
            used_conc_drilled = self.base_dx_df_drilled['Conc'].unique().tolist()
        if len(self.base_dx_df_planned) > 0:
            self.base_dx_df_planned['Conc'] = self.base_dx_df_planned['shp_pt'].apply(find_conc)
            self.base_dx_df_planned, self.planned_footages = self.testClearance(self.base_dx_df_planned, self.plat_df)
            used_conc_planned = self.base_dx_df_planned['Conc'].unique().tolist()
        all_conc = list(set(used_conc_drilled + used_conc_planned))
        self.plat_df = self.plat_df[self.plat_df['Conc'].isin(all_conc)]

    def makeSureAllPlatsAreFoundByCheckingAdjacentPlats(self, conn_db, plat_df):
        def check_contains_any_point(polygon, points):
            return any(polygon.contains(point) for point in points)

        unique_concs = set(plat_df['Conc'].unique())
        recursive_query = f"""
        WITH RECURSIVE adjacent_plats AS (
            -- Initial set: directly adjacent plats
            SELECT DISTINCT adjacent_Conc_Name_2, 1 as level
            FROM Adjacent
            WHERE Conc IN ({','.join(['?'] * len(unique_concs))})

            UNION

            -- Recursive part: find adjacent plats of adjacent plats
            SELECT DISTINCT a.adjacent_Conc_Name_2, ap.level + 1
            FROM Adjacent a
            JOIN adjacent_plats ap ON a.Conc = ap.adjacent_Conc_Name_2
            WHERE ap.level < 3
        )
        SELECT DISTINCT adjacent_Conc_Name_2 FROM adjacent_plats
        """

        # Execute the query
        df_adjacent_plats = pd.read_sql(recursive_query, conn_db, params=tuple(unique_concs))

        quoted_values = [f"'{value}'" for value in self.plat_df['Conc'].unique()]
        values_string = ', '.join(quoted_values)
        df_adjacent_plats = pd.read_sql(f"select * from Adjacent where Conc2 in ({values_string})", conn_db)[
            'adjacent_Conc_Name_2']

        quoted_values_2 = [f"'{value}'" for value in df_adjacent_plats.unique()]
        quoted_values_2 = list(set(quoted_values_2))
        values_string_2 = ', '.join(quoted_values_2)
        values_string_2 += values_string

        df_adjacent_plats2 = pd.read_sql(f"select * from Adjacent where Conc2 in ({values_string_2})", conn_db)[
            'adjacent_Conc_Name_2']
        quoted_values_3 = [f"'{value}'" for value in df_adjacent_plats2.unique()]
        quoted_values_3 = list(set(quoted_values_3))
        values_string_3 = ', '.join(quoted_values_3)
        values_string_3 += values_string
        values_string_2 = values_string_3

        query = f"select * from BaseData where Conc in ({values_string_2})"
        df_adjacent_plats_loc_data = pd.read_sql(query, conn_db)
        df_adjacent_plats_loc_data = ma.geometryTransform(df_adjacent_plats_loc_data)
        point_list = self.base_dx_df['shp_pt'].tolist()

        # Apply the check to each polygon in df_adjacent_plats_loc_data
        df_adjacent_plats_loc_data['contains_point'] = df_adjacent_plats_loc_data['geometry'].apply(
            lambda poly: check_contains_any_point(poly, point_list))

        # Filter the dataframe to keep only polygons that contain at least one point
        result = df_adjacent_plats_loc_data[df_adjacent_plats_loc_data['contains_point']]
        result = result.drop('contains_point', axis=1)
        all_plats_adjacent = pd.concat([plat_df, df_adjacent_plats_loc_data],
                                            ignore_index=True).drop_duplicates(
            keep="first")
        plat_df = pd.concat([plat_df, result], ignore_index=True).drop_duplicates(
            keep="first")
        return plat_df, all_plats_adjacent
        # lst = self.plat_df['geometry'].values.tolist()
        # sql_data = [list(i.exterior.coords) for i in lst]

    def sqlGetTops(self, api):
        try:
            sql_query = f"""select wellid, rf.FormationName, cp.PerfTop, cp.PerfBottom
                from well w join construct c on w.PKey = c.WellKey  
                join ConstructPerforation cp on c.PKey = cp.ConstructKey
                join RefFormation rf on cp.FormationKey = rf.PKey 
                where wellid = '{api}' and PerfTop != ''"""
            tops = self.db.query_to_dataframe(sql_query)

            # tops = pd.read_sql_query(sql_query, self.engine)
            tops = tops.map(self.strip_if_string)
            perf_top = tops['PerfTop'].values.tolist()[0]
            perf_bottom = tops['PerfBottom'].values.tolist()[0]
            self.perf_mods = [float(perf_top), float(perf_bottom)]
        except IndexError:
            self.perf_mods = [0, 0]

    def sqlRetrieveSurvey(self):
        self.plat_north_ref = 't'
        api = self.ui.well_api_val.text()
        lateral_num = self.ui.lateral_name_line_edit.text()
        if lateral_num == '':
            lateral_num = '0000'
        # query = f"""SELECT SurfaceLatLongDatum FROM DirectionalSurveyHeader dsh"""
        # test = self.db.query_to_dataframe(query)

        query = f"""SELECT MeasuredDepth, Inclination, Azimuth, CitingType, dsd.X, dsd.Y, dsh.SurveySurfaceElevation, dsh.SurfaceLatitude, dsh.SurfaceLongitude
                FROM DirectionalSurveyHeader dsh
                JOIN DirectionalSurveyData dsd on dsd.DirectionalSurveyHeaderKey = dsh.Pkey
                WHERE dsh.APINumber = '{api}' and dsh.LateralName = '{lateral_num}' order by MeasuredDepth"""
        self.base_dx_df = self.db.query_to_dataframe(query)

        # self.base_dx_df = pd.read_sql_query(query, self.engine)
        self.base_dx_df = self.base_dx_df.map(self.strip_if_string)
        self.base_dx_df = self.base_dx_df.sort_values(by=['CitingType', 'MeasuredDepth'])
        self.well_elevation = self.base_dx_df['SurveySurfaceElevation'].iloc[0]
        self.base_dx_df.drop('SurveySurfaceElevation', axis=1)
        self.base_dx_df['CitingType'] = self.base_dx_df['CitingType'].str.lower().replace(
            {'asdrilled': 'AsDrilled', 'planned': 'Planned'})
        self.base_dx_df = self.base_dx_df.rename(columns={'X': 'Easting', 'Y': 'Northing'})
        values = self.base_dx_df[['Easting', 'Northing']].values.tolist()
        values = ma.remove_duplicates_preserve_order(values)

    def processDirectionalSurveys2(self, north_ref, df_referenced, utm_v2, stepped_boo):
        def findKopAndLP(df_kop):
            def landing_check(inc, dls):
                if math.degrees(inc) > 85 and dls < 1.0:
                    return True
                return False

            header_foo = we.survey.SurveyHeader(azi_reference=returnSpelledNorthRef(north_ref.lower()), deg=False,
                                                convergence=math.radians(calc['convergence']))
            survey_foo = we.survey.Survey(md=df_referenced['MeasuredDepth'],
                                          inc=df_referenced['Inclination'],
                                          azi=df_referenced['Azimuth'], start_nev=start_nev, deg=False,
                                          header=header_foo, error_model='ISCWSA MWD Rev4').interpolate_survey(step=10)

            outputs2 = {
                'MeasuredDepth': survey_foo.md,
                'Inclination': survey_foo.inc_rad,
                'Azimuth': survey_foo.azi_true_rad,
                'DogLegSeverity': survey_foo.dls}

            df = pd.DataFrame(outputs2)
            df['KOP'] = df['DogLegSeverity'].apply(lambda x: x > 1.5)
            df['LP'] = df.apply(lambda row: landing_check(row['Inclination'], row['DogLegSeverity']), axis=1)

            # Create a DataFrame for KOP
            kop_row = df[df['KOP'] == True][['MeasuredDepth', 'Inclination', 'Azimuth']].iloc[[0]]
            kop_row['Point'] = 'KOP'  # Add a column to identify the point

            # Create a DataFrame for LP
            lp_row = df[df['LP'] == True][['MeasuredDepth', 'Inclination', 'Azimuth']].iloc[[0]]
            lp_row['Point'] = 'LP'  # Add a column to identify the point

            # Combine the two DataFrames
            result_df = pd.concat([kop_row, lp_row], ignore_index=True)

            return result_df

        def returnSpelledNorthRef(val):
            if val.lower() == 't':
                return 'true'
            elif val.lower() == 'g':
                return 'grid'

        def solveUTM(md, inc, azi, lat1, lon1):
            lst = [[lat1, lon1]]
            geod = Geod(ellps='WGS84')
            for i in range(len(md) - 1):
                d_z, d_x, d_y = min_curve.delta_z[i + 1], min_curve.delta_x[i + 1], min_curve.delta_y[i + 1]
                delta_x_angle = 90 if d_x >= 0 else 270
                delta_y_angle = 0 if d_y >= 0 else 180
                lon_x, lat_y, back_azimuth = geod.fwd(abs(lon1) * -1, lat1, delta_x_angle,
                                                      abs(d_x) * 0.3048)
                lon1, lat1, back_azimuth = geod.fwd(abs(lon_x) * -1, lat_y, delta_y_angle,
                                                    abs(d_y) * 0.3048)
                lst.append([lat1, lon1])

            utm_v = [utm.from_latlon(i[0], i[1])[:2] for i in lst]

            utm_v = [[int(round(j, 0)) for j in i] for i in utm_v]

            return np.array(utm_v)

        def toolfaceSolve():
            vectors = survey_used.vec_nev
            pos_nev = survey_used.pos_nev
            tool_face = []
            for i in range(len(pos_nev) - 1):
                tf = we.utils.get_toolface(pos1=pos_nev[i], pos2=pos_nev[i + 1], vec1=vectors[i])
                tool_face.append(tf)
            tool_face = [math.degrees(i) for i in tool_face]
            tool_face.append(tool_face[-1])
            tool_face = np.array(tool_face)
            return tool_face

        columns = ['MeasuredDepth', 'Inclination', 'Azimuth']

        lat, lon = utm.to_latlon(utm_v2[0], utm_v2[1], 12, 'T')
        calculator = we.survey.SurveyParameters('EPSG:32612')

        calc = calculator.get_factors_from_x_y(x=utm_v2[0], y=utm_v2[1])
        start_nev = np.array([utm_v2[0] / 0.3048, utm_v2[1] / 0.3048, 0])
        conv_angle = calc['convergence']
        time_start = time.perf_counter()
        header_foo = we.survey.SurveyHeader(azi_reference=returnSpelledNorthRef(north_ref.lower()), deg=False,
                                            convergence=math.radians(conv_angle))
        init_md = df_referenced['MeasuredDepth'].values.tolist()
        kop_lp = findKopAndLP(df_referenced)
        init_md = init_md + kop_lp['MeasuredDepth'].values.tolist()
        df_referenced = pd.concat([df_referenced, kop_lp], ignore_index=True).sort_values('MeasuredDepth').reset_index(
            drop=True)

        if stepped_boo:
            if self.ui.stepped_check_box.isChecked():
                try:
                    steps = int(float(self.ui.step_box.text()))
                except ValueError as e:
                    steps = 10
            else:
                steps = 10
            survey_used = we.survey.Survey(md=df_referenced['MeasuredDepth'],
                                           inc=df_referenced['Inclination'],
                                           azi=df_referenced['Azimuth'], start_nev=start_nev, deg=False,
                                           header=header_foo, error_model='ISCWSA MWD Rev4').interpolate_survey(
                step=steps)
        else:
            survey_used = we.survey.Survey(md=df_referenced['MeasuredDepth'],
                                           inc=df_referenced['Inclination'],
                                           azi=df_referenced['Azimuth'], start_nev=start_nev, deg=False,
                                           header=header_foo,
                                           error_model='ISCWSA MWD Rev4', )  # .interpolate_survey(step=1)

        min_curve = we.utils.MinCurve(md=df_referenced['MeasuredDepth'],
                                      inc=df_referenced['Inclination'],
                                      azi=df_referenced['Azimuth'], unit='feet')
        utm_vals = solveUTM(df_referenced['MeasuredDepth'],
                            df_referenced['Inclination'],
                            df_referenced['Azimuth'], lat, lon)
        easting, northing = utm_vals.T
        tool_face = toolfaceSolve()
        # Get the last survey point
        last_point = survey_used.survey_deg[-1]
        # Extract the proposed azimuth (last survey point's azimuth)
        proposed_azimuth = last_point[2]  # Azimuth is the third element

        outputs = {
            'MeasuredDepth': survey_used.md,
            'Inclination': survey_used.inc_deg,
            'Azimuth': survey_used.azi_true_deg,
            'TVD': survey_used.tvd,
            'RatioFactor': min_curve.rf,
            'N Offset': survey_used.y,
            'E Offset': survey_used.x,
            'ToolFace': tool_face,
            'Vertical Section': survey_used.vertical_section,
            'Easting': easting,
            'Northing': northing,
            'DeltaZ': min_curve.delta_z,
            'DeltaY': min_curve.delta_y,
            'DeltaX': min_curve.delta_x,
            'DeltaMD': min_curve.delta_md,
            'DogLegSeverity': min_curve.dls,
            'BuildRadius': survey_used.radius,
            'BuildRate': survey_used.build_rate,
            'TurnRate': survey_used.turn_rate}
        df = pd.DataFrame(outputs)

        columns_to_round = ['MeasuredDepth', 'Inclination', 'Azimuth', 'TVD', 'N Offset', 'E Offset',
                            'Vertical Section', 'DeltaZ', 'DeltaY', 'DeltaX', 'DeltaMD']
        df[columns_to_round] = df[columns_to_round].round(2)
        df = df.reset_index(drop=True)

        if self.ui.stepped_check_box.isChecked():
            pass
        else:
            df = df[df['MeasuredDepth'].isin(init_md)].reset_index(drop=True)
        return df, kop_lp, conv_angle, proposed_azimuth

    def WCRGetDXData(self):
        def find_conc(point):
            for idx, row in self.all_plats_adjacent.iterrows():
                # for idx, row in self.plat_df.iterrows():
                if row['geometry'].contains(point):
                    return row['Conc']
            return None  # Return None if no matching polygon is found

        self.plat_north_ref = 't'
        api = self.ui.well_api_val.text()
        try:

            sql_query = f"""select [Top], Bottom, [Perf Date]
                from well w 
				join construct c on w.PKey = c.WellKey  
                join [dbo].[vwDM_ConstructPerf] cp on c.PKey = cp.PKey
                where wellid = {api} and [Zone Type] = 'Perforations'"""
            tops = self.db.query_to_dataframe(sql_query)

            # tops = pd.read_sql_query(sql_query, self.engine)
            tops = tops.map(self.strip_if_string)
            perf_top = tops['Top'].values.tolist()[0]
            perf_bottom = tops['Bottom'].values.tolist()[0]
            perf_mods = [float(perf_top), float(perf_bottom)]
            perf_date = tops['Perf Date'].iloc[0]
        except IndexError:
            perf_mods = [0, 0]
            perf_date = "1/1/1900"
        lateral_num = self.ui.lateral_name_line_edit.text()
        if lateral_num == '':
            lateral_num = '0000'
        query = f"""SELECT MeasuredDepth, Inclination, Azimuth, CitingType, dsd.X, dsd.Y, NorthReference, dsh.SurveySurfaceElevation 
                FROM DirectionalSurveyHeader dsh
                JOIN DirectionalSurveyData dsd on dsd.DirectionalSurveyHeaderKey = dsh.Pkey
                WHERE dsh.APINumber = '{api}'and CitingType = 'AsDrilled' and dsh.LateralName = '{lateral_num}' order by MeasuredDepth"""
        # wcr_df = pd.read_sql_query(query, self.engine)
        wcr_df = self.db.query_to_dataframe(query)

        wcr_df = wcr_df.map(self.strip_if_string)
        wcr_df = wcr_df.sort_values(by=['CitingType', 'MeasuredDepth'])
        wcr_df['CitingType'] = wcr_df['CitingType'].str.lower().replace(
            {'asdrilled': 'AsDrilled', 'planned': 'Planned'})
        wcr_df = wcr_df[wcr_df['CitingType'] != 'Planned']
        wcr_df = wcr_df.rename(columns={'X': 'Easting', 'Y': 'Northing'})
        north_ref = wcr_df['NorthReference'].iloc[0]
        for i in perf_mods:
            wcr_df = ma.insert_row_at_md(wcr_df, i)

        wcr_df = self.check_and_insert_zero_md(wcr_df)
        drilled_depths = self.getDrilledDepthsWCR()
        wcr_df['shp_pt'] = wcr_df.apply(lambda row: Point(row['Easting'], row['Northing']), axis=1)

        drl_df = SurveyProcess(df_referenced=wcr_df, drilled_depths=drilled_depths, elevation=self.well_elevation, citing_type='AsDrilled', coords_type='utm')
        output_df_g, kop_g = (drl_df.df_g, drl_df.kop_g)
        output_df_t, kop_t = (drl_df.df_t, drl_df.kop_t)

        # if north_ref[0].lower() == 'g':
        #     output_df, kop = (drl_df.df_g, drl_df.kop_g)
        # elif north_ref[0].lower() == 't':
        #     output_df, kop = (drl_df.df_t, drl_df.kop_t)

        if int(float(kop_g[kop_g['Point'] == 'KOP']['MeasuredDepth'].iloc[0])) == 0:
            new_val = math.floor(len(output_df_g) * (2 / 3))
            new_output = output_df_g.iloc[new_val]
            kop_g.loc[0, 'MeasuredDepth'] = new_output['MeasuredDepth']
            kop_g.loc[0, 'Inclination'] = new_output['Inclination']
            kop_g.loc[0, 'Azimuth'] = new_output['Azimuth']

        if int(float(kop_t[kop_t['Point'] == 'KOP']['MeasuredDepth'].iloc[0])) == 0:
            new_val = math.floor(len(output_df_t) * (2 / 3))
            new_output = output_df_t.iloc[new_val]
            kop_t.loc[0, 'MeasuredDepth'] = new_output['MeasuredDepth']
            kop_t.loc[0, 'Inclination'] = new_output['Inclination']
            kop_t.loc[0, 'Azimuth'] = new_output['Azimuth']

        plat_df_wcr, plat_adjacents = self.WCRGetPlatData()
        plat_df_wcr['geometry'] = plat_df_wcr['geometry'].apply(lambda x: x if isinstance(x, Polygon) else None)
        plat_df_wcr = plat_df_wcr.dropna(subset=['geometry'])
        clear_df_g = ClearanceProcess(output_df_g, plat_df_wcr, plat_adjacents)
        clear_df_t = ClearanceProcess(output_df_t, plat_df_wcr, plat_adjacents)

        output_df_g = clear_df_g.clearance_data
        output_df_t = clear_df_t.clearance_data

        used_conc_drilled_g = output_df_g['Conc'].unique().tolist()
        used_conc_drilled_t = output_df_t['Conc'].unique().tolist()

        all_conc = list(set(used_conc_drilled_g + used_conc_drilled_t))
        plat_df_wcr = plat_df_wcr[plat_df_wcr['Conc'].isin(all_conc)]
        return {'grid': output_df_g, 'true': output_df_t}, perf_mods, {'grid': kop_g, 'true': kop_t}, north_ref, plat_df_wcr, perf_date

    def WCRGetPlatData(self):
        path_used_db = r'C:\Work\Databases'
        apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
        conn_db = sqlite3.connect(apd_data_dir)
        needed_wells = self.base_well_df[['Sec', 'Township', 'TownshipDir', 'Range', 'RangeDir', 'PM']].drop_duplicates(
            keep="first")
        needed_wells["Township"] = needed_wells["Township"].astype(float).astype(int).astype(str).astype(str)
        needed_wells["Range"] = needed_wells["Range"].astype(float).astype(int).astype(str).astype(str)
        needed_wells['Sec'] = needed_wells['Sec'].astype(str)
        query = f"""SELECT * FROM BaseData WHERE """
        conditions = []
        for _, row in needed_wells.iterrows():
            condition = f"""(SECTION = '{row['Sec']}' AND TOWNSHIP = '{row['Township']}' AND Township_D = '{row['TownshipDir']}' AND RANGE = '{row['Range']}' AND Range_D = '{row['RangeDir']}' AND Baseline = '{row['PM']}')"""
            conditions.append(condition)
        query += ' OR '.join(conditions)
        plat_df_wcr = pd.read_sql(query, conn_db)
        plat_df_wcr = plat_df_wcr.map(self.strip_if_string)
        plat_df_wcr = ma.geometryTransform(plat_df_wcr)
        plat_df_wcr, plat_adjacents = self.makeSureAllPlatsAreFoundByCheckingAdjacentPlats(conn_db, plat_df_wcr)

        conn_db.close()
        return plat_df_wcr, plat_adjacents
    def WCRGetMiscData(self):
        api = self.ui.well_api_val.text()
        query = f"""SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = '{api}0000'"""
        # apdNo = pd.read_sql_query(query, self.engine)['APDNo'].unique()[0]
        apdNo = self.db.query_to_dataframe(query)['APDNo'].unique()[0]

        query = f"""select [Wh_Sec], [Wh_Twpn] , [Wh_Twpd], [Wh_RngN], [Wh_RngD], [Wh_Pm], [Wh_FtNS], [Wh_Ns], [Wh_FtEW], [Wh_EW], [Zone_Name],[Wh_Qtr],[Wh_X],[Wh_Y], [Bh_X], [Bh_Y], [Wh_Pm] from [dbo].[tblAPDLoc] where APDNO = '{apdNo}'"""
        wcr_loc_df = pd.read_sql_query(query, self.engine)
        # wcr_loc_df = self.db.query_to_dataframe(query)

        wcr_loc_df = wcr_loc_df.map(self.strip_if_string)
        line = wcr_loc_df.to_numpy().tolist()
        line = [[str(i) for i in j] for j in line]
        line = [i[:-4] for i in line]
        df_test = [{'Section': i[0], 'Township': i[1], 'Township Direction': i[2], 'Range': i[3],
                    'Range Direction': i[4], 'Baseline': i[5], 'FNSL': i[6], 'FNSL Dir': i[7], 'FEWL': i[8],
                    'FEWL Dir': i[9], 'Label': i[10]} for i in line]
        wcr_tsr_db = pd.DataFrame(df_test,
                                  columns=['Section', 'Township', 'Township Direction', 'Range', 'Range Direction',
                                           'Baseline', 'FNSL', 'FNSL Dir', 'FEWL', 'FEWL Dir', 'Label'])
        return wcr_tsr_db

    def wcr_sundries_sql(self):
        query =f"""select APINO, TypeSubmission, SubmitDate, Operations
                    from tblAPDSundry
        where APINO = '{self.ui.well_api_val.text()}0000'
        order by SubmitDate"""
        df = self.db.query_to_dataframe(query)
        df['APINO'] = df['APINO'].astype(str).apply(lambda row: row[:10])
        df['SubmitDate'] = df['SubmitDate'].astype(str).apply(lambda row: row[:10])
        return df

    def wcr_logs_sql(self):
        query =f"""select w.WellID, cl.LogType, cl.ReceivedDate
            from well w
            inner join construct c on w.pkey=c.WellKey
            inner join ConstructLog cl on cl.ConstructKey = c.PKey
            where w.WellID = '{self.ui.well_api_val.text()}'
            order by cl.ReceivedDate"""
        df = self.db.query_to_dataframe(query)
        return df


    def getWCRWellInfo(self):
        lateral_num = self.ui.lateral_name_line_edit.text()
        if lateral_num == '':
            lateral_num = '0000'
        query = f"""select wi.*, dsh.OperatorName, dsh.WellNameNumber, dsh.APINumber, LateralName as ConstructKey
        from tblAPDWCRWellInfo wi
        join [dbo].tblAPD ta on wi.APDNo = ta.APDNo
        JOIN DirectionalSurveyHeader dsh ON LEFT(ta.API_WellNo, 10) = dsh.APINumber where ta.APDno = {self.apdNo} and dsh.LateralName = '{lateral_num}'"""
        # wcr_info = pd.read_sql_query(query, self.engine)
        wcr_info = self.db.query_to_dataframe(query)

        wcr_info = wcr_info.drop_duplicates(keep="first")
        return wcr_info

    def getWCRCasingInfo(self):
        query = f"""select Feature, [Top], Bottom, Diam, [Weight], Grade,
       [Connection Type], [Cement Top], [Cement Bottom], [Cement Type],
       Sacks, Yield, [Cement Weight]
        from well w
        inner join construct c on w.pkey=c.WellKey
        inner join vwDM_ConstructCasingCement vw on c.PKey = vw.PKey
        WHERE w.WellID = {self.ui.well_api_val.text()} and [Feature] is not Null"""
        custom_order = ['Hole', 'Surface Casing', 'Intermediate Casing', 'Production Casing', 'Production Casing 2',
                        'Tubing']
        # wcr_casing = pd.read_sql_query(query, self.engine)
        wcr_casing = self.db.query_to_dataframe(query)

        wcr_casing = wcr_casing[wcr_casing['Feature'].isin(custom_order)]
        wcr_casing = wcr_casing.drop_duplicates(keep="first")
        wcr_casing['Feature'] = pd.Categorical(wcr_casing['Feature'], categories=custom_order, ordered=True)
        # Then sort by both Feature and bottom
        wcr_casing = wcr_casing.sort_values(['Feature', 'Bottom']).reset_index(drop=True)

        return wcr_casing

    def getWCRPersonalDatabaseUpdate(self):
        lateral_num = self.ui.lateral_name_line_edit.text()
        if lateral_num == '':
            lateral_num = '0000'
        query = f"""select wi.SundryNo, dsh.OperatorName, dsh.WellNameNumber, dsh.APINumber, dsh.LateralName as ConstructKey, tas.SubmitDate
        from tblAPDWCRWellInfo wi
        join [dbo].tblAPD ta on wi.APDNo = ta.APDNo
        join [dbo].[tblAPDSundry] tas on ta.API_WellNo = tas.APINO
        JOIN DirectionalSurveyHeader dsh ON LEFT(ta.API_WellNo, 10) = dsh.APINumber where ta.APDno = {self.apdNo} and dsh.LateralName = '{lateral_num}'
        order BY tas.SubmitDate"""
        wcr_info = self.db.query_to_dataframe(query)

        wcr_info = wcr_info.drop_duplicates(keep="first")
        wcr_info = wcr_info.tail(1)
        return wcr_info
    def get_wcr_oil_gravity(self):
        lateral_num = self.ui.lateral_name_line_edit.text()
        if lateral_num == '':
            lateral_num = '0000'
        query = f"""select wi.SundryNo, dsh.OperatorName, dsh.WellNameNumber, dsh.APINumber, dsh.LateralName as ConstructKey, tas.SubmitDate
            from tblAPDWCRWellInfo wi
            join [dbo].tblAPD ta on wi.APDNo = ta.APDNo
            join [dbo].[tblAPDSundry] tas on ta.API_WellNo = tas.APINO
            JOIN DirectionalSurveyHeader dsh ON LEFT(ta.API_WellNo, 10) = dsh.APINumber where ta.APDno = {self.apdNo} and dsh.LateralName = '{lateral_num}'
            order BY tas.SubmitDate"""
    def getDrilledDepthsWCR(self):
        def update_last_row(dataframe, new_value):
            # Update CasingBottom
            # dataframe.loc[dataframe.index[-1], 'CasingBottom'] = new_value
            dataframe.loc[dataframe.index[-1], 'CasingBottom'] = np.int32(float(new_value))


            # Update Interval
            previous_bottom = dataframe.loc[dataframe.index[-2], 'CasingBottom']
            # dataframe.loc[dataframe.index[-1], 'Interval'] = pd.Interval(previous_bottom, new_value, closed='right')
            # dataframe.loc[dataframe.index[-1], 'Interval'] = pd.Interval(left=float(previous_bottom),right=float(new_value), closed='left')
            dataframe.loc[dataframe.index[-1], 'Interval'] = pd.Interval(
                left=np.int64(previous_bottom),
                right=np.int64(new_value),
                closed='left'
            )
            return dataframe

        api = self.ui.well_api_val.text()
        query_drilled = f"""select cc.Feature, cc.CasingBottom
               FROM Well w 
               left join Construct c ON c.WellKey = w.PKey
               left join ConstructCasing cc on cc.ConstructKey = c.PKey
               WHERE w.WellID = '{api}' and Weight is not Null and cc.Feature != 'Hole'
               """
        try:
            drilled_depths = pd.read_sql_query(query_drilled, self.engine)
            drilled_depths = drilled_depths.map(self.strip_if_string)
            drilled_depths['CasingBottom'] = pd.to_numeric(drilled_depths['CasingBottom'], errors='coerce')
            drilled_depths.iloc[-1, drilled_depths.columns.get_loc('CasingBottom')] = \
                drilled_depths['CasingBottom'].iloc[-1] + 200
            # Drop any rows where CasingBottom is not a number
            drilled_depths = drilled_depths.dropna(subset=['CasingBottom'])
            # Sort the dataframe by CasingBottom
            drilled_depths = drilled_depths.sort_values('CasingBottom')
            # Create the intervals
            drilled_depths['Interval'] = pd.IntervalIndex.from_arrays(
                [0] + drilled_depths['CasingBottom'].tolist()[:-1], drilled_depths['CasingBottom'],
                closed='right')
            return drilled_depths
        except IndexError:
            def getDepth(api):
                lateral_num = self.ui.lateral_name_line_edit.text()
                if lateral_num == '':
                    lateral_num = '0000'
                try:
                    query = f"""SELECT MAX(MeasuredDepth) AS MaxMeasuredDepth
                        FROM DirectionalSurveyHeader dsh
                        JOIN DirectionalSurveyData dsd ON dsh.PKey = dsd.DirectionalSurveyHeaderKey
                        WHERE dsh.APINumber = '{api}' and CitingType = 'Planned' and dsh.LateralName = '{lateral_num}'"""
                    output = float(pd.read_sql_query(query, self.engine)['MaxMeasuredDepth'].unique()[0])
                except TypeError:
                    query_prop = f"""select Proposed_Depth_MD 
                            from [dbo].[tblAPD]
                            where API_WellNo  = '{api}0000'"""
                    output = float(pd.read_sql_query(query_prop, self.engine)['Proposed_Depth_MD'].unique()[0])
                return output

            depth = float(getDepth(api))

            if depth > 0:
                drilled_depths = self.planned_depths
                drilled_depths = update_last_row(drilled_depths, depth)
                return drilled_depths
    def convert_casing_names(self, df, column_name):
        casing_conversion_reversed = {
            'Surface Casing': 'Surf',
            'Intermediate Casing': 'I1',
            'Hole': 'Open',
            'Production Casing': 'Prod',
            'Production Casing 2': 'P2',
            'Tubing': 'T1'
        }
        return df[column_name].map(casing_conversion_reversed).fillna(df[column_name])
    def getBetterCasingData(self):
        query = f"""select Feature, [Top], Bottom, Diam, [Weight], Grade,
        [Connection Type], [Cement Top], [Cement Bottom], [Cement Type],
        Sacks, Yield, [Cement Weight]
         from well w
         inner join construct c on w.pkey=c.WellKey
         inner join vwDM_ConstructCasingCement vw on c.PKey = vw.PKey
         WHERE w.WellID = '4301354305' AND [Feature] IS NOT NULL 
         AND [Feature] != 'Hole'"""
        # custom_order = ['Hole', 'Surface Casing', 'Intermediate Casing', 'Production Casing', 'Production Casing 2',
        #                 'Tubing']
        # wcr_casing = pd.read_sql_query(query, self.engine)
        wcr_casing = self.db.query_to_dataframe(query)

        # wcr_casing = wcr_casing[wcr_casing['Feature'].isin(custom_order)]
        # wcr_casing = wcr_casing.drop_duplicates(keep="first")
        # wcr_casing['Feature'] = pd.Categorical(wcr_casing['Feature'], categories=custom_order, ordered=True)

        query1 = f"""select distinct w.Csg_String, HoleDia, Dia, ToC, w.Bot, p.Weight, p.Grade, p.ConnectionType, Sacks, Yield, c.Weight, Max_Mud_Wt, Top_ 
        from tblAPDWellStrings w 
        join tblAPDWellCementCls c on c.APDNO = w.APDNO 
        inner join tblAPDWellStringPipe p on p.APDNO = c.APDNO 
        where c.APDNO = '14843' AND UPPER(w.Csg_String) LIKE UPPER(c.Csg_String) AND UPPER(w.Csg_String) LIKE UPPER(p.Csg_String)"""
        # wcr_casing2 = pd.read_sql_query(query1, self.engine)
        wcr_casing2 = self.db.query_to_dataframe(query1)

        wcr_casing['Feature'] = self.convert_casing_names(wcr_casing, 'Feature')

        self.merge_casing_data(wcr_casing, wcr_casing2)

    def merge_casing_data(self, df1, df2):
        # Convert Csg_String to Feature in df2 using our conversion dictionary
        column_mapping = {
            'Csg_String': 'Feature',
            'HoleDia': 'Top',  # Adjust if this isn't correct - example mapping
            'Dia': 'Diam',
            'ToC': 'Cement Top',
            'Bot': 'Cement Bottom',
            'Weight': 'Weight',
            'Grade': 'Grade',
            'ConnectionType': 'Connection Type',
            'Sacks': 'Sacks',
            'Yield': 'Yield',
            'Weight': 'Cement Weight',  # assuming this column is for cement
            'Max_Mud_Wt': None,  # Drop if not relevant
            'Top_': 'Top'
        }

        # Rename and align df2 to match df1
        df2_renamed = df2.rename(columns=column_mapping)

        # Drop columns in df2 that do not exist in df1
        df2_renamed = df2_renamed[df1.columns]

        # Replace values in df1 with df2_renamed wherever df1 has NaN or 0 (based on your data logic)
        # Here I assume the "0" value can be replaced as it may represent missing/invalid data
        df_combined = df1.copy()

        for col in df_combined.columns:
            # Replace 0 or NaN values in df1 with corresponding values from df2
            mask = (df_combined[col] == 0) | df_combined[col].isna()
            df_combined.loc[mask, col] = df2_renamed.loc[mask, col]

        # Optionally, we can add columns from df2 that are not in df1
        additional_cols = df2_renamed.columns.difference(df1.columns)
        df_combined = pd.concat([df_combined, df2_renamed[additional_cols]], axis=1)

        # Display the combined dataframe
