import sqlite3
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
import os
from typing import Tuple, Dict, Any, Union


class TownShipAndRangeProcess:
    """Process and retrieve township, range, and plat data for oil and gas well locations.

    This class manages the integration of well survey data with Public Land Survey System (PLSS)
    plat information, handling spatial queries and geographic data processing for regulatory
    compliance and engineering analysis.
    """

    def __init__(self, api: str, lateral: str, db_process: 'DatabaseManager', survey_dict: Dict[str, Any], location_db: sqlite3.Connection) -> None:
        """Initialize township and range processing with well identifiers and database connections.

        Sets up location data retrieval and plat boundary processing for a specific well.
        Coordinates between regulatory databases and spatial plat information to provide
        comprehensive location context for engineering analysis.

        Args:
            api (str): API well number identifier
            lateral (str): Lateral designation for multi-lateral wells
            db_process (DatabaseManager): Main database connection manager for regulatory data
            survey_dict (Dict[str, Any]): Dictionary containing processed survey objects
            location_db (sqlite3.Connection): SQLite connection to plat boundary database
        """

        def setup_db():
            # Internal helper function for backup database connection setup
            path_used_db = r'C:\Work\Databases'
            apd_data_dir = os.path.join(path_used_db, 'location_data.db')
            return sqlite3.connect(apd_data_dir)

        # Step 1: Retrieve regulatory location data from APD database
        loc_df, shl, bhl = self.retrieve_sql_location_data(api, lateral, db_process)

        # Step 2: Find and process plat boundary data using survey trajectory points
        plat_df = self.find_plats_data2(data=survey_dict, conn_db=location_db)

        # Step 3: Store processed data as instance attributes for later access
        self.plat_df = plat_df
        self.loc_df = loc_df

    def find_relative_data(self, conn_db: sqlite3.Connection, plat_df: pd.DataFrame) -> pd.core.groupby.DataFrameGroupBy:
        """Retrieve relative coordinate data for plat sections from database.

        Queries the section_relative table to find coordinate transformation data
        for the plat concentrations identified in the plat_df. Groups results by
        concentration and version for systematic coordinate processing.

        Args:
            conn_db (sqlite3.Connection): Database connection to plat data
            plat_df (pd.DataFrame): DataFrame containing plat data with 'Conc' column

        Returns:
            pd.core.groupby.DataFrameGroupBy: Grouped data by concentration and version
        """
        # Step 1: Extract unique concentration values from plat data
        used_concs = tuple(plat_df['Conc'].unique().tolist())

        # Step 2: Query database for all relative coordinate data
        query = f"select * from section_relative"
        output = pd.read_sql(query, conn_db).drop_duplicates(keep="first")

        # Step 3: Standardize concentration format and filter to used concentrations
        output['Conc'] = output['Conc'].apply(lambda row: row[:9])  # Truncate to 9 characters
        output = output[output['Conc'].isin(used_concs)]

        # Step 4: Group by concentration and version for coordinate processing
        grouped = output.groupby(['Conc', 'Version'])
        return grouped

    def find_plats_data2(self, data: Union[Dict[str, Any], pd.DataFrame], conn_db: sqlite3.Connection) -> pd.DataFrame:
        """Find plat boundary data using spatial queries and survey trajectory analysis.

        Implements a multi-stage spatial analysis pipeline to identify plat boundaries
        that intersect with well survey trajectories. Uses bounding box optimization
        and spatial joins to efficiently process large plat databases.

        Args:
            data (Union[Dict[str, Any], pd.DataFrame]): Survey trajectory data as dictionary
                of survey objects or processed DataFrame
            conn_db (sqlite3.Connection): Database connection to plat boundary data

        Returns:
            pd.DataFrame: Processed plat boundary data with geometry and labels
        """

        def process_input_data(data: Union[Dict[str, Any], pd.DataFrame]) -> pd.DataFrame:
            """Convert survey data from various formats into standardized DataFrame format.

            Handles both dictionary format (containing survey objects with true_dx and grid_dx)
            and direct DataFrame input, ensuring consistent processing pipeline.
            """
            if isinstance(data, dict):
                # Step 1a: Extract trajectory data from survey objects
                combined = []
                for obj in data.values():
                    combined.append(obj.true_dx)
                    combined.append(obj.grid_dx)
                # Step 1b: Combine and deduplicate trajectory points
                return pd.concat(combined, ignore_index=True).drop_duplicates(keep="first")
            elif isinstance(data, pd.DataFrame):
                return data
            return pd.DataFrame()

        def read_base_data_by_bbox(conn: sqlite3.Connection, bbox: Tuple[float, float, float, float], buffer_dist: int = 1000) -> pd.DataFrame:
            """Execute spatial bounding box query with buffer distance for initial data filtering.

            Optimizes database queries by limiting results to geographic area of interest
            plus buffer zone, reducing memory usage and processing time for large datasets.
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

        def read_base_data_by_conc(conn: sqlite3.Connection, conc_values: list) -> pd.DataFrame:
            """Query plat data using concentration value list for targeted data retrieval.

            Performs efficient IN clause query to retrieve only the plat sections
            that contain survey trajectory points, minimizing data transfer and processing.
            """
            conc_str = ', '.join(f"'{c}'" for c in conc_values)
            query = f"SELECT * FROM BaseData WHERE Conc IN ({conc_str})"
            return pd.read_sql(query, conn)

        def get_points_bbox(points_series: pd.Series) -> Tuple[float, float, float, float]:
            """Calculate spatial bounding box coordinates from series of Shapely Point objects.

            Extracts coordinate extremes to define rectangular boundary encompassing
            all trajectory points for spatial query optimization.
            """
            coords = [(pt.x, pt.y) for pt in points_series]
            x_coords, y_coords = zip(*coords)
            return min(x_coords), min(y_coords), max(x_coords), max(y_coords)

        def geo_transform(df: pd.DataFrame) -> pd.DataFrame:
            """Transform coordinate points into polygon geometries with standardized labels.

            Groups coordinate data by concentration values, creates polygon geometries,
            generates human-readable labels, and calculates centroids for visualization
            and spatial analysis operations.
            """
            # Step 1: Create polygon geometries from coordinate groups
            polygons = (df.groupby('Conc')
                        .apply(lambda x: Polygon(zip(x['Easting'], x['Northing'])))
                        .reset_index()
                        .rename(columns={0: 'geometry'}))

            # Step 2: Generate readable township/range labels from concentration codes
            polygons['label'] = (polygons['Conc'].str[:2].astype(int).astype(str) + ' ' +
                                 polygons['Conc'].str[2:4].astype(int).astype(str) + polygons['Conc'].str[4] + ' ' +
                                 polygons['Conc'].str[5:7].astype(int).astype(str) + polygons['Conc'].str[7] + ' ' +
                                 polygons['Conc'].str[-1])

            # Step 3: Calculate polygon centroids for labeling and analysis
            polygons['centroid'] = polygons['geometry'].apply(lambda x: x.centroid)
            return polygons

        # Main processing pipeline
        # Step 1: Process input survey data into standardized format
        point_df = process_input_data(data)

        # Step 2: Calculate bounding box for spatial query optimization
        bbox = get_points_bbox(point_df['shp_pt'])
        filtered_data = read_base_data_by_bbox(conn_db, bbox)

        # Step 3: Refine data selection using concentration filtering
        conc_vals = filtered_data['Conc'].unique()
        filtered_data = read_base_data_by_conc(conn_db, conc_vals)

        # Step 4: Transform coordinate data into polygon geometries
        test_plat = geo_transform(filtered_data)
        if not isinstance(test_plat, gpd.GeoDataFrame):
            test_plat_gdf = gpd.GeoDataFrame(test_plat, geometry='geometry')
        else:
            test_plat_gdf = test_plat

        # Step 5: Create GeoDataFrame from survey points for spatial analysis
        plat_gdf = gpd.GeoDataFrame(
            point_df,
            geometry=point_df['shp_pt'],
            crs=test_plat_gdf.crs
        )

        # Step 6: Standardize coordinate reference systems for spatial operations
        plat_gdf.crs = "EPSG:4326"
        test_plat_gdf.crs = "EPSG:4326"

        # Step 7: Perform spatial join to identify containing plats for each survey point
        joined = gpd.sjoin(
            plat_gdf,
            test_plat_gdf[['Conc', 'label', 'geometry']],
            how='inner',
            predicate='within'
        )

        # Step 8: Final data refinement using updated concentration list
        conc_vals = joined['Conc'].unique()
        filtered_data2 = read_base_data_by_conc(conn_db, conc_vals)
        test_plat = geo_transform(filtered_data2)

        return test_plat

    # def find_plats_data(self, data: Union[Dict[str, Any], pd.DataFrame]) -> Tuple[pd.DataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    #     """Legacy method for plat data processing - superseded by find_plats_data2.
    #
    #     This method implements an older approach to plat boundary identification
    #     and has been replaced by the more efficient find_plats_data2 method.
    #     Maintained for backward compatibility but not actively used.
    #     """
    #     def setup_sqlite_db():
    #         path_used_db = r'C:\Work\Databases'
    #         apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
    #         return sqlite3.connect(apd_data_dir)
    #
    #     def process_input_data(data):
    #         """Return a DataFrame from either a dict of data or an existing DataFrame."""
    #         if isinstance(data, dict):
    #             combined = []
    #             for obj in data.values():
    #                 combined.append(obj.true_dx)
    #                 combined.append(obj.grid_dx)
    #             return pd.concat(combined, ignore_index=True).drop_duplicates(keep="first")
    #         elif isinstance(data, pd.DataFrame):
    #             return data
    #         return pd.DataFrame()
    #
    #     # Legacy implementation details...
    #     # This method has been commented out as it's no longer used in the current workflow

    def retrieve_sql_location_data(self, api: str, lateral: str, db: 'DatabaseManager') -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Retrieve well location data from APD database using API number and lateral designation.

        Attempts to find location data using API pattern matching first, then falls back to
        APD number lookup if no results found. Returns complete location data plus filtered
        subsets for surface and bottom hole locations.

        Args:
            api (str): API well number identifier (e.g., "05-123-45678")
            lateral (str): Lateral designation (e.g., "H", "A", "B")
            db (DatabaseManager): Database connection manager with query_to_dataframe method

        Returns:
            Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
                - loc_df: Complete location dataset with PLSS and coordinate data
                - shl: Surface location records only
                - bhl: Proposed depth location records only
        """
        # Step 1: Attempt primary query using API pattern matching with lateral extension
        query = f"""select [Wh_Sec] as section, [Wh_Twpn] as township, [Wh_Twpd] as township_dir, [Wh_RngN] as rng, [Wh_RngD] as rng_dir,
         [Wh_Pm] as baseline, [Wh_FtNS] as fnsl, [Wh_Ns] as fnsl_dir, [Wh_FtEW] as fewl, [Wh_EW] as fewl_dir,
          [Zone_Name] as zone_name,[Wh_Qtr] as qtr_qtr,[Wh_X] as shl_x,[Wh_Y] as shl_y, [Bh_X] as bhl_x, [Bh_Y] as bhl_y
         from [dbo].[tblAPDLoc] where API LIKE '%{api}%' and API_EXT = '{lateral}'"""
        loc_df = db.query_to_dataframe(query)

        # Step 2: If primary query returns empty, use fallback APD number resolution
        if loc_df.empty:
            # Step 2a: Resolve APD number from master table using concatenated API+lateral
            query = f"""SELECT APDNo, Well_Nm FROM [dbo].[tblAPD] WHERE API_WellNo = '{api}{lateral}'"""
            output = db.query_to_dataframe(query)['APDNo'].unique()[0]

            # Step 2b: Query location table using resolved APD number
            query = f"""select [Wh_Sec] as section, [Wh_Twpn] as township, [Wh_Twpd] as township_dir, [Wh_RngN] as rng, [Wh_RngD] as rng_dir,
             [Wh_Pm] as baseline, [Wh_FtNS] as fnsl, [Wh_Ns] as fnsl_dir, [Wh_FtEW] as fewl, [Wh_EW] as fewl_dir,
              [Zone_Name] as zone_name,[Wh_Qtr] as qtr_qtr,[Wh_X] as shl_x,[Wh_Y] as shl_y, [Bh_X] as bhl_x, [Bh_Y] as bhl_y
             from [dbo].[tblAPDLoc] where APDNO = {output}"""
            loc_df = db.query_to_dataframe(query)

        # Step 3: Clean string data by trimming whitespace from all object columns
        loc_df = loc_df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

        # Step 4: Filter data by zone types to create specialized datasets
        shl = loc_df[loc_df['zone_name'] == 'Surface Location']  # Surface hole location
        bhl = loc_df[loc_df['zone_name'] == 'Proposed Depth']  # Bottom hole location

        return loc_df, shl, bhl