import traceback

import pandas as pd
from main_project_dx_survey import SurveyProcess
import main_project_detect_kop
from PyQt5.QtWidgets import QHeaderView, QAbstractItemView
from typing import Dict, Any, List, Tuple, Union

import numpy as np
from kop_predictor import predict_kickoff_point, analyze_survey, determine_well_type

class SurveyProcessBase:
    """Base class for processing well survey data with coordinate transformations and trajectory calculations.

    This class manages the complete survey processing workflow, handling both planned and as-drilled
    survey data. It processes different citing types (Planned/AsDrilled) and generates both true
    north and grid north referenced trajectories along with key point identification (KOP, Landing Point, BHL).
    """

    def __init__(self, api: str, lateral: str, db_process: 'DatabaseManager', survey_dx: pd.DataFrame,
                 well_elevation: float, north_ref: List[str]) -> None:
        """Initialize survey processing with well identifiers and survey data.

        Sets up the survey processing framework to handle multiple citing types and coordinate
        reference systems. Initializes data structures for processed surveys and special depth
        points, then triggers the main survey processing workflow.

        Args:
            api (str): API well number identifier for database correlation
            lateral (str): Lateral designation for multi-lateral wells
            db_process (DatabaseManager): Database connection manager for data queries
            survey_dx (pd.DataFrame): Raw survey data containing measured depth, inclination,
                azimuth, and location information
            well_elevation (float): Surface elevation of the well in feet above sea level
            north_ref (List[str]): North reference system indicator (True/Grid)
        """
        # Step 1: Initialize processing parameters and data structures
        self.conv_angle = 0  # Convergence angle placeholder - will be calculated during processing
        self.dx_dict = {}  # Dictionary to store processed survey objects
        self.dx_dict_spec_depths = {}  # Dictionary to store special depth points (KOP, LP, BHL)
        self.survey_dx = survey_dx  # Store raw survey data for processing

        # Step 2: Setup survey processing parameters dictionary
        self.survey_parameters = {"conv_angle": self.conv_angle, "north_ref": None}
        self.survey_parameters["north_ref"] = north_ref[0].lower()  # Extract first character and normalize

        # Step 3: Trigger main survey processing workflow
        self.survey_process(self.survey_dx, well_elevation, north_ref)

    def survey_process(self, survey_dx: pd.DataFrame, well_elevation: float, north_ref: List[str]) -> None:
        """Process survey data for all citing types present in the dataset.

        Identifies unique citing types (Planned/AsDrilled) in the survey data and processes
        each type separately. Creates standardized survey objects and calculates special
        depth points for engineering analysis and regulatory reporting.

        Args:
            survey_dx (pd.DataFrame): Complete survey dataset with multiple citing types
            well_elevation (float): Well surface elevation for depth calculations
            north_ref (List[str]): North reference system specification
        """
        # Step 1: Identify unique citing types in the survey data
        citing_types = survey_dx['CitingType'].unique()

        # Step 2: Setup citing type mapping for standardized naming
        dict_citings = {"Planned": 'pln', 'AsDrilled': 'drl'}

        # Step 3: Process each citing type individually
        for i in citing_types:
            # Step 3a: Get standardized label for citing type
            relabel = dict_citings[i]

            # Step 3b: Process survey data and extract results
            self.dx_dict[f"""{relabel}_df"""], self.dx_dict_spec_depths[
                f"""{relabel}_df"""], self.conv_angle = self.reprocess_survey(survey_dx, relabel, i, well_elevation,
                                                                              north_ref)

        # Step 4: Update parameters with calculated convergence angle
        self.survey_parameters["conv_angle"] = self.conv_angle

    def reprocess_survey(self, survey_dx: pd.DataFrame, relabel: str, i: str, well_elevation: float,
                         north_ref: List[str]) -> Tuple['SurveyProcess', pd.DataFrame, float]:

        def kop_test(survey_df, label):
            try:
                # Load survey data
                # print(f"Loaded {len(survey_df)} survey points")
                # print(f"Depth range: {survey_df['measured_depth'].min():.0f} - {survey_df['measured_depth'].max():.0f} ft")

                # Convert inclination and azimuth to radians if they're in degrees
                if survey_df['inclination'].max() > 10:  # Likely in degrees
                    survey_df['inclination'] = np.radians(survey_df['inclination'])
                    survey_df['azimuth'] = np.radians(survey_df['azimuth'])

                # Perform complete analysis
                results = analyze_survey(survey_df)


                if results['kop']:
                    kop = results['kop']
                    kop_df = pd.DataFrame([kop])
                    kop_df['Point'] = 'KOP'
                    kop_df['type'] = f"{sot}{label}"

                    # Landing point analysis for all directional/horizontal wells
                    if results['landing_point']:
                        lp = results['landing_point']
                        lp_df = pd.DataFrame([lp])
                        lp_df['Point'] = 'LP'
                        lp_df['type'] = f"{sot}{label}"
                        return kop_df, lp_df
                    else:
                        # print(f"\nNo clear landing point detected")
                        if results['well_type'] == 'directional':
                            print("  (Well may still be building or have irregular profile)")
                        return kop_df, pd.DataFrame()
                else:
                    print("\nNo kickoff point detected - likely a vertical well")
                    return 0, 0

            except Exception as e:
                print(f"Error processing file: {e}")
                error_traceback = traceback.format_exc()
                print(f"Error details:\n{error_traceback}")
        """Process individual survey citing type with trajectory calculations and special point identification.

        Creates trajectory calculations for both true north and grid north reference systems,
        identifies critical well points (KOP, Landing Point, BHL), and handles error cases
        for kick-off point detection using advanced algorithms.

        Args:
            survey_dx (pd.DataFrame): Complete survey dataset containing all citing types
            relabel (str): Standardized label for citing type ('pln' or 'drl')
            i (str): Original citing type name ('Planned' or 'AsDrilled')
            well_elevation (float): Surface elevation for trajectory calculations
            north_ref (List[str]): North reference system specification

        Returns:
            Tuple[SurveyProcess, pd.DataFrame, float]: Processed survey object, special depth
                points DataFrame, and calculated convergence angle
        """
        # Step 1: Setup object naming convention for dynamic attribute assignment
        sot = f"""{relabel}_df"""

        # Step 2: Filter and prepare survey data for specific citing type
        survey_dx = survey_dx[
            ['measured_depth', 'inclination', 'azimuth', 'CitingType', 'SurfaceLatitude', 'SurfaceLongitude']]

        # Step 3: Create individual survey object with filtered data
        setattr(self, f"""survey_dx_{relabel}""", IndividualSurvey(survey_dx, i))
        object_dx = getattr(self, f"survey_dx_{relabel}")

        # Step 4: Extract starting coordinates for trajectory calculations
        starting_point = (object_dx.surf_lat, object_dx.surf_lon)

        # Step 5: Create main survey processing object with coordinate transformations
        setattr(self, sot, SurveyProcess(df_referenced=object_dx.df,
                                         elevation=float(well_elevation),
                                         north_ref=north_ref,
                                         starting_point=starting_point))
        output = getattr(self, sot)

        # Step 6: Extract Bottom Hole Location (BHL) data for true north trajectory
        bhl_true = output.true_dx.iloc[-1][['measured_depth', 'inclination', 'azimuth']]
        bhl_true['Point'] = 'BHL'
        bhl_true['type'] = f"{sot}_true_dx"

        # Step 7: Process kick-off point and landing point identification
        # output.find_kop_and_lp_process(output.true_dx)
        # lp_true = output.find_landing_point(output.true_dx)

        # Step 8: Attempt standard kick-off point detection with fallback to advanced algorithm
        kop_true,lp_true = kop_test(output.true_dx, '_true_dx')
        kop_grid,lp_grid = kop_test(output.grid_dx,'_grid_dx')

        # print(kop_true_2)
        # # print(filter_by_citing_type(kop_true_2, output.true_dx))
        # try:
        #     kop_true = output.find_kick_off_point(output.true_dx)
        # except IndexError:
        #     # Step 8a: Use advanced KOP detection algorithm when standard method fails
        #     kop_result = main_project_detect_kop.determine_kickoff_point(output.true_dx)
        #     print('kop result', kop_result)
        #     kop_true = output.true_dx[output.true_dx['measured_depth'] == kop_result['kop_md']][
        #         ['measured_depth', 'inclination', 'azimuth']]
        #     kop_true['Point'] = 'KOP'
        # # Step 9: Label true north trajectory points with type information
        # kop_true['type'] = f"{sot}_true_dx"
        # lp_true['type'] = f"{sot}_true_dx"
        #
        # # Step 10: Process grid north trajectory points (parallel processing to true north)
        # bhl_grid = output.grid_dx.iloc[-1][['measured_depth', 'inclination', 'azimuth']]
        # bhl_grid['Point'] = 'BHL'
        # bhl_grid['type'] = f"{sot}_grid_dx"
        # lp_grid = output.find_landing_point(output.grid_dx)
        #
        # # Step 11: Grid north KOP detection with same fallback logic
        # try:
        #     kop_grid = output.find_kick_off_point(output.grid_dx)
        # except IndexError:
        #     # Step 11a: Apply advanced algorithm for grid north trajectory
        #     kop_result = main_project_detect_kop.determine_kickoff_point(output.grid_dx)
        #     kop_grid = output.grid_dx[output.grid_dx['measured_depth'] == kop_result['kop_md']][
        #         ['measured_depth', 'inclination', 'azimuth']]
        #     kop_grid['Point'] = 'KOP'

        # # Step 12: Complete grid north trajectory labeling
        # kop_grid['type'] = f"{sot}_grid_dx"
        # lp_grid['type'] = f"{sot}_grid_dx"
        # print('kop', kop_true)

        # Step 13: Combine all special depth points into comprehensive DataFrame
        spec_vals = pd.concat([kop_true, kop_grid, lp_true, lp_grid])

        return output, spec_vals, output.conv_angle


class IndividualSurvey:
    """Individual survey data processor for specific citing types.

    This class handles the preprocessing of survey data for individual citing types
    (Planned or AsDrilled), including data filtering, coordinate extraction, and
    zero-depth insertion when necessary for trajectory calculations.
    """

    def __init__(self, df: pd.DataFrame, label: str) -> None:
        """Initialize individual survey processor with citing type filtering.

        Filters survey data to specific citing type and extracts surface coordinates
        for trajectory calculations. Handles data validation and preprocessing for
        subsequent survey processing operations.

        Args:
            df (pd.DataFrame): Complete survey dataset containing multiple citing types
            label (str): Citing type to filter and process ('Planned' or 'AsDrilled')
        """
        # Step 1: Initialize coordinate storage attributes
        self.surf_lat, self.surf_lon = None, None
        self.label = label

        # Step 2: Filter dataset to specific citing type and reset indexing
        df = df[df['CitingType'] == label].reset_index(drop=True)

        # Step 3: Process filtered data if not empty
        if not df.empty:
            self.df = self.assign_new_variables(df)

    def assign_new_variables(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process and validate survey data with zero-depth insertion if necessary.

        Sorts survey data by measured depth, extracts surface coordinates, and ensures
        a zero measured depth point exists for proper trajectory calculation. Inserts
        zero-depth row when missing and gap is significant (>500 feet).

        Args:
            df (pd.DataFrame): Filtered survey data for specific citing type

        Returns:
            pd.DataFrame: Processed survey data with proper depth sequencing and
                surface coordinate information
        """
        # Step 1: Sort survey data by measured depth for proper trajectory calculation
        df = df.sort_values('measured_depth', ascending=True)

        # Step 2: Extract surface coordinates from first survey point
        surf_lat, surf_lon = df['SurfaceLatitude'].iloc[0], df['SurfaceLongitude'].iloc[0]

        # Step 3: Check for missing zero measured depth point and significant gap
        if df['measured_depth'].iloc[0] != 0 and df['measured_depth'].iloc[1] - 0 > 500:
            # Step 3a: Create zero-depth row with surface coordinates and neutral trajectory
            new_row = pd.DataFrame({'measured_depth': [0],
                                    'inclination': [0],  # Vertical inclination at surface
                                    'azimuth': [0],  # Neutral azimuth at surface
                                    'CitingType': self.label,
                                    'SurfaceLatitude': df['SurfaceLatitude'].iloc[0],
                                    'SurfaceLongitude': df['SurfaceLongitude'].iloc[0],
                                    })
            # Step 3b: Prepend zero-depth row and reset indexing
            df = pd.concat([new_row, df]).reset_index(drop=True)

        # Step 4: Store surface coordinates as instance attributes
        self.surf_lat, self.surf_lon = surf_lat, surf_lon

        return df