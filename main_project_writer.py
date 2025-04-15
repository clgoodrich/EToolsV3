import decimal
import pandas as pd
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QHeaderView, QAbstractItemView
import math
import numpy as np


def _isolate_footage_depths(survey, spec_data):
    depths_lst = {'kop': spec_data['measured_depth'].iloc[0], 'prod': spec_data['measured_depth'].iloc[1],
                  'bhl': survey['measured_depth'].iloc[-1]}
    reverse_map = {v: k for k, v in depths_lst.items()}
    dx_lst = survey[survey['measured_depth'].isin(depths_lst.values())]
    dx_lst['lbl'] = dx_lst['measured_depth'].map(reverse_map)
    df = dx_lst[['lbl', 'FNL', 'FSL', 'FEL', 'FWL', 'measured_depth', 'azimuth']]
    return df



class DataWriter:
    def __init__(self, ui, surveys, spec_surveys, parameters, plat_df):
        self.surveys = surveys
        self.spec_surveys = spec_surveys
        self.survey_parameters = parameters
        self.ui = ui
        self.dx_survey_model = QStandardItemModel()
        self.ui.dx_survey_table_mod.setModel(self.dx_survey_model)
        self.ui.dx_survey_table_mod.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dx_survey_model_footages = QStandardItemModel()
        self.ui.dx_survey_location_tableview.setModel(self.dx_survey_model_footages)
        self.ui.dx_survey_location_tableview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dx_survey_model_new_line = QStandardItemModel()
        self.ui.dx_survey_table_mod_new_md.setModel(self.dx_survey_model_new_line)
        self.ui.dx_survey_table_mod_new_md.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ui.dx_survey_kop_line.setText("")
        self.ui.dx_survey_prod_line.setText("")
        self.ui.dx_survey_bhl_line.setText("")
        self.ui.dx_survey_north_ref_line.setText("")
        self.ui.dx_survey_mag_dec_line.setText("")
        self.ui.dx_survey_conv_angle_line.setText("")
        self.ui.dx_survey_pro_azi_line.setText("")

    def set_clear_survey(self, data):
        self.surveys = data

    def set_spec_surveys(self, data):
        self.spec_surveys = data

    def survey_writer(self, ui, survey_label):

        survey = self.surveys[survey_label].clearance_data
        spec_id = survey_label[:6]
        spec_survey_found = self.spec_surveys[spec_id]
        spec_data = spec_survey_found[spec_survey_found['type'] == survey_label]
        self.write_survey_to_table(survey, ui)
        footage_lst = _isolate_footage_depths(survey, spec_data)
        self.write_significant_depths_to_line_edits(ui, self.survey_parameters, footage_lst)
        self.write_clearance_footages(footage_lst, ui)

    def write_survey_to_table(self, survey, ui):
        self.ui.shl_lat_easting.setText("")
        self.ui.shl_lon_northing.setText("")
        self.dx_survey_model.setRowCount(0)  # Clear existing rows efficiently
        self.ui.dx_survey_table_mod.setModel(self.dx_survey_model)
        self.ui.dx_survey_table_mod.setUpdatesEnabled(False)
        survey = survey.drop(columns=['point_index', 'feature'])
        for col in ['azimuth', 'inclination']:
            survey[col] = np.degrees(survey[col])

        data = survey.values.tolist()
        self.dx_survey_model.setRowCount(len(data))
        for row_idx, row in enumerate(data):
            for col_idx, value in enumerate(row):
                try:
                    num_places_decimal = abs(decimal.Decimal(str(value)).as_tuple().exponent)
                    num_places_whole = len(str(int(value)))
                    if num_places_whole + num_places_decimal > 10:
                        if num_places_whole > 2:
                            value = round(value, 4)
                        else:
                            value = f'{value:.8g}'
                except (TypeError, decimal.InvalidOperation):
                    pass
                item = QStandardItem(str(value))
                # Optionally, set additional data or flags here
                self.dx_survey_model.setItem(row_idx, col_idx, item)
        columns = survey.columns.values
        self.dx_survey_model.setHorizontalHeaderLabels(columns)
        # Configure the view settings after data insertion
        self.ui.dx_survey_table_mod.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_survey_table_mod.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.ui.dx_survey_table_mod.verticalHeader().setVisible(False)
        self.ui.dx_survey_table_mod.setShowGrid(True)

        # Re-enable updates and refresh the view
        self.ui.dx_survey_table_mod.setUpdatesEnabled(True)
        self.ui.dx_survey_table_mod.show()
        first_pt = survey.head(1)
        self.ui.shl_lat_easting.setText(str(first_pt['easting'].iloc[0]))
        self.ui.shl_lon_northing.setText(str(first_pt['northing'].iloc[0]))
        self.ui.dx_survey_table_mod.viewport().update()

    def write_new_survey_line_to_display(self, survey, md, row_position=None):
        self.dx_survey_model_new_line.setRowCount(0)  # Clear existing rows efficiently
        self.ui.dx_survey_table_mod_new_md.setModel(self.dx_survey_model_new_line)
        self.ui.dx_survey_table_mod_new_md.setUpdatesEnabled(False)
        used_data = survey[survey['measured_depth'] == md]
        used_data = used_data.drop(columns=['point_index', 'feature'])
        items = [QStandardItem(str(item)) for item in used_data.iloc[0].tolist()]
        for k, value in enumerate(used_data.iloc[0]):
            try:
                num_places_decimal = abs(decimal.Decimal(str(value)).as_tuple().exponent)
                num_places_whole = len(str(int(value)))
                if num_places_whole + num_places_decimal > 10:
                    if num_places_whole > 2:
                        value = round(value, 4)
                    else:
                        value = f'{value:.8g}'

            except (TypeError, decimal.InvalidOperation):
                pass
            items[k].setData(str(value))
        self.dx_survey_model_new_line.appendRow(items)

        columns = used_data.columns.values
        self.dx_survey_model_new_line.setHorizontalHeaderLabels(columns)
        # Configure the view settings after data insertion
        self.ui.dx_survey_table_mod_new_md.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_survey_table_mod_new_md.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.ui.dx_survey_table_mod_new_md.verticalHeader().setVisible(False)
        self.ui.dx_survey_table_mod_new_md.setShowGrid(True)

        # Re-enable updates and refresh the view
        self.ui.dx_survey_table_mod_new_md.setUpdatesEnabled(True)
        self.ui.dx_survey_table_mod_new_md.show()

    def write_significant_depths_to_line_edits(self, ui, param, footage_lst):
        self.ui.dx_survey_kop_line.setText("")
        self.ui.dx_survey_prod_line.setText("")
        self.ui.dx_survey_bhl_line.setText("")
        self.ui.dx_survey_north_ref_line.setText("")
        self.ui.dx_survey_mag_dec_line.setText("")
        self.ui.dx_survey_conv_angle_line.setText("")
        self.ui.dx_survey_pro_azi_line.setText("")

        depths_str_lst = ['kop', 'prod', 'bhl']
        footage_lst['lbl'] = pd.Categorical(footage_lst['lbl'], categories=depths_str_lst, ordered=True)
        columns = footage_lst['lbl'].unique()
        for i in columns:
            used_line_edit = getattr(self.ui, f"dx_survey_{i}_line")
            md_val = footage_lst[footage_lst['lbl'] == i]['measured_depth'].iloc[0]
            used_line_edit.setText(str(md_val))
        self.ui.dx_survey_north_ref_line.setText(param['north_ref'])
        self.ui.dx_survey_conv_angle_line.setText(str(round(param['conv_angle'], 4)))
        self.ui.dx_survey_pro_azi_line.setText(str(round(math.degrees(footage_lst['azimuth'].iloc[-1]), 3)))

    def write_clearance_footages(self, footage_lst, ui):
        footage_lst = footage_lst.drop(columns=['measured_depth', 'azimuth'])
        # Block signals and prevent the view from updating until data is fully loaded
        self.ui.dx_survey_location_tableview.setUpdatesEnabled(False)
        self.dx_survey_model_footages.setRowCount(0)  # Clear existing rows efficiently
        self.ui.dx_survey_location_tableview.setModel(self.dx_survey_model_footages)
        data = footage_lst.values.tolist()
        self.dx_survey_model_footages.setRowCount(len(data))

        for row_idx, row in enumerate(data):
            for col_idx, value in enumerate(row):
                if col_idx != 0:
                    item = QStandardItem(str(round(float(value), 2)))
                else:
                    item = QStandardItem(str(value))
                self.dx_survey_model_footages.setItem(row_idx, col_idx, item)

        columns = footage_lst.columns.values
        self.dx_survey_model_footages.setHorizontalHeaderLabels(columns)
        self.ui.dx_survey_location_tableview.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_survey_location_tableview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_survey_location_tableview.verticalHeader().setVisible(False)
        self.ui.dx_survey_location_tableview.setShowGrid(True)
        self.ui.dx_survey_location_tableview.setUpdatesEnabled(True)
        self.ui.dx_survey_location_tableview.show()
