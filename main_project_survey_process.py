import pandas as pd
from main_project_dx_survey import SurveyProcess
import main_project_detect_kop


class SurveyProcessBase:
    def __init__(self, api, lateral, db_process, survey_dx, well_elevation, north_ref):
        self.conv_angle = 0
        self.dx_dict = {}
        self.dx_dict_spec_depths = {}
        self.survey_dx = survey_dx
        self.survey_parameters = {"conv_angle": self.conv_angle, "north_ref": None}
        self.survey_parameters["north_ref"] = north_ref[0].lower()
        self.survey_process(self.survey_dx, well_elevation, north_ref)

    def sql_query_survey(self, db_process, api, lateral):
        query = f"""SELECT MeasuredDepth as measured_depth, Inclination as inclination, Azimuth as azimuth, 
        CitingType, dsh.SurveySurfaceElevation, dsh.SurfaceLatitude, dsh.SurfaceLongitude,dsh.NorthReference
                FROM DirectionalSurveyHeader dsh
                JOIN DirectionalSurveyData dsd on dsd.DirectionalSurveyHeaderKey = dsh.Pkey
                WHERE dsh.APINumber = '{api}' and dsh.LateralName = '{lateral}' order by MeasuredDepth"""
        survey_dx = db_process.query_to_dataframe(query)
        well_elevation = survey_dx['SurveySurfaceElevation'].iloc[0]
        north_ref = survey_dx['NorthReference'].iloc[0][0].lower()
        survey_dx = survey_dx.drop(['SurveySurfaceElevation', 'NorthReference'], axis=1)
        survey_dx = survey_dx.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        survey_dx = survey_dx.sort_values(by=['CitingType', 'measured_depth'])
        survey_dx['CitingType'] = survey_dx['CitingType'].str.lower().replace(
            {'asdrilled': 'AsDrilled', 'planned': 'Planned'})
        return survey_dx, well_elevation, north_ref

    def survey_process(self, survey_dx, well_elevation, north_ref):
        citing_types = survey_dx['CitingType'].unique()
        dict_citings = {"Planned": 'pln', 'AsDrilled': 'drl'}
        for i in citing_types:
            relabel = dict_citings[i]
            self.dx_dict[f"""{relabel}_df"""], self.dx_dict_spec_depths[
                f"""{relabel}_df"""], self.conv_angle = self.reprocess_survey(survey_dx, relabel, i, well_elevation,
                                                                              north_ref)
        self.survey_parameters["conv_angle"] = self.conv_angle

    def reprocess_survey(self, survey_dx, relabel, i, well_elevation, north_ref):
        sot = f"""{relabel}_df"""
        survey_dx = survey_dx[
            ['measured_depth', 'inclination', 'azimuth', 'CitingType', 'SurfaceLatitude', 'SurfaceLongitude']]
        setattr(self, f"""survey_dx_{relabel}""", IndividualSurvey(survey_dx, i))
        object_dx = getattr(self, f"survey_dx_{relabel}")
        starting_point = (object_dx.surf_lat, object_dx.surf_lon)
        setattr(self, sot, SurveyProcess(df_referenced=object_dx.df,
                                         elevation=float(well_elevation),
                                         north_ref=north_ref,
                                         starting_point=starting_point))
        output = getattr(self, sot)
        bhl_true = output.true_dx.iloc[-1][['measured_depth', 'inclination', 'azimuth']]
        bhl_true['Point'] = 'BHL'
        bhl_true['type'] = f"{sot}_true_dx"
        output.find_kop_and_lp_process(output.true_dx)
        lp_true = output.find_landing_point(output.true_dx)
        try:
            kop_true = output.find_kick_off_point(output.true_dx)

        except IndexError:
            kop_result = main_project_detect_kop.determine_kickoff_point(output.true_dx)
            kop_true = output.true_dx[output.true_dx['measured_depth'] == kop_result['kop_md']][
                ['measured_depth', 'inclination', 'azimuth']]
            kop_true['Point'] = 'KOP'
        kop_true['type'] = f"{sot}_true_dx"
        lp_true['type'] = f"{sot}_true_dx"
        bhl_grid = output.grid_dx.iloc[-1][['measured_depth', 'inclination', 'azimuth']]
        bhl_grid['Point'] = 'BHL'
        bhl_grid['type'] = f"{sot}_grid_dx"
        lp_grid = output.find_landing_point(output.grid_dx)
        try:
            kop_grid = output.find_kick_off_point(output.grid_dx)
        except IndexError:
            kop_result = main_project_detect_kop.determine_kickoff_point(output.grid_dx)
            kop_grid = output.grid_dx[output.grid_dx['measured_depth'] == kop_result['kop_md']][
                ['measured_depth', 'inclination', 'azimuth']]
            kop_grid['Point'] = 'KOP'
        kop_grid['type'] = f"{sot}_grid_dx"
        lp_grid['type'] = f"{sot}_grid_dx"

        spec_vals = pd.concat([kop_true, kop_grid, lp_true, lp_grid])
        return output, spec_vals, output.conv_angle


class IndividualSurvey:
    def __init__(self, df, label):
        self.surf_lat, self.surf_lon = None, None
        self.label = label
        df = df[df['CitingType'] == label].reset_index(drop=True)
        if not df.empty:
            self.df = self.assign_new_variables(df)
            pass

    def assign_new_variables(self, df):
        df = df.sort_values('measured_depth', ascending=True)
        surf_lat, surf_lon = df['SurfaceLatitude'].iloc[0], \
            df['SurfaceLongitude'].iloc[0]
        if df['measured_depth'].iloc[0] != 0 and df['measured_depth'].iloc[1] - 0 > 500:
            new_row = pd.DataFrame({'measured_depth': [0],
                                    'inclination': [0],
                                    'azimuth': [0],
                                    'CitingType': self.label,
                                    'SurfaceLatitude': df['SurfaceLatitude'].iloc[0],
                                    'SurfaceLongitude': df['SurfaceLongitude'].iloc[0],
                                    })
            df = pd.concat([new_row, df]).reset_index(drop=True)

        self.surf_lat, self.surf_lon = surf_lat, surf_lon
        return df
