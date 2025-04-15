from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, select, and_, text
from shapely.geometry import Point, LineString, MultiPoint, Polygon
import welleng as we
from datetime import date
import datetime
import openpyxl
from openpyxl.styles import Font
import copy
from PyQt5.QtWidgets import QHeaderView, QAbstractItemView
from PyQt5.QtGui import QStandardItem
from shapely.geometry import Point, LineString, MultiPoint, Polygon

import collections.abc

import pandas as pd
import utm
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from functools import partial
import numpy as np
from datetime import date

# hyper needs the four following aliases to be done manually.
collections.Iterable = collections.abc.Iterable
collections.Mapping = collections.abc.Mapping
collections.MutableSet = collections.abc.MutableSet
collections.MutableMapping = collections.abc.MutableMapping
from WCR import *
from PyQt5.QtWidgets import QApplication, QMainWindow, QTableWidgetItem, QApplication, QWidget, QVBoxLayout, \
    QPushButton, QRadioButton, QButtonGroup, QMessageBox, QLabel, QVBoxLayout, QScrollArea
import ModuleAgnostic as ma
import os
from openpyxl import load_workbook, Workbook
import collections.abc
import pandas as pd
import utm
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
import numpy as np

# hyper needs the four following aliases to be done manually.
collections.Iterable = collections.abc.Iterable
collections.Mapping = collections.abc.Mapping
collections.MutableSet = collections.abc.MutableSet
collections.MutableMapping = collections.abc.MutableMapping
from PyQt5.QtWidgets import QMessageBox, QLabel, QScrollArea, QHeaderView, QAbstractItemView
import ModuleAgnostic as ma
import os
import math
from PyQt5.QtGui import QStandardItem, QStandardItemModel


# noinspection PyTestUnpassedFixture
class WCR_Main:
    def __init__(self, df, ui, db, loc_df, spec_surveys, north_ref):
        self.perf_date = None
        self.perf_mods = None
        self.wcr_result_df = None
        filtered_dict = {k: v for k, v in df.items() if "drl" in k}
        self._sundries_df = None
        self.df = filtered_dict
        self.spec_surveys = {k: v for k, v in spec_surveys.items() if "drl" in k}
        self.ui = ui
        self.db = db
        self.loc_df = loc_df
        self.north_ref = north_ref
        self.api = self.ui.well_api_val.text()
        self.lateral = self.ui.lateral_name_line_edit.text()
        self.ui.prev_depth_line.textChanged.connect(self.interpolation_table_process)
        self.ui.prev_ns_line.textChanged.connect(self.interpolation_table_process)
        self.ui.prev_ew_line.textChanged.connect(self.interpolation_table_process)
        self.ui.cur_depth_line.textChanged.connect(self.interpolation_table_process)
        self.ui.next_depth_line.textChanged.connect(self.interpolation_table_process)
        self.ui.next_ns_line.textChanged.connect(self.interpolation_table_process)
        self.ui.next_ew_line.textChanged.connect(self.interpolation_table_process)
        self.report_box_model = QStandardItemModel()
        self.ui.logs_report_box.setModel(self.report_box_model)
        self.ui.logs_report_box.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ui.find_submitted_logs_button.pressed.connect(self.create_well_logs_list)
        self.ui.find_submitted_sundries_button.pressed.connect(self.create_sundries_list)
        self.ui.sundries_combo_box.activated.connect(self.sundries_combo_box_process)
        self.ui.load_plat_button.pressed.connect(self.present_plat_data)
        self.ui.collect_survey_push.pressed.connect(self.process_survey_data)
        self.ui.update_personal_wcr.pressed.connect(self.update_personal_excel)
        self.ui.wcr_survey_northref_buttons.buttonClicked.connect(self.process_survey_data)
        self.ui.pushButton.pressed.connect(self.generate_excel_file)
        self.coords_wcr_model = QStandardItemModel()
        self.ui.display_table_utm_locs.setModel(self.coords_wcr_model)
        self.ui.display_table_utm_locs.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.process_wcr()
        self.ui.survey_north_ref_combo.clear()
        self.ui.plat_north_ref_combo.clear()
        self.ui.sundries_combo_box.clear()
        self.ui.sundries_report_box.setText('')
        self.reset_check_boxes()
        perf_mods, self.perf_date = self.wcr_perf_mods()
        self.ui.perf_interval_top.setText(str(perf_mods[0]))
        self.ui.perf_interval_bottom.setText(str(perf_mods[1]))
        one_letter_id = self.north_ref[0].upper()
        if one_letter_id == 'T':
            self.ui.wcr_survey_northref_buttons.button(-2).setChecked(True)
        elif one_letter_id == 'G':
            self.ui.wcr_survey_northref_buttons.button(-3).setChecked(True)

    def reset_check_boxes(self):
        self.ui.action_taken_checkbox.setChecked(False)
        self.ui.comp_sum_checkbox.setChecked(False)
        self.ui.drill_sum_checkbox.setChecked(False)
        self.ui.cement_log_checkbox.setChecked(False)
        self.ui.logs_included_checkbox.setChecked(False)
        self.ui.asdrilled_excel_checkbox.setChecked(False)
        self.ui.action_taken__utms_checkbox.setChecked(False)
        self.ui.action_taken_footages_checkbox.setChecked(False)
        self.ui.action_taken_perfs_checkbox.setChecked(False)
        self.ui.action_taken_depths_checkbox.setChecked(False)
        self.ui.action_taken_other_lineedit.setText("")
        self.ui.action_taken_other_checkbox.setChecked(False)

    def savedPopup(self):
        choice = QMessageBox.warning(None, "Attention", "Data saved!", QMessageBox.Ok)

    def get_wcr_info(self):
        query = f"""select wi.*, dsh.OperatorName, dsh.WellNameNumber, dsh.APINumber, LateralName as ConstructKey
        from tblAPDWCRWellInfo wi
        join [dbo].tblAPD ta on wi.APDNo = ta.APDNo
        JOIN DirectionalSurveyHeader dsh ON LEFT(ta.API_WellNo, 10) = dsh.APINumber where ta.API_WellNo = '{self.api}{self.lateral}' and dsh.LateralName = '{self.lateral}'"""
        # wcr_info = pd.read_sql_query(query, self.engine)
        wcr_info = self.db.query_to_dataframe(query)

        wcr_info = wcr_info.drop_duplicates(keep="first")
        return wcr_info

    def get_wcr_casing(self):
        query = f"""select Feature, [Top], Bottom, Diam, [Weight], Grade,
       [Connection Type], [Cement Top], [Cement Bottom], [Cement Type],
       Sacks, Yield, [Cement Weight]
        from well w
        inner join construct c on w.pkey=c.WellKey
        inner join vwDM_ConstructCasingCement vw on c.PKey = vw.PKey
        WHERE w.WellID = {self.api} and [Feature] is not Null"""
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

    def generate_excel_file(self):
        wcr_info = self.get_wcr_info()
        wcr_casing = self.get_wcr_casing()

        model = self.ui.display_table_utm_locs.model()

        test = [[model.data(model.index(row, column)) for column in range(model.columnCount())] for row in
                range(model.rowCount())]
        if not test:
            self.process_survey_data()
            self.run_excel_process(wcr_info, wcr_casing)
        else:
            self.run_excel_process(wcr_info, wcr_casing)

    def run_excel_process(self, wcr_info, wcr_casing):
        bold_font = Font(bold=True)
        wcr_info['ModifyDate'] = pd.to_datetime(wcr_info['ModifyDate'], format='%m/%d/%Y', errors='coerce')
        labels = ['WellName', 'API', 'Operator', 'ConstructKey' 'WellType', 'SpudDate', 'RotaryRigDate',
                  'TDReachedDate', 'CompletedOrAbandonedDate']
        survey_scale = ['measured_depth', 'tvd', 'easting', 'northing', 'FNL', 'FSL', 'FEL', 'FWL', 'Section',
                        'Township', 'Township_Direction', 'Range', 'Range_Direction', 'Baseline']
        survey_depths = ['SHL', 'Control_Point', 'Frac_Start', 'Frac_End', 'BHL']
        survey_casing = wcr_casing.columns

        used_wcr = self.wcr_result_df[survey_scale]
        label_cells = ['1', '2', '3', '4', '5', '6', '7', '8']
        dx_data_header_cells = 'ABCDEFGHIJKLMNOPQRSTUV'
        max_row = 0
        wb = Workbook()
        sheet = wb.active
        sheet.column_dimensions['A'].width = 30
        sheet.column_dimensions['B'].width = 15
        info_vals = [wcr_info['WellNameNumber'].iloc[0],
                     wcr_info['APINumber'].iloc[0],
                     wcr_info['OperatorName'].iloc[0],
                     wcr_info['ConstructKey'].iloc[0],
                     wcr_info['WellType'].iloc[0],
                     wcr_info['SpudRigDate'].iloc[0].strftime('%Y-%m-%d'),
                     wcr_info['RotaryRigDate'].iloc[0].strftime('%Y-%m-%d'),
                     wcr_info['TDReachedDate'].iloc[0].strftime('%Y-%m-%d'),
                     wcr_info['CompletedOrAbandonedDate'].iloc[0].strftime('%Y-%m-%d')]
        for i in range(len(labels)):
            sheet["A" + label_cells[i]] = labels[i]
            sheet["B" + label_cells[i]] = info_vals[i]
        for i in range(len(survey_scale)):
            sheet[dx_data_header_cells[i + 1] + "10"] = survey_scale[i]
        used_wcr[['FNL', 'FSL', 'FEL', 'FWL']] = used_wcr[['FNL', 'FSL', 'FEL', 'FWL']].round(0)
        used_wcr = used_wcr.drop_duplicates(keep='first')
        for idx, row in used_wcr.iterrows():
            sheet['A' + str(11 + idx)] = survey_depths[idx]
            max_row = 11 + idx
            for i in range(len(survey_scale)):
                sheet[dx_data_header_cells[i + 1] + str(max_row)] = row[i]

        """Assemble the casing data"""
        for i in range(len(survey_casing)):
            sheet[dx_data_header_cells[i] + str(max_row + 2)] = survey_casing[i]
        for idx, row in wcr_casing.iterrows():
            for i in range(len(row)):
                sheet[dx_data_header_cells[i] + str(max_row + 3 + idx)] = row[i]

        sheet['E1'] = 'Perf Top'
        sheet['F1'] = 'Perf Bottom'
        sheet['G1'] = 'Perf Date'
        sheet['E1'].font = bold_font
        sheet['F1'].font = bold_font
        sheet['G1'].font = bold_font

        sheet['E2'] = self.perf_mods[0]
        sheet['F2'] = self.perf_mods[1]
        sheet['G2'] = self.perf_date

        for cell in sheet[10]:
            cell.font = bold_font
        for cell in sheet[max_row + 2]:
            cell.font = bold_font
        for cell in sheet['A']:
            cell.font = bold_font

        wb_name = "{}_{}_WCR.xlsx".format(wcr_info['WellNameNumber'].iloc[0], wcr_info['APINumber'].iloc[0])
        wb_name = wb_name.replace(" ", "_").replace("/", "_")
        wb.save(wb_name)
        self.savedPopup()

    def update_personal_excel(self):
        def get_all_edits():
            utms_str = "utms" if self.ui.action_taken__utms_checkbox.isChecked() else ""
            footages_str = "footages" if self.ui.action_taken_footages_checkbox.isChecked() else ""
            perfs_str = "perfs" if self.ui.action_taken_perfs_checkbox.isChecked() else ""
            depths_str = "depths" if self.ui.action_taken_depths_checkbox.isChecked() else ""
            other_str = self.ui.action_taken_other_lineedit.text() if self.ui.action_taken_other_checkbox.isChecked() else ""
            return "/".join(filter(None, [utms_str, footages_str, perfs_str, depths_str, other_str]))

        file = r"TrackingWCR.xlsx"
        data = self.get_wcr_person_db_update()
        wb = openpyxl.load_workbook(file)
        sheet = wb.active
        values = [cell.value for cell in sheet['E']]
        try:
            api_number = int(float(data['APINumber'].iloc[0]))
        except IndexError:
            api_number = int(float(self.api))
        if api_number in values:
            api_index = values.index(api_number) + 1
            max_row = api_index
        else:
            max_row = sheet.max_row + 1
        date_filed = data['SubmitDate'].iloc[0]
        counted_returns = self.ui.no_returns_box.text()
        ret_count = 0 if counted_returns == "" else counted_returns
        sundry_number = data['SundryNo'].iloc[0]
        well_name = data['WellNameNumber'].iloc[0]
        date_processed = date.today()
        date_as_datetime = datetime.datetime.combine(date_processed, datetime.time())
        days_average = int(abs(date_filed - date_as_datetime).days)
        company = data['OperatorName'].iloc[0]
        action_taken = "y" if self.ui.action_taken_checkbox.isChecked() else "n"
        comp_sum = "y" if self.ui.comp_sum_checkbox.isChecked() else "n"
        drilling_sum = "y" if self.ui.drill_sum_checkbox.isChecked() else "n"
        cement_log = "y" if self.ui.cement_log_checkbox.isChecked() else "n"
        logs = "y" if self.ui.logs_included_checkbox.isChecked() else "n"
        bhl_processed = "y"
        as_drilled_excel = "y" if self.ui.asdrilled_excel_checkbox.isChecked() else "n"
        edited_wcr = "y"
        all_edits = get_all_edits()
        all_data = [days_average, date_filed.strftime("%m/%d/%Y"), ret_count, sundry_number, api_number,
                    well_name, date_processed.strftime("%m/%d/%Y"), company, action_taken, comp_sum, drilling_sum,
                    cement_log, logs, bhl_processed, as_drilled_excel, edited_wcr, all_edits]
        letters = "abcdefghijklmnopqrstuvwxyz"
        for i in range(len(all_data)):
            sheet[letters[i] + str(max_row)] = all_data[i]
        wb.save(file)
        wb.close()
        self.savedPopup()

    def get_wcr_person_db_update(self):
        query = f"""select wi.SundryNo, dsh.OperatorName, dsh.WellNameNumber, dsh.APINumber, dsh.LateralName as ConstructKey, tas.SubmitDate
        from tblAPDWCRWellInfo wi
        join [dbo].tblAPD ta on wi.APDNo = ta.APDNo
        join [dbo].[tblAPDSundry] tas on ta.API_WellNo = tas.APINO
        JOIN DirectionalSurveyHeader dsh ON LEFT(ta.API_WellNo, 10) = dsh.APINumber where dsh.APINumber = {self.api} and dsh.LateralName = '{self.lateral}'
        order BY tas.SubmitDate"""
        wcr_info = self.db.query_to_dataframe(query)

        wcr_info = wcr_info.drop_duplicates(keep="first")
        wcr_info = wcr_info.tail(1)
        return wcr_info

    def wcr_logs_sql(self):
        query = f"""select w.WellID, cl.LogType, cl.ReceivedDate
            from well w
            inner join construct c on w.pkey=c.WellKey
            inner join ConstructLog cl on cl.ConstructKey = c.PKey
            where w.WellID = '{self.api}'
            order by cl.ReceivedDate"""
        df = self.db.query_to_dataframe(query)
        return df

    def wcr_sundries_sql(self):
        query = f"""select APINO, TypeSubmission, SubmitDate, Operations
                    from tblAPDSundry
        where APINO = '{self.api}0000'
        order by SubmitDate"""
        df = self.db.query_to_dataframe(query)
        df['APINO'] = df['APINO'].astype(str).apply(lambda row: row[:10])
        df['SubmitDate'] = df['SubmitDate'].astype(str).apply(lambda row: row[:10])
        return df

    #collect survey data process
    def process_survey_data(self):
        def transform_string(s):
            section = str(int(s[:2]))
            township = str(int(s[2:4]))
            township_dir = s[4]
            rng = str(int(s[5:7]))
            rng_dir = s[7]
            baseline = s[-1]
            return {
                'Section': section,
                'Township': township,
                'Township_Direction': township_dir,
                'Range': rng,
                'Range_Direction': rng_dir,
                'Baseline': baseline
            }

        wcr_df, kop = self.return_button_data()
        perf_mods = [float(self.ui.perf_interval_top.text()), float(self.ui.perf_interval_bottom.text())]

        for i in perf_mods:
            wcr_df = self.insert_row_at_md(wcr_df, i)
        new_columns = wcr_df['Conc'].apply(transform_string).apply(pd.Series)
        wcr_df = wcr_df.join(new_columns)
        init = [kop['measured_depth'].iloc[0]]
        self.perf_mods = perf_mods
        used_depths = perf_mods + init
        perf_mods = wcr_df[wcr_df['measured_depth'].isin(used_depths)]
        wcr_result_df = self.process_survey_data_misc(kop, perf_mods, wcr_df)
        self.wcr_result_df = wcr_result_df
        self.data_writer_process(wcr_result_df)
        self.set_shl_bhl_data(wcr_df)
        self.write_coords(wcr_result_df)

    def insert_row_at_md(self, df, target_md):
        # Ensure the dataframe is sorted by MeasuredDepth
        df = df.sort_values('measured_depth').reset_index(drop=True)

        # Find the index where the new row should be inserted
        insert_index = df['measured_depth'].searchsorted(target_md)

        if insert_index == 0:
            return df
            # raise ValueError("Target MeasuredDepth is below the range of existing data.")

        if insert_index == len(df):
            # Extrapolate using the last two rows
            lower_row = df.iloc[-2]
            upper_row = df.iloc[-1]
        else:
            # Interpolate using the surrounding rows
            lower_row = df.iloc[insert_index - 1]
            upper_row = df.iloc[insert_index]

        # Calculate the interpolation factor

        # Initialize new row with target_md
        new_row = {'measured_depth': target_md}

        # Process each column
        for col in df.columns:
            if col == 'measured_depth':
                continue

            # Check if column contains strings (object dtype)
            if df[col].dtype == 'object':
                # Use the value from the lower row for string columns
                new_row[col] = lower_row[col]
            else:
                try:
                    # Attempt interpolation for numeric columns
                    new_row[col] = np.interp(target_md,
                                             [lower_row['measured_depth'], upper_row['measured_depth']],
                                             [lower_row[col], upper_row[col]])
                except (TypeError, ValueError):
                    # If interpolation fails, use the value from the lower row
                    new_row[col] = lower_row[col]

        # Convert to Series and insert the new row
        new_row = pd.Series(new_row)
        df = pd.concat([df.iloc[:insert_index], pd.DataFrame([new_row]), df.iloc[insert_index:]]).reset_index(drop=True)

        return df

    def data_writer_process(self, wcr_result_df):
        baseline_dict = {'T': 'True', 'G': 'Grid'}
        asdrilled_survey_data = [
            [self.ui.bhl1_depth, self.ui.bhl1_ns_offset, self.ui.bhl1_ns_offset_combo, self.ui.bhl1_ew_offset,
             self.ui.bhl1_ew_offset_combo],
            [self.ui.bhl1_depth_2, self.ui.bhl1_ns_offset_2, self.ui.bhl1_ns_offset_combo_2, self.ui.bhl1_ew_offset_2,
             self.ui.bhl1_ew_offset_combo_2],
            [self.ui.bhl2_depth, self.ui.bhl2_ns_offset, self.ui.bhl2_ns_offset_combo, self.ui.bhl2_ew_offset,
             self.ui.bhl2_ew_offset_combo],
            [self.ui.bhl2_depth_2, self.ui.bhl2_ns_offset_2, self.ui.bhl2_ns_offset_combo_2, self.ui.bhl2_ew_offset_2,
             self.ui.bhl2_ew_offset_combo_2]]
        one_letter_id = self.north_ref[0].upper()
        self.ui.survey_north_ref_combo.setCurrentText(baseline_dict[one_letter_id])


    def process_survey_data_misc(self, kop, perf_mods, wcr_df):

        last_line = wcr_df.tail(1)
        first_line = wcr_df.head(1)
        first_and_last_df = pd.concat([first_line, last_line], ignore_index=True)
        wcr_result_df = pd.concat([perf_mods, first_and_last_df], ignore_index=True).sort_values(
            'measured_depth').reset_index(drop=True)

        return wcr_result_df

    def return_button_data(self):
        active_button_id = self.ui.wcr_survey_northref_buttons.checkedId()
        used_spec_survey = self.spec_surveys['drl_df']
        if active_button_id == -2:
            wcr_df = self.df['drl_df_true_dx'].clearance_data
            kop = used_spec_survey[
                (used_spec_survey['Point'] == 'KOP') & (used_spec_survey['type'] == 'drl_df_true_dx')]
        else:
            wcr_df = self.df['drl_df_grid_dx'].clearance_data
            kop = used_spec_survey[
                (used_spec_survey['Point'] == 'KOP') & (used_spec_survey['type'] == 'drl_df_grid_dx')]
        return wcr_df, kop

    def set_shl_bhl_data(self, wcr_df):
        shl_row = wcr_df.head(1)
        bhl_row = wcr_df.tail(1)
        latlon_shl = utm.to_latlon(shl_row['easting'], shl_row['northing'], 12, 'T')
        latlon_bhl = utm.to_latlon(bhl_row['easting'], bhl_row['northing'], 12, 'T')
        self.ui.shl_lat.setText(str(abs(round(float(latlon_shl[0].iloc[0]), 5))))
        self.ui.shl_lon.setText(str(abs(round(float(latlon_shl[1].iloc[0]), 5))))
        self.ui.bhl_lat_2.setText(str(abs(round(float(latlon_bhl[0].iloc[0]), 5))))
        self.ui.bhl_lon_2.setText(str(abs(round(float(latlon_bhl[1].iloc[0]), 5))))

    def write_coords(self, df):
        self.coords_wcr_model.setRowCount(0)  # Clear existing rows efficiently
        self.ui.display_table_utm_locs.setModel(self.coords_wcr_model)
        self.ui.display_table_utm_locs.setUpdatesEnabled(False)
        used_dataframe = df[['measured_depth', 'tvd', 'easting', 'northing', 'FNL', 'FSL', 'FEL', 'FWL']]
        columns = ['measured_depth', 'tvd', 'easting', 'northing', 'FNL', 'FSL', 'FEL', 'FWL']
        used_dataframe = used_dataframe.drop_duplicates(keep="first")
        for i, row in used_dataframe.iterrows():
            row_data = [str(int(round(r, 0))) for r in row]
            items = [QStandardItem(item) for item in row_data]
            for column_index, value in enumerate(row):
                items[column_index].setData(int(round(value, 0)))
            self.coords_wcr_model.appendRow(items)
        self.coords_wcr_model.setHorizontalHeaderLabels(columns)
        # Configure the view settings after data insertion
        self.ui.display_table_utm_locs.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.display_table_utm_locs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.ui.display_table_utm_locs.verticalHeader().setVisible(False)
        self.ui.display_table_utm_locs.setShowGrid(True)

        # Re-enable updates and refresh the view
        self.ui.display_table_utm_locs.setUpdatesEnabled(True)
        self.ui.display_table_utm_locs.show()

    def wcr_perf_mods(self):
        try:
            sql_query = f"""select [Top], Bottom, [Perf Date]
                        from well w 
        				join construct c on w.PKey = c.WellKey  
                        join [dbo].[vwDM_ConstructPerf] cp on c.PKey = cp.PKey
                        where wellid = {self.api} and [Zone Type] = 'Perforations'"""
            tops = self.db.query_to_dataframe(sql_query)

            # tops = pd.read_sql_query(sql_query, self.engine)
            tops = tops.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
            perf_top = tops['Top'].values.tolist()[0]
            perf_bottom = tops['Bottom'].values.tolist()[0]
            perf_mods = [float(perf_top), float(perf_bottom)]
            perf_date = tops['Perf Date'].iloc[0]
        except IndexError:
            perf_mods = [0, 0]
            perf_date = "1/1/1900"
        return perf_mods, perf_date

    def process_wcr(self):
        self.setup_combo_boxes()

    def present_plat_data(self):
        wcr_tsr_db = self.loc_df
        self.ui.display_data.clear()
        sd = wcr_tsr_db[(wcr_tsr_db['zone_name'] == 'Surface Location')]
        td = wcr_tsr_db[(wcr_tsr_db['zone_name'] == 'Proposed Depth')]
        prod = wcr_tsr_db[(wcr_tsr_db['zone_name'] == 'Uppermost Producing')]
        baseline_dict = {'U': 'Uintah', 'S': 'Salt Lake'}
        # Convert and set planned_survey_data_fnsl
        planned_survey_data_fnsl = [[self.ui.shl_fnsl_data.setText(str(sd.iloc[0, 6])),
                                     self.ui.shl_fnsl_combo.setCurrentText(str(sd.iloc[0, 7]))],
                                    [self.ui.bhl1_fnsl_data.setText(str(prod.iloc[0, 6])),
                                     self.ui.bhl1_fnsl_combo.setCurrentText(str(prod.iloc[0, 7]))],
                                    [self.ui.bhl2_fnsl_data.setText(str(td.iloc[0, 6])),
                                     self.ui.bhl2_fnsl_combo.setCurrentText(str(td.iloc[0, 7]))]]

        # Convert and set planned_survey_data_fewl
        planned_survey_data_fewl = [[self.ui.shl_fewl_data.setText(str(sd.iloc[0, 8])),
                                     self.ui.shl_fewl_combo.setCurrentText(str(sd.iloc[0, 9]))],
                                    [self.ui.bhl1_fewl_data.setText(str(prod.iloc[0, 8])),
                                     self.ui.bhl1_fewl_combo.setCurrentText(str(prod.iloc[0, 9]))],
                                    [self.ui.bhl2_fewl_data.setText(str(td.iloc[0, 8])),
                                     self.ui.bhl2_fewl_combo.setCurrentText(str(td.iloc[0, 9]))]]

        # Convert and set tsr_data
        tsr_data = [[self.ui.shl_section.setText(str(sd.iloc[0, 0])),
                     self.ui.shl_township.setText(str(sd.iloc[0, 1])),
                     self.ui.shl_township_dir_combo.setCurrentText(str(sd.iloc[0, 2])),
                     self.ui.shl_range.setText(str(sd.iloc[0, 3])),
                     self.ui.shl_range_dir_combo.setCurrentText(str(sd.iloc[0, 4]))],
                    [self.ui.bhl1_section.setText(str(prod.iloc[0, 0])),
                     self.ui.bhl1_township.setText(str(prod.iloc[0, 1])),
                     self.ui.bhl1_township_dir_combo.setCurrentText(str(prod.iloc[0, 2])),
                     self.ui.bhl1_range.setText(str(prod.iloc[0, 3])),
                     self.ui.bhl1_range_dir_combo.setCurrentText(str(prod.iloc[0, 4]))],
                    [self.ui.bhl2_section.setText(str(td.iloc[0, 0])),
                     self.ui.bhl2_township.setText(str(td.iloc[0, 1])),
                     self.ui.bhl2_township_dir_combo.setCurrentText(str(td.iloc[0, 2])),
                     self.ui.bhl2_range.setText(str(td.iloc[0, 3])),
                     self.ui.bhl2_range_dir_combo.setCurrentText(str(td.iloc[0, 4]))]]
        self.ui.meridian_combo.setCurrentText(baseline_dict[sd['baseline'].values[0]])

    def create_well_logs_list(self):
        self.report_box_model.setRowCount(0)  # Clear existing rows efficiently
        self.ui.logs_report_box.setModel(self.report_box_model)
        self.ui.logs_report_box.setUpdatesEnabled(False)
        df = self.wcr_logs_sql()
        columns = df.columns
        if df.empty:
            self.report_box_model.setColumnCount(1)
            empty_item = QStandardItem("No logs found")
            self.report_box_model.appendRow([empty_item])
        else:
            for i, row in df.iterrows():
                items = [QStandardItem(str(item)) for item in row]
                for column_index, value in enumerate(row):
                    items[column_index].setData(value)
                self.report_box_model.appendRow(items)
            self.report_box_model.setHorizontalHeaderLabels(columns)

        self.ui.logs_report_box.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.logs_report_box.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.ui.logs_report_box.verticalHeader().setVisible(False)
        self.ui.logs_report_box.setShowGrid(True)

        # Re-enable updates and refresh the view
        self.ui.logs_report_box.setUpdatesEnabled(True)
        self.ui.logs_report_box.show()

    def create_sundries_list(self):
        df = self.wcr_sundries_sql()
        self.ui.sundries_combo_box.clear()
        self.set_sundries_df(df)
        for idx, row in df.iterrows():
            label = f"""{row['SubmitDate']} {row['TypeSubmission']}"""
            self.ui.sundries_combo_box.addItem(label)

    def set_sundries_df(self, value):
        self._sundries_df = value

    def sundries_combo_box_process(self):
        self.ui.sundries_report_box.clear()
        df_index = self._sundries_df.iloc[self.ui.sundries_combo_box.currentIndex()]['Operations']
        self.ui.sundries_report_box.setText(df_index)

    def setup_combo_boxes(self):
        # Define all options
        combo_options = {
            'north_ref': ['True', 'Grid'],
            'fnsl': ['FNL', 'FSL'],
            'fewl': ['FEL', 'FWL'],
            'ns': ['N', 'S'],
            'ew': ['E', 'W'],
            'meridian': ['Salt Lake', 'Uintah'],
            'directions': ['SE', 'NE', 'SW', 'NW']
        }

        # Group related combo boxes
        widget_groups = {
            'north_ref': [
                self.ui.plat_north_ref_combo,
                self.ui.survey_north_ref_combo
            ],
            'fnsl': [
                self.ui.shl_fnsl_combo,
                self.ui.bhl1_fnsl_combo,
                self.ui.bhl2_fnsl_combo
            ],
            'fewl': [
                self.ui.shl_fewl_combo,
                self.ui.bhl1_fewl_combo,
                self.ui.bhl2_fewl_combo
            ],
            'township_ns': [
                self.ui.shl_township_dir_combo,
                self.ui.bhl1_township_dir_combo,
                self.ui.bhl2_township_dir_combo
            ],
            'range_ew': [
                self.ui.shl_range_dir_combo,
                self.ui.bhl1_range_dir_combo,
                self.ui.bhl2_range_dir_combo
            ],
            'meridian': [
                self.ui.meridian_combo
            ],
            'ns_offset': [
                self.ui.bhl1_ns_offset_combo,
                self.ui.bhl1_ns_offset_combo_2,
                self.ui.bhl2_ns_offset_combo,
                self.ui.bhl2_ns_offset_combo_2
            ],
            'ew_offset': [
                self.ui.bhl1_ew_offset_combo,
                self.ui.bhl1_ew_offset_combo_2,
                self.ui.bhl2_ew_offset_combo,
                self.ui.bhl2_ew_offset_combo_2
            ],
            'directions': [
                self.ui.shl_to_bhl1_dir_combo,
                self.ui.bhl1_to_bhl2__dir_combo,
                self.ui.bhl_1_bearing_dir_ew_combo,
                self.ui.bhl_1_bearing_dir_ns_combo,
                self.ui.bhl_2_bearing_dir_ew_combo,
                self.ui.bhl_2_bearing_dir_ns_combo
            ]
        }

        # Populate all combo boxes
        for group_name, widgets in widget_groups.items():
            options = combo_options.get(group_name, [])
            if group_name in ['township_ns']:
                options = combo_options['ns']
            elif group_name in ['range_ew', 'ew_offset']:
                options = combo_options['ew']
            elif group_name in ['ns_offset']:
                options = combo_options['ns']

            for widget in widgets:
                widget.addItems(options)

    def interpolation_table_process(self):
        try:
            next_depth = float(self.ui.next_depth_line.text())
            next_ns = float(self.ui.next_ns_line.text())
            next_ew = float(self.ui.next_ew_line.text())
            prev_depth = float(self.ui.prev_depth_line.text())
            prev_ns = float(self.ui.prev_ns_line.text())
            prev_ew = float(self.ui.prev_ew_line.text())
            target_depth = float(self.ui.cur_depth_line.text())
            interpolated_ns = ((next_ns - prev_ns) / (next_depth - prev_depth)) * (target_depth - prev_depth) + prev_ns
            interpolated_ew = ((next_ew - prev_ew) / (next_depth - prev_depth)) * (target_depth - prev_depth) + prev_ew
            self.ui.cur_ns_line.setText((str(round(interpolated_ns, 2))))
            self.ui.cur_ew_line.setText((str(round(interpolated_ew, 2))))
        except ValueError:
            pass




