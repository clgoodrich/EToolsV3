import sqlite3
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
import os


class TownShipAndRangeProcess:
    def __init__(self, api, lateral, db_process, survey_dict):
        def setup_db():
            path_used_db = r'C:\Work\Databases'
            apd_data_dir = os.path.join(path_used_db, 'location_data.db')
            return sqlite3.connect(apd_data_dir)
        location_db = setup_db()
        loc_df, shl, bhl = self.retrieve_sql_location_data(api, lateral, db_process)

        plat_df = self.find_plats_data2(data=survey_dict, conn_db = location_db)
        grouped_df = self.find_relative_data(conn_db=location_db, plat_df=plat_df)
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
        # print(data['drl_df'].true_dx.columns)
        # print(foo)
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
            # polygons = (
            #     df.groupby('Conc')
            #     .apply(lambda x: Polygon(zip(x['Easting'], x['Northing'])))
            #     .to_frame(name='geometry')
            #     .reset_index()
            # )
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

        def graphic(df_points, df_polygons):
            # Assuming df_points and df_polygons are your DataFrames
            # with a 'geometry' column of shapely Points and Polygons respectively

            # points_gdf = gpd.GeoDataFrame(df_points, geometry='geometry', crs="EPSG:4326")
            # polygons_gdf = gpd.GeoDataFrame(df_polygons, geometry='geometry', crs="EPSG:4326")

            # print(df_polygons['geometry'].values.tolist)
            fig, ax = plt.subplots(figsize=(10, 10))
            for geom in df_points['geometry']:
                ax.plot(geom.x, geom.y, 'ro')
            for geom in df_polygons['geometry']:
                x, y = geom.exterior.xy
                ax.plot(x, y, color='blue')
                # Plot points
                # if geom.geom_type == 'Point':
                #     ax.plot(geom.x, geom.y, 'ro')  # red marker for points
                # # Plot polygons
                # elif geom.geom_type == 'Polygon':
                #     x, y = geom.exterior.xy
                #     ax.plot(x, y, color='blue')
                # # For MultiPolygon objects, loop through each polygon
                # elif geom.geom_type == 'MultiPolygon':
                #     for poly in geom.geoms:
                #         x, y = poly.exterior.xy
                #         ax.plot(x, y, color='blue')

            # Manually set the aspect ratio to avoid the error.
            ax.set_aspect('equal')

            plt.title("Points and Polygons")
            plt.xlabel("Longitude / Easting")
            plt.ylabel("Latitude / Northing")
            plt.show()
        point_df = process_input_data(data)

        # 1) Initial bounding box read
        # pts_all = point_df['shp_pt'].values.tolist()
        # pts_all = [(i.x, i.y) for i in pts_all]
        # print(pts_all)
        # print(point_df['shp_pt'].values.tolist())
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
        # print(plat_gdf)
        # print(test_plat_gdf)
        plat_gdf.crs = "EPSG:4326"
        test_plat_gdf.crs = "EPSG:4326"

        # graphic(plat_gdf, test_plat_gdf)
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
        # 4) Join with original point_df as a GeoDataFrame
        # print(test_plat_gdf[['Conc', 'label', 'geometry']])

        plat_gdf = gpd.GeoDataFrame(
            point_df,
            geometry=point_df['shp_pt'],
            crs=test_plat_gdf.crs
        )
        # print(plat_gdf)

        joined = gpd.sjoin(
            plat_gdf,
            test_plat_gdf[['Conc', 'label', 'geometry']],
            how='inner',
            predicate='within'
        )
        # print(plat_gdf)

        # 5) Second pass for final polygons
        conc_vals = joined['Conc'].unique()
        filtered_data2 = read_base_data_by_conc(conn_db, conc_vals)
        test_plat = geo_transform(filtered_data2)

        return test_plat, plat_gdf, test_plat_gdf



    # def find_plats_data2(data):
    #     def setup_sqlite_db():
    #         path_used_db = r'C:\Work\Databases'
    #         apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
    #         conn_db = sqlite3.connect(apd_data_dir)
    #         return conn_db
    #
    #     def geo_transform(df):
    #         # First create polygons DataFrame
    #         polygons = (df.groupby('Conc')
    #                     .apply(lambda x: Polygon(zip(x['Easting'], x['Northing'])))
    #                     .reset_index()
    #                     .rename(columns={0: 'geometry'}))
    #
    #         # Add label transformation
    #         polygons['label'] = (polygons['Conc'].str[:2].astype(int).astype(str) + ' ' +
    #                              polygons['Conc'].str[2:4].astype(int).astype(str) + polygons['Conc'].str[4] + ' ' +
    #                              polygons['Conc'].str[5:7].astype(int).astype(str) + polygons['Conc'].str[7] + ' ' +
    #                              polygons['Conc'].str[-1])
    #
    #         # Add centroids
    #         polygons['centroid'] = polygons['geometry'].apply(lambda x: x.centroid)
    #         return polygons
    #
    #     # def geo_transform(df):
    #     #     def transform_string(s):
    #     #         part1 = str(int(s[:2]))
    #     #         part2 = str(int(s[2:4])) + s[4]
    #     #         part3 = str(int(s[5:7])) + s[7]
    #     #         part4 = s[-1]
    #     #
    #     #         return f"{part1} {part2} {part3} {part4}"
    #     #
    #     #     df['geometry'] = df.apply(lambda row: Point(row['Easting'], row['Northing']), axis=1)
    #     #     used_fields = df[['Conc', 'Easting', 'Northing', 'geometry']]
    #     #     used_fields['geometry'] = used_fields.apply(lambda row: Point(row['Easting'], row['Northing']), axis=1)
    #     #     polygons = used_fields.groupby('Conc').apply(
    #     #         lambda x: Polygon(zip(x['Easting'], x['Northing']))).reset_index()
    #     #     merged_data = used_fields.merge(polygons, on='Conc')
    #     #     merged_data = merged_data.drop('geometry', axis=1).rename(columns={0: 'geometry'})
    #     #     df_new = merged_data.groupby('Conc').apply(
    #     #         lambda x: Polygon(zip(x['Easting'], x['Northing']))).reset_index()
    #     #
    #     #     df_new.columns = ['Conc', 'geometry']
    #     #     df_new['centroid'] = df_new.apply(lambda x: x['geometry'].centroid, axis=1)
    #     #     df_new['label'] = df_new.apply(lambda x: transform_string(x['Conc']), axis=1)
    #     #     return df_new
    #
    #     conn_db = setup_sqlite_db()
    #     def get_points_bbox(points_series):
    #         """
    #         Calculate bbox from a series of Shapely points
    #
    #         Parameters:
    #         points_series: pandas Series containing Shapely Point objects
    #
    #         Returns:
    #         tuple: (minx, miny, maxx, maxy)
    #         """
    #         # Create a list of coordinates
    #         coords = [(pt.x, pt.y) for pt in points_series]
    #         # Unzip coordinates into separate x and y lists
    #         x_coords, y_coords = zip(*coords)
    #
    #         # Calculate bounds
    #         return min(x_coords), min(y_coords), max(x_coords), max(y_coords)
    #
    #     def get_coordinate_query(bbox, buffer_distance=1000):
    #         """
    #         Query using coordinate columns directly
    #
    #         Parameters:
    #         bbox: tuple of (minx, miny, maxx, maxy)
    #         buffer_distance: amount to expand search area
    #         """
    #         return f"""
    #         SELECT *
    #         FROM BaseData
    #         WHERE
    #             Easting >= {bbox[0] - buffer_distance}
    #             AND Easting <= {bbox[2] + buffer_distance}
    #             AND Northing >= {bbox[1] - buffer_distance}
    #             AND Northing <= {bbox[3] + buffer_distance}
    #         """
    #     empty_pd = pd.DataFrame()
    #     output = []
    #     if isinstance(data, dict):
    #         for k, v in data.items():
    #             output.append(v.true_dx)
    #             output.append(v.grid_dx)
    #         point_df = pd.concat(output, ignore_index=True).drop_duplicates(
    #             keep="first")
    #     elif isinstance(data, pd.DataFrame):
    #         point_df = data
    #     # Usage:
    #     bbox = get_points_bbox(point_df['shp_pt'])
    #     spatial_query = get_coordinate_query(bbox)
    #     filtered_data = pd.read_sql(spatial_query, conn_db)
    #     conc_vals = filtered_data['Conc'].unique()
    #     concs = [str(i) for i in conc_vals]
    #     concs = ', '.join([f"'{str(elem)}'" for elem in concs])
    #     query = f"""select * from BaseData where Conc IN ({concs})"""
    #     filtered_data = pd.read_sql(query, conn_db)
    #     test_plat = geo_transform(filtered_data)
    #     if not isinstance(test_plat, gpd.GeoDataFrame):
    #         test_plat_gdf = gpd.GeoDataFrame(test_plat, geometry='geometry')
    #     else:
    #         test_plat_gdf = test_plat
    #
    #     # Convert plat_df to a GeoDataFrame with Point geometries
    #     plat_gdf = gpd.GeoDataFrame(
    #         point_df,
    #         geometry=point_df['shp_pt'],
    #         crs=test_plat_gdf.crs  # Ensure both GeoDataFrames have the same CRS
    #     )
    #     #
    #     joined = gpd.sjoin(plat_gdf, test_plat_gdf[['Conc', 'label', 'geometry']], how='inner', predicate='within')
    #     conc_vals = joined['Conc'].unique()
    #     concs = [str(i) for i in conc_vals]
    #     concs = ', '.join([f"'{str(elem)}'" for elem in concs])
    #     query = f"""select * from BaseData where Conc IN ({concs})"""
    #     filtered_data = pd.read_sql(query, conn_db)
    #     test_plat = geo_transform(filtered_data)
    #     return test_plat



    # def geo_transform(self, df):
    #     def transform_string(s):
    #         part1 = str(int(s[:2]))
    #         part2 = str(int(s[2:4])) + s[4]
    #         part3 = str(int(s[5:7])) + s[7]
    #         part4 = s[-1]
    #
    #         return f"{part1} {part2} {part3} {part4}"
    #
    #     df['geometry'] = df.apply(lambda row: Point(row['Easting'], row['Northing']), axis=1)
    #     used_fields = df[['Conc', 'Easting', 'Northing', 'geometry']]
    #     used_fields['geometry'] = used_fields.apply(lambda row: Point(row['Easting'], row['Northing']), axis=1)
    #     polygons = used_fields.groupby('Conc').apply(lambda x: Polygon(zip(x['Easting'], x['Northing']))).reset_index()
    #     merged_data = used_fields.merge(polygons, on='Conc')
    #     merged_data = merged_data.drop('geometry', axis=1).rename(columns={0: 'geometry'})
    #     df_new = merged_data.groupby('Conc').apply(lambda x: Polygon(zip(x['Easting'], x['Northing']))).reset_index()
    #
    #     df_new.columns = ['Conc', 'geometry']
    #     df_new['centroid'] = df_new.apply(lambda x: x['geometry'].centroid, axis=1)
    #     df_new['label'] = df_new.apply(lambda x: transform_string(x['Conc']), axis=1)
    #     return df_new

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

    # def setup_sqlite_db(self):
    #     path_used_db = r'C:\Work\Databases'
    #     apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
    #     conn_db = sqlite3.connect(apd_data_dir)
    #     return conn_db

    # def retrieve_all_plats_proximal(self, loc_df, conn_db):
    #     def query_for_data():
    #         query = f"""SELECT * FROM BaseData WHERE """
    #         conditions = []
    #         for _, row in needed_wells.iterrows():
    #             condition = f"""(SECTION = '{row['section']}' AND TOWNSHIP = '{row['township']}' AND Township_D = '{row['township_dir']}' AND RANGE = '{row['rng']}' AND Range_D = '{row['rng_dir']}' AND Baseline = '{row['baseline']}')"""
    #             conditions.append(condition)
    #         query += ' OR '.join(conditions)
    #         return query
    #     needed_wells = loc_df[['section', 'township', 'township_dir', 'rng', 'rng_dir', 'baseline']].drop_duplicates(
    #         keep="first")
    #     needed_wells["township"] = needed_wells["township"].astype(float).astype(int).astype(str).astype(str)
    #     needed_wells["rng"] = needed_wells["rng"].astype(float).astype(int).astype(str).astype(str)
    #     needed_wells['section'] = needed_wells['section'].astype(str)
    #     plat_df = pd.read_sql(query_for_data(), conn_db)
    #     plat_df = plat_df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
    #     return plat_df

    # def check_adjacent_plats(self, conn_db, plat_df, survey_dict):
    #     def check_contains_any_point(polygon, points):
    #         return any(polygon.contains(point) for point in points)
    #     quoted_values = [f"'{value}'" for value in plat_df['Conc'].unique()]
    #     values_string = ', '.join(quoted_values)
    #     df_adjacent_plats = pd.read_sql(f"select * from Adjacent where Conc2 in ({values_string})", conn_db)[
    #         'adjacent_Conc_Name_2']
    #
    #     quoted_values_2 = [f"'{value}'" for value in df_adjacent_plats.unique()]
    #     quoted_values_2 = list(set(quoted_values_2))
    #     values_string_2 = ', '.join(quoted_values_2)
    #     values_string_2 += values_string
    #
    #     df_adjacent_plats2 = pd.read_sql(f"select * from Adjacent where Conc2 in ({values_string_2})", conn_db)[
    #         'adjacent_Conc_Name_2']
    #     quoted_values_3 = [f"'{value}'" for value in df_adjacent_plats2.unique()]
    #     quoted_values_3 = list(set(quoted_values_3))
    #     values_string_3 = ', '.join(quoted_values_3)
    #     values_string_3 += values_string
    #     values_string_2 = values_string_3
    #
    #     query = f"select * from BaseData where Conc in ({values_string_2})"
    #     df_adjacent_plats_loc_data = pd.read_sql(query, conn_db)
    #     df_adjacent_plats_loc_data = ma.geometryTransform(df_adjacent_plats_loc_data)
    #     point_list = []
    #     for i, v in survey_dict.items():
    #         survey_used = survey_dict[i]
    #         point_list.extend(survey_used.true_dx['shp_pt'].tolist())
    #         point_list.extend(survey_used.grid_dx['shp_pt'].tolist())
    #     point_list = list(set(point_list))
    #     #
    #     # # Apply the check to each polygon in df_adjacent_plats_loc_data
    #     df_adjacent_plats_loc_data['contains_point'] = df_adjacent_plats_loc_data['geometry'].apply(
    #         lambda poly: check_contains_any_point(poly, point_list))
    #     result = df_adjacent_plats_loc_data[df_adjacent_plats_loc_data['contains_point']]
    #     result = result.drop('contains_point', axis=1)
    #     plat_df = pd.concat([plat_df, result], ignore_index=True).drop_duplicates(
    #         keep="first")
    #     return plat_df


    # def retrievePlatData(self):
    #     path_used_db = r'C:\Work\Databases'
    #     apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
    #     conn_db = sqlite3.connect(apd_data_dir)
    #     needed_wells = self.base_well_df[['Sec', 'Township', 'TownshipDir', 'Range', 'RangeDir', 'PM']].drop_duplicates(
    #         keep="first")
    #     needed_wells["Township"] = needed_wells["Township"].astype(float).astype(int).astype(str).astype(str)
    #     needed_wells["Range"] = needed_wells["Range"].astype(float).astype(int).astype(str).astype(str)
    #     needed_wells['Sec'] = needed_wells['Sec'].astype(str)
    #     query = f"""SELECT * FROM BaseData WHERE """
    #     conditions = []
    #     for _, row in needed_wells.iterrows():
    #         condition = f"""(SECTION = '{row['Sec']}' AND TOWNSHIP = '{row['Township']}' AND Township_D = '{row['TownshipDir']}' AND RANGE = '{row['Range']}' AND Range_D = '{row['RangeDir']}' AND Baseline = '{row['PM']}')"""
    #         conditions.append(condition)
    #     query += ' OR '.join(conditions)
    #     self.plat_df = pd.read_sql(query, conn_db)
    #     self.plat_df = self.plat_df.map(self.strip_if_string)
    #     self.plat_df = ma.geometryTransform(self.plat_df)
    #     self.plat_df, self.all_plats_adjacent = self.makeSureAllPlatsAreFoundByCheckingAdjacentPlats(conn_db, self.plat_df)
    #
    #     conn_db.close()
