import sqlite3
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
import os


class TownShipAndRangeProcess:
    def __init__(self, api, lateral, db_process, survey_dict, location_db):
        def setup_db():
            path_used_db = r'C:\Work\Databases'
            apd_data_dir = os.path.join(path_used_db, 'location_data.db')
            return sqlite3.connect(apd_data_dir)

        # location_db = setup_db()
        loc_df, shl, bhl = self.retrieve_sql_location_data(api, lateral, db_process)

        plat_df = self.find_plats_data2(data=survey_dict, conn_db=location_db)
        # grouped_df = self.find_relative_data(conn_db=location_db, plat_df=plat_df)
        self.plat_df = plat_df
        self.loc_df = loc_df

    def find_relative_data(self, conn_db, plat_df):
        used_concs = tuple(plat_df['Conc'].unique().tolist())
        query = f"select * from section_relative"
        output = pd.read_sql(query, conn_db).drop_duplicates(keep="first")
        output['Conc'] = output['Conc'].apply(lambda row: row[:9])
        output = output[output['Conc'].isin(used_concs)]
        grouped = output.groupby(['Conc', 'Version'])
        return grouped

    def find_plats_data2(self, data, conn_db):

        def process_input_data(data):
            """
            Return a DataFrame from either a dict of data or an existing DataFrame.
            """
            if isinstance(data, dict):
                combined = []
                for obj in data.values():
                    combined.append(obj.true_dx)
                    combined.append(obj.grid_dx)
                return pd.concat(combined, ignore_index=True).drop_duplicates(keep="first")
            elif isinstance(data, pd.DataFrame):
                return data
            return pd.DataFrame()

        def read_base_data_by_bbox(conn, bbox, buffer_dist=1000):
            """
            Run a bounding box query on BaseData in the database.
            """

            query = f"""
                SELECT *
                FROM BaseData
                WHERE Easting >= {bbox[0] - buffer_dist}
                  AND Easting <= {bbox[2] + buffer_dist}
                  AND Northing >= {bbox[1] - buffer_dist}
                  AND Northing <= {bbox[3] + buffer_dist}
            """
            return pd.read_sql(query, conn)

        def read_base_data_by_conc(conn, conc_values):
            """
            Run a 'Conc in' query on BaseData for a given list of conc_values.
            """
            conc_str = ', '.join(f"'{c}'" for c in conc_values)
            query = f"SELECT * FROM BaseData WHERE Conc IN ({conc_str})"
            return pd.read_sql(query, conn)

        def get_points_bbox(points_series):
            """
            Calculate the bounding box of a pandas Series of Shapely Points.
            Returns (minx, miny, maxx, maxy).
            """
            coords = [(pt.x, pt.y) for pt in points_series]
            x_coords, y_coords = zip(*coords)
            return min(x_coords), min(y_coords), max(x_coords), max(y_coords)

        def geo_transform(df):

            polygons = (df.groupby('Conc')
                        .apply(lambda x: Polygon(zip(x['Easting'], x['Northing'])))
                        .reset_index()
                        .rename(columns={0: 'geometry'}))

            # Add label transformation
            polygons['label'] = (polygons['Conc'].str[:2].astype(int).astype(str) + ' ' +
                                 polygons['Conc'].str[2:4].astype(int).astype(str) + polygons['Conc'].str[4] + ' ' +
                                 polygons['Conc'].str[5:7].astype(int).astype(str) + polygons['Conc'].str[7] + ' ' +
                                 polygons['Conc'].str[-1])

            # Add centroids
            polygons['centroid'] = polygons['geometry'].apply(lambda x: x.centroid)
            return polygons

        point_df = process_input_data(data)

        bbox = get_points_bbox(point_df['shp_pt'])
        filtered_data = read_base_data_by_bbox(conn_db, bbox)

        # 2) Filter again by Conc
        conc_vals = filtered_data['Conc'].unique()
        filtered_data = read_base_data_by_conc(conn_db, conc_vals)
        # 3) Create polygons
        test_plat = geo_transform(filtered_data)
        if not isinstance(test_plat, gpd.GeoDataFrame):
            test_plat_gdf = gpd.GeoDataFrame(test_plat, geometry='geometry')
        else:
            test_plat_gdf = test_plat

        # 4) Join with original point_df as a GeoDataFrame
        plat_gdf = gpd.GeoDataFrame(
            point_df,
            geometry=point_df['shp_pt'],
            crs=test_plat_gdf.crs
        )

        plat_gdf.crs = "EPSG:4326"
        test_plat_gdf.crs = "EPSG:4326"

        joined = gpd.sjoin(
            plat_gdf,
            test_plat_gdf[['Conc', 'label', 'geometry']],
            how='inner',
            predicate='within'
        )

        # 5) Second pass for final polygons
        conc_vals = joined['Conc'].unique()
        filtered_data2 = read_base_data_by_conc(conn_db, conc_vals)

        test_plat = geo_transform(filtered_data2)

        return test_plat

    def find_plats_data(self, data):
        def setup_sqlite_db():
            path_used_db = r'C:\Work\Databases'
            apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
            return sqlite3.connect(apd_data_dir)

        def process_input_data(data):
            """
            Return a DataFrame from either a dict of data or an existing DataFrame.
            """
            if isinstance(data, dict):
                combined = []
                for obj in data.values():
                    combined.append(obj.true_dx)
                    combined.append(obj.grid_dx)
                return pd.concat(combined, ignore_index=True).drop_duplicates(keep="first")
            elif isinstance(data, pd.DataFrame):
                return data
            return pd.DataFrame()

        def read_base_data_by_bbox(conn, bbox, buffer_dist=1000):
            """
            Run a bounding box query on BaseData in the database.
            """
            query = f"""
                SELECT *
                FROM BaseData
                WHERE Easting >= {bbox[0] - buffer_dist}
                  AND Easting <= {bbox[2] + buffer_dist}
                  AND Northing >= {bbox[1] - buffer_dist}
                  AND Northing <= {bbox[3] + buffer_dist}
            """
            return pd.read_sql(query, conn)

        def read_base_data_by_conc(conn, conc_values):
            """
            Run a 'Conc in' query on BaseData for a given list of conc_values.
            """
            conc_str = ', '.join(f"'{c}'" for c in conc_values)
            query = f"SELECT * FROM BaseData WHERE Conc IN ({conc_str})"
            return pd.read_sql(query, conn)

        def get_points_bbox(points_series):
            """
            Calculate the bounding box of a pandas Series of Shapely Points.
            Returns (minx, miny, maxx, maxy).
            """
            coords = [(pt.x, pt.y) for pt in points_series]
            x_coords, y_coords = zip(*coords)
            return min(x_coords), min(y_coords), max(x_coords), max(y_coords)

        def geo_transform(df):
            # First create polygons DataFrame
            polygons = (df.groupby('Conc')
                        .apply(lambda x: Polygon(zip(x['Easting'], x['Northing'])))
                        .reset_index()
                        .rename(columns={0: 'geometry'}))

            # Add label transformation
            polygons['label'] = (polygons['Conc'].str[:2].astype(int).astype(str) + ' ' +
                                 polygons['Conc'].str[2:4].astype(int).astype(str) + polygons['Conc'].str[4] + ' ' +
                                 polygons['Conc'].str[5:7].astype(int).astype(str) + polygons['Conc'].str[7] + ' ' +
                                 polygons['Conc'].str[-1])

            # Add centroids
            polygons['centroid'] = polygons['geometry'].apply(lambda x: x.centroid)
            return polygons

        conn_db = setup_sqlite_db()
        point_df = process_input_data(data)

        # 1) Initial bounding box read
        bbox = get_points_bbox(point_df['shp_pt'])
        filtered_data = read_base_data_by_bbox(conn_db, bbox)

        # 2) Filter again by Conc
        conc_vals = filtered_data['Conc'].unique()
        filtered_data = read_base_data_by_conc(conn_db, conc_vals)

        # 3) Create polygons
        test_plat = geo_transform(filtered_data)
        if not isinstance(test_plat, gpd.GeoDataFrame):
            test_plat_gdf = gpd.GeoDataFrame(test_plat, geometry='geometry')
        else:
            test_plat_gdf = test_plat

        plat_gdf = gpd.GeoDataFrame(
            point_df,
            geometry=point_df['shp_pt'],
            crs=test_plat_gdf.crs
        )

        joined = gpd.sjoin(
            plat_gdf,
            test_plat_gdf[['Conc', 'label', 'geometry']],
            how='inner',
            predicate='within'
        )

        # 5) Second pass for final polygons
        conc_vals = joined['Conc'].unique()
        filtered_data2 = read_base_data_by_conc(conn_db, conc_vals)
        test_plat = geo_transform(filtered_data2)

        return test_plat, plat_gdf, test_plat_gdf

    def retrieve_sql_location_data(self, api, lateral, db):
        query = f"""select [Wh_Sec] as section, [Wh_Twpn] as township, [Wh_Twpd] as township_dir, [Wh_RngN] as rng, [Wh_RngD] as rng_dir,
         [Wh_Pm] as baseline, [Wh_FtNS] as fnsl, [Wh_Ns] as fnsl_dir, [Wh_FtEW] as fewl, [Wh_EW] as fewl_dir,
          [Zone_Name] as zone_name,[Wh_Qtr] as qtr_qtr,[Wh_X] as shl_x,[Wh_Y] as shl_y, [Bh_X] as bhl_x, [Bh_Y] as bhl_y
         from [dbo].[tblAPDLoc] where API LIKE '%{api}%' and API_EXT = '{lateral}'"""
        loc_df = db.query_to_dataframe(query)
        if loc_df.empty:
            query = f"""SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = '{api}{lateral}'"""
            output = db.query_to_dataframe(query)['APDNo'].unique()[0]
            query = f"""select [Wh_Sec] as section, [Wh_Twpn] as township, [Wh_Twpd] as township_dir, [Wh_RngN] as rng, [Wh_RngD] as rng_dir,
             [Wh_Pm] as baseline, [Wh_FtNS] as fnsl, [Wh_Ns] as fnsl_dir, [Wh_FtEW] as fewl, [Wh_EW] as fewl_dir,
              [Zone_Name] as zone_name,[Wh_Qtr] as qtr_qtr,[Wh_X] as shl_x,[Wh_Y] as shl_y, [Bh_X] as bhl_x, [Bh_Y] as bhl_y
             from [dbo].[tblAPDLoc] where APDNO = {output}"""
            loc_df = db.query_to_dataframe(query)
        loc_df = loc_df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        shl = loc_df[loc_df['zone_name'] == 'Surface Location']
        bhl = loc_df[loc_df['zone_name'] == 'Proposed Depth']
        return loc_df, shl, bhl
