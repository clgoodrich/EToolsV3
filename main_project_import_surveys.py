import csv
import sys
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LTPage, LTChar, LTAnno, LAParams, LTTextBox, LTTextLine
from pdfminer.pdfpage import PDFPage
from shapely.geometry import Point, Polygon
import ModuleAgnostic as ma
import sqlite3
import statistics as st
from itertools import chain
from PyQt5.QtWidgets import QMainWindow, QWidget, QApplication, QFileDialog, QTableView, QProgressDialog, QVBoxLayout
import os
import regex as re
import pandas as pd
import re
import utm
from PyQt5.QtCore import QAbstractTableModel, Qt
import numpy as np
from sklearn.cluster import OPTICS
import numpy as np
from scipy.spatial import Delaunay


class PandasModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self._data.columns)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]
            return str(value)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._data.columns[section])
            if orientation == Qt.Vertical:
                return str(self._data.index[section])
        return None


class DataFrameViewer(QMainWindow):
    def __init__(self, df, title="DataFrame Viewer"):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(800, 600)

        # Create the main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Create table view
        table_view = QTableView()
        model = PandasModel(df)
        table_view.setModel(model)

        # Adjust table properties
        table_view.horizontalHeader().setStretchLastSection(True)
        table_view.horizontalHeader().setSectionsMovable(True)
        table_view.verticalHeader().setSectionsMovable(True)
        table_view.setSortingEnabled(True)

        layout.addWidget(table_view)


class PDFPageDetailedAggregator(PDFPageAggregator):
    def __init__(self, rsrcmgr, pageno=1, laparams=None):
        PDFPageAggregator.__init__(self, rsrcmgr, pageno=pageno, laparams=laparams)
        self.rows = []
        self.page_number = 0

    def receive_layout(self, ltpage):
        def render(item, page_number):
            if isinstance(item, LTPage) or isinstance(item, LTTextBox):
                for child in item:
                    render(child, page_number)
            elif isinstance(item, LTTextLine):
                child_str = ''
                for child in item:
                    if isinstance(child, (LTChar, LTAnno)):
                        child_str += child.get_text()
                child_str = ' '.join(child_str.split()).strip()
                if child_str:
                    row = (page_number, item.bbox[0], item.bbox[1], item.bbox[2], item.bbox[3],
                           child_str)  # bbox == (x1, y1, x2, y2)
                    self.rows.append(row)
                for child in item:
                    render(child, page_number)
            return

        render(ltpage, self.page_number)
        self.page_number += 1
        self.rows = sorted(self.rows, key=lambda x: (x[0], -x[2]))
        self.result = ltpage


class SurveyImporter:
    def __init__(self):
        # self.well_name = None
        self.api = None
        self.db = None
        self.file_path = None
        # Create the thread as an instance variable

    def load_and_process_data(self, label, db, api, file_path_dict):
        # self.well_name = name
        self.db = db
        self.api = api
        used_file = file_path_dict[label]
        _, extension = os.path.splitext(used_file)
        extension = extension.lower()
        df, north_ref, extra_plats = pd.DataFrame(), "", None
        if extension == '.pdf':
            try:
                return self.process_pdf_data(used_file, label)
            except NameError as nm:
                pass
        elif extension == '.csv':
            return self.process_table_data(used_file, label, 'csv')
        elif extension in ['.xls', '.xlsx', '.xlsm', '.xlsb']:
            return self.process_table_data(used_file, label, 'xl')
        else:
            return df, north_ref, extra_plats

    def process_table_data(self, directory, label, table_doc_type):
        header_dict = {}
        north_ref_dict = {'t': 'true', 'g': 'grid'}
        header_info, data_table = pd.DataFrame(), pd.DataFrame()
        if table_doc_type == 'xl':
            header_info = pd.read_excel(directory, nrows=6, header=None)
            data_table = pd.read_excel(directory, skiprows=6)
            header_dict = {header_info.iloc[i, 0]: header_info.iloc[i, 1] for i in range(len(header_info))}


        elif table_doc_type == 'csv':
            with open(directory, 'r') as file:
                csv_reader = csv.reader(file)
                header_rows = [next(csv_reader) for _ in range(6)]
            header_dict = {row[0]: row[1] if len(row) > 1 else None for row in header_rows}
            data_table = pd.read_csv(directory, skiprows=6)
        data_table['SurfaceLatitude'] = header_dict['surface_latitude']
        data_table['SurfaceLongitude'] = header_dict['surface_longitude']
        data_table['SurveySurfaceElevation'] = header_dict['surface_elevation']
        data_table['CitingType'] = 'Planned' if label == 'planned' else 'AsDrilled'

        # north_ref =
        return data_table, north_ref_dict[header_dict['north_ref'].lower()]

    def process_pdf_data(self, directory, label):
        parsed_text_data = self.text_box_data_gather(directory)
        # Handle case where processing was cancelled
        if parsed_text_data is None:
            return None
        returned_data = self.gather_process(parsed_text_data)
        shl = self.process_shl(parsed_text_data)
        elevation = self.find_elevation()
        if elevation is None:
            elevation = self.gather_elevation(parsed_text_data, shl)
        output_data = [{"measured_depth": i[0], "inclination": i[1], "azimuth": i[2]} for i in returned_data]
        df = pd.DataFrame(data=output_data, columns=["measured_depth", "inclination", "azimuth"])
        df['SurfaceLatitude'] = shl[0]
        df['SurfaceLongitude'] = shl[1]
        df['SurveySurfaceElevation'] = elevation
        df['CitingType'] = 'Planned' if label == 'planned' else 'AsDrilled'
        north_ref = self.process_north_reference(parsed_text_data)
        df = df.drop_duplicates(keep="first")
        # extra_plats = self.load_new_data_locations(df)
        df = df.sort_values(by=['CitingType', 'measured_depth'])
        return df, north_ref
        # return df, north_ref, extra_plats

    def load_new_data_locations(self, df):

        def setup_sqlite_db():
            path_used_db = r'C:\Work\Databases'
            apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
            return sqlite3.connect(apd_data_dir)

        def get_coordinate_query(x, y, buffer_distance=1000):
            """
            Query using coordinate columns directly

            Parameters:
            bbox: tuple of (minx, miny, maxx, maxy)
            buffer_distance: amount to expand search area
            """
            return f"""
            SELECT *
            FROM BaseData
            WHERE 
                Easting >= {x - buffer_distance}
                AND Easting <= {x + buffer_distance}
                AND Northing >= {y - buffer_distance}
                AND Northing <= {y + buffer_distance}
            """

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

        def parse_for_location():
            for idx, row in test_plat.iterrows():
                polygon = row['geometry']
                if polygon.contains(first_pt):
                    return test_plat.loc[[idx]]

        def read_base_data_by_conc(conn, conc_values):
            """
            Run a 'Conc in' query on BaseData for a given list of conc_values.
            """
            conc_str = ', '.join(f"'{c}'" for c in conc_values)
            query = f"SELECT * FROM BaseData WHERE Conc IN ({conc_str})"
            return pd.read_sql(query, conn)

        conn_db = setup_sqlite_db()
        utm_pt = utm.from_latlon(float(df['SurfaceLatitude'].iloc[0]), float(df['SurfaceLongitude'].iloc[0]))[:2]
        query = get_coordinate_query(utm_pt[0], utm_pt[1])
        filtered_data = pd.read_sql(query, conn_db)
        conc_vals = filtered_data['Conc'].unique()
        filtered_data = read_base_data_by_conc(conn_db, conc_vals)
        test_plat = geo_transform(filtered_data)

        first_pt = [float(df['SurfaceLatitude'].iloc[0]), float(df['SurfaceLongitude'].iloc[0])]
        first_pt = Point(utm.from_latlon(first_pt[0], first_pt[1])[:2])
        row_found = parse_for_location()
        conn_db.close()
        return row_found

    def find_elevation(self):
        query = f"""SELECT l.GRELEV
          FROM Well w
          LEFT JOIN Construct c ON c.WellKey = w.PKey
          LEFT JOIN loc l ON l.ConstructKey = c.pkey
          WHERE WellID = '{self.api}'
          AND LocType IN ('SURF')"""
        loc_df = self.db.query_to_dataframe(query)
        elevation = loc_df['GRELEV'].iloc[0]
        return elevation

    def text_box_data_gather(self, path):
        # Open and setup PDF
        try:
            fp = open(path, 'rb')
        except FileNotFoundError:
            return
        rsrcmgr = PDFResourceManager()
        laparams = LAParams(char_margin=0.1)
        device = PDFPageDetailedAggregator(rsrcmgr, laparams=laparams)
        interpreter = PDFPageInterpreter(rsrcmgr, device)

        # Get total page count first
        pages = list(PDFPage.get_pages(fp, caching=False))
        total_pages = len(pages)

        # Create progress dialog
        progress = QProgressDialog("Processing PDF...", "Cancel", 0, total_pages)
        progress.setWindowTitle("Processing PDF")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        # Reset file pointer
        fp.seek(0)
        pages = PDFPage.get_pages(fp, caching=False)

        counter = 0
        for i in pages:
            if progress.wasCanceled():
                fp.close()
                return None

            try:
                interpreter.process_page(i)
                device.get_result()
            except TypeError:
                pass

            counter += 1
            progress.setValue(counter)
            QApplication.processEvents()

        data_lst = self.text_box_grouper_manager(device, counter)
        fp.close()
        return data_lst

    def text_box_grouper_manager(self, device, counter):
        data_lst = [[] for p in range(counter + 1)]
        for (page_nb, x_min, y_min, x_max, y_max, txt) in device.rows:
            data_lst[page_nb].append([x_min, y_min, x_max, y_max, txt])

        for i in range(len(data_lst)):
            if data_lst[i]:
                data_lst[i] = sorted(data_lst[i], key=lambda x: (x[0], x[1]))
        return data_lst

    def parse_and_find(self, lst, str_t, b_lst):
        def process_item(page_num, item):
            x1, y1, x2, y2, txt = item
            txt = re.sub(r'[\n,]', ' ', txt.lower().strip())
            if str_t in txt and (b_lst == [''] or not any(word.lower() in txt for word in b_lst)):
                return [page_num, txt, x1, y1, x2, y2]
            return None

        return [
            result for page_num, page in enumerate(lst)
            for result in map(lambda item: process_item(page_num, item), page)
            if result is not None
        ]

    def gather_process(self, parsed_data):
        def find_blacklist(line):
            black_lst = {"start", "drop", "hold", "dls", "casing", "surface", "kick", "lp", "shl", "water", "pbhl",
                         "build", "tangent", "3d", "inch", "inches", "includes", "sincerely", "reference", "referenced",
                         "end", "correct", "west", "east", "american", "county", "plan", "tgr", "fnl", "fel", "fsl",
                         "fwl", "tgr3"}
            white_lst = {"azimuth", "inclination"}
            line = line.replace("\n", " ").lower()
            words = set(re.findall(r'\b\w+\b', line))
            # if self.well_name.lower() in line:
            #     return True
            if black_lst.intersection(words) and not white_lst.intersection(words):
                return True
            data = re.sub(r'[^0-9. ]+', '', line)
            if 0 < len(data) / len(line) < 0.15:
                return True
            return False

        def find_md_data():
            measured_depth_lst1 = self.parse_and_find(parsed_data, 'measured', [''])
            md_lst_found = self.parse_and_find(parsed_data, 'md', [''])
            md_all_lst = measured_depth_lst1 + md_lst_found
            md_edited = [md_all_lst[i] for i in range(len(md_all_lst)) if not find_blacklist(md_all_lst[i][1])]
            md_edited = [list(t) for t in set(tuple(element) for element in md_edited)]
            md_edited = sorted(md_edited)
            return md_edited

        def find_inc_data():
            inclination_lst = self.parse_and_find(parsed_data, 'inclination', [''])
            inc_lst_found = self.parse_and_find(parsed_data, 'inc', [''])
            inc_all_lst = inclination_lst + inc_lst_found
            inc_edited = [inc_all_lst[i] for i in range(len(inc_all_lst)) if not find_blacklist(inc_all_lst[i][1])]
            inc_edited = [list(t) for t in set(tuple(element) for element in inc_edited)]
            inc_edited = sorted(inc_edited)
            return inc_edited

        def find_azi_data():
            azimuth_lst = self.parse_and_find(parsed_data, 'azimuth', [''])
            azi_lst_found = self.parse_and_find(parsed_data, 'azi', [''])
            azi_all_lst = azi_lst_found + azimuth_lst
            azi_edited = [azi_all_lst[i] for i in range(len(azi_all_lst)) if not find_blacklist(azi_all_lst[i][1])]
            azi_edited = [list(t) for t in set(tuple(element) for element in azi_edited)]
            azi_edited = sorted(azi_edited)
            for i in range(len(azi_edited)):
                if "extrapolated station" in azi_edited[i][1]:
                    index_cut = azi_edited[i][1].index('azimuth')
                    azi_edited[i][1] = azi_edited[i][1][index_cut:]
                    azi_edited[i][1].strip()
            return azi_edited

        def compare_page_coordinates():
            def create_dataframe(lst, columns):
                return pd.DataFrame(lst, columns=['page', 'text'] + columns)

            # Create DataFrames
            md_df = create_dataframe(md_lst, ['x1', 'y1', 'x2', 'y2'])
            inc_df = create_dataframe(inc_lst, ['x1', 'y1', 'x2', 'y2'])
            azi_df = create_dataframe(azi_lst, ['x1', 'y1', 'x2', 'y2'])

            # Merge inc and azi DataFrames
            inc_azi_df = pd.merge(inc_df, azi_df, on='page', suffixes=('_inc', '_azi'))

            # Filter based on y2 ratio condition
            inc_azi_df = inc_azi_df[
                (inc_azi_df['y2_inc'] / inc_azi_df['y2_azi']).between(0.95, 1.05)
            ]

            # Merge with md DataFrame
            result_df = pd.merge(md_df, inc_azi_df, on='page')

            # Apply conditions
            result_df = result_df[
                (result_df['y2_inc'] / result_df['y2']).between(0.95, 1.05) &
                (result_df['x2_azi'] < 330) &
                (result_df['x2_azi'] >= result_df['x1_azi']) &
                (result_df['x2_azi'] >= result_df['x1_inc']) &
                (result_df['x2_inc'] >= result_df['x1_inc']) &
                (result_df['x2_inc'] >= result_df['x2']) &
                (result_df['x2'] >= result_df['x1']) &
                (
                        ((result_df['x1'] < result_df['x2']) & (result_df['x2'] <= result_df['x1_inc']) & (
                                result_df['x1_inc'] < result_df['x2_inc'])) |
                        ((result_df['x1'] <= result_df['x1_inc']) & (result_df['x2'] <= result_df['x2_inc']))
                )
                ]

            # Prepare output
            md_inc_azi_found = result_df.apply(lambda row: [
                [row['page']],
                [row['x1'], row['x2'], row['y1'], row['y2']],
                [row['x1_inc'], row['x2_inc'], row['y1_inc'], row['y2_inc']],
                [row['x1_azi'], row['x2_azi'], row['y1_azi'], row['y2_azi']]
            ], axis=1).tolist()

            page_lst_found = sorted(result_df['page'].unique())
            inc_azi_lst_found = inc_azi_df[['page', 'text_inc', 'x1_inc', 'y1_inc', 'x2_inc', 'y2_inc',
                                            'text_azi', 'x1_azi', 'y1_azi', 'x2_azi', 'y2_azi']].values.tolist()

            return md_inc_azi_found, set(page_lst_found), inc_azi_lst_found

        def grouper_process():
            def find_corresponding_data(grouper, lst, checker):
                def find_closest(val):
                    return min(flat_grouper, key=lambda x: abs(x - val))

                df = pd.DataFrame(lst, columns=['x1', 'y1', 'x2', 'y2', 'text'])
                df['avg_x'] = (df['x1'] + df['x2']) / 2
                df['avg_y'] = (df['y1'] + df['y2']) / 2
                flat_grouper = [item for sublist in grouper for item in sublist]

                group_col = 'avg_x' if checker == 'x_avg' else 'avg_y'
                df['group'] = df[group_col].apply(find_closest)
                grouped = df.groupby('group').apply(lambda x: x.sort_values('y1', ascending=False))
                result = [group[['x1', 'y1', 'x2', 'y2', 'text']].values.tolist()
                          for _, group in grouped.groupby(level=0)]
                return result

            def stats_processor(data_x, data_y, md_limit):
                def data_gather(lst):
                    lst = str(lst)
                    data = lst.replace("\n", " ").replace("†", "").lower().strip().replace(",", "")
                    data = re.sub(r'[^0-9. ]+', '', data).strip()
                    data_lst = data.split(" ")
                    data_lst = [i for i in data_lst if i]
                    if len(data_lst) > 1 or data_lst == [] or data_lst == ['.'] or (
                            len(data_lst) == 1 and len(data_lst[0]) * 2 < len(lst)):
                        return []
                    return data_lst

                y_avg_limit = [st.mean([md_limit[i][2], md_limit[i][3]]) for i in range(1, len(md_limit))]
                y_avg_all = st.mean(y_avg_limit)
                for i in range(len(data_y)):
                    data_y[i] = [j for j in data_y[i] if data_gather(j[-1]) != [] and st.mean([j[1], j[3]]) < y_avg_all]
                    for j in range(len(data_y[i])):
                        data_y[i][j][-1] = data_gather(data_y[i][j][-1])[0]
                for i in range(len(data_x)):
                    data_x[i] = [j for j in data_x[i] if data_gather(j[-1]) != [] and st.mean([j[1], j[3]]) < y_avg_all]
                    data_x[i] = sorted(data_x[i], key=lambda x: x[3])
                    for j in range(len(data_x[i])):
                        data_x[i][j][-1] = data_gather(data_x[i][j][-1])[0]
                data_y = [group for group in data_y if len(group) > 1 and float(group[1][-1]) < 100]
                data_x = [group for group in data_x if len(group) > 1 and float(group[1][-1]) < 100]
                return data_x, data_y, y_avg_all

            parsed_data_used = [parsed_data[i] for i in range(len(parsed_data)) if i in page_lst]
            all_x_data = []
            mode_row_returner = []
            all_y_data = []

            for i in range(len(parsed_data_used)):
                group_lst = [st.mean([parsed_data_used[i][j][0], parsed_data_used[i][j][2]]) for j in
                             range(len(parsed_data_used[i]))]
                group_lst_y = [st.mean([parsed_data_used[i][j][1], parsed_data_used[i][j][3]]) for j in
                               range(len(parsed_data_used[i]))]
                grouper_func = [j for i, j in dict(enumerate(ma.grouper(sorted(group_lst), 3), 1)).items()]
                grouper_func_y = [j for i, j in dict(enumerate(ma.grouper(sorted(group_lst_y), 2), 1)).items()]
                grouper_full_data = find_corresponding_data(grouper_func, parsed_data_used[i], 'x_avg')
                grouper_full_data_y = find_corresponding_data(grouper_func_y, parsed_data_used[i], 'y_avg')
                grouper_full_data_y = sorted(grouper_full_data_y, key=lambda x: x[0][1], reverse=True)
                grouper_full_data, grouper_full_data_y, boundary_line = stats_processor(grouper_full_data,
                                                                                        grouper_full_data_y,
                                                                                        md_inc_azi[i])

                grouper_full_data_y = sorted(grouper_full_data_y, key=lambda x: x[1], reverse=True)

                all_x_data.append(grouper_full_data)
                grouper_full_data_y = [r for r in grouper_full_data_y if len(r) >= 3]
                all_lengths = [len(r) for r in grouper_full_data_y if len(r) > 0]

                mode_row_returner = mode_row_returner + all_lengths

                all_y_data.append(grouper_full_data_y)

            mode_row = st.mode(mode_row_returner)

            all_y_data = list(chain.from_iterable(all_y_data))

            all_y_data = [i for i in all_y_data if mode_row + 1 >= len(i) >= mode_row - 1]

            all_y_data = [i[:3] for i in all_y_data]

            all_y_data = [i for i in all_y_data if len(i) == 3]

            all_y_data = [[float(i[0][-1]), float(i[1][-1]), float(i[2][-1])] for i in all_y_data]
            return all_y_data

        def error_finder(data_1):
            outliers = []
            threshold = 3
            mean_1 = np.mean(data_1)
            std_1 = np.std(data_1)
            counter_errors = 0
            for y in data_1:
                z_score = (y - mean_1) / std_1
                if np.abs(z_score) > threshold:
                    outliers.append([y, counter_errors])
                counter_errors += 1
            return outliers

        counter = 1
        md_lst = find_md_data()
        inc_lst = find_inc_data()
        azi_lst = find_azi_data()
        md_inc_azi, page_lst, inc_azi_lst = compare_page_coordinates()
        page_lst = sorted(list(page_lst))
        returned_data = grouper_process()
        md_lst = [float(i[0]) for i in returned_data]
        inc_lst = [float(i[1]) for i in returned_data]
        azi_lst = [float(i[2]) for i in returned_data]
        md_outliers = error_finder(md_lst)
        inc_outliers = error_finder(inc_lst)
        azi_outliers = error_finder(azi_lst)
        outliers_lst = md_outliers + inc_outliers + azi_outliers
        outliers_lst = list(set(i[1] for i in outliers_lst))
        for i in outliers_lst:
            returned_data[i] = []
        returned_data = [i for i in returned_data if i]
        return returned_data

    def gather_elevation(self, parsed_data, shl):
        n_lst = self.parse_and_find(parsed_data, 'ground level', [''])
        for i in range(len(parsed_data)):
            for j in range(len(parsed_data[i])):
                text = parsed_data[i][j][4].lower().strip().replace("\n", " ").replace(",", "")
                x1, y1, x2, y2 = parsed_data[i][j][0], parsed_data[i][j][1], parsed_data[i][j][2], parsed_data[i][j][3]
                for k in range(len(n_lst)):
                    if i == n_lst[k][0]:
                        x3, y3, x4, y4 = n_lst[k][2], n_lst[k][3], n_lst[k][4], n_lst[k][5]
                        if x4 < x1 and abs(y1 - y3) < 2 and abs(y2 - y4) < 4:
                            try:
                                float(text)
                                return float(text)
                            except ValueError:
                                pass

    def process_north_reference(self, parsed_data):
        n_lst = self.parse_and_find(parsed_data, 'north reference', [''])
        for i in range(len(parsed_data)):
            for j in range(len(parsed_data[i])):
                text = parsed_data[i][j][4].lower().strip().replace("\n", " ").replace(",", "")
                x1, y1, x2, y2 = parsed_data[i][j][0], parsed_data[i][j][1], parsed_data[i][j][2], parsed_data[i][j][3]
                for k in range(len(n_lst)):
                    if i == n_lst[k][0]:
                        x3, y3, x4, y4 = n_lst[k][2], n_lst[k][3], n_lst[k][4], n_lst[k][5]
                        o_text = n_lst[k][1]
                        value_ret_d = self.find_proximal_values_north_ref(x1, y1, x2, y2, text, x3, y3, x4, y4, o_text)
                        if value_ret_d != -1:
                            return value_ret_d

    def find_proximal_values_north_ref(self, x1, y1, x2, y2, input_text, x3, y3, x4, y4, reference_text):
        y4 = self.modify_north_ref_for_incomplete_data(reference_text, input_text, y3, y4, y1, y2)
        value_ret = -1
        type_lst = ['magnetic', 'true', 'grid']
        if x3 < x4 < x1 < x2 and abs(y1 - y3) < 2 and abs(y2 - y4) < 4:  # index == str_lst[0]:
            for k in type_lst:
                re_text2 = re.search(r"\b{}\b".format(k), input_text, re.IGNORECASE)
                if re_text2 is not None:
                    value_ret = re_text2.group()
                    return value_ret
        if x3 == x1 and x4 == x2 and abs(y1 - y3) < 2 and abs(y2 - y4) < 4:  # index == str_lst[0]:
            for k in type_lst:
                re_text2 = re.search(r"\b{}\b".format(k), input_text, re.IGNORECASE)
                if re_text2 is not None:
                    value_ret = re_text2.group()
                    return value_ret
        return value_ret

    def modify_north_ref_for_incomplete_data(self, reference_text, input_text, y3, y4, y1, y2):
        re_text = re.search(r"\b{}\b".format('local co-ordinate reference'), reference_text, re.IGNORECASE)
        re_text2 = re.search(r"\b{}\b".format('md reference'), reference_text, re.IGNORECASE)
        if re_text is None and re_text2 is not None:
            if abs(y3 - y1) < 2 < abs(y4 - y2):
                if y4 < y2:
                    y4 = y2
                    return y4
        return y4

    def process_shl(self, parsed_data):
        lat_lst_o = self.parse_and_find(parsed_data, 'latitude', [''])
        lon_lst_o = self.parse_and_find(parsed_data, 'longitude', [''])
        latRange = ['35', '36', '37', '38', '39', '40', '41', '42', '43', '44']
        lonRange = ['115', '114', '113', '112', '111', '110', '109', '108']
        lat_lon_value = [0, 0]
        page_no = self.find_bounding_y_coordinates(parsed_data)
        page_no = list(set(page_no))
        for k in page_no:
            lat_lst = [i for i in lat_lst_o if i[0] == k]
            lon_lst = [i for i in lon_lst_o if i[0] == k]
            for j in range(len(parsed_data[k])):
                parse_left, parse_down, parse_right, parse_up = parsed_data[k][j][0], parsed_data[k][j][1], \
                    parsed_data[k][j][2], parsed_data[k][j][3]  # get the data for the current line
                text = parsed_data[k][j][4].lower().strip().replace("\n", " ").replace(",", "")
                for r in range(len(lat_lst)):
                    val_left, val_down, val_right, val_up = lat_lst[r][2], lat_lst[r][3], lat_lst[r][4], lat_lst[r][5]
                    output = self.find_proximal_values(parse_left, parse_down, parse_right, parse_up, text, val_left,
                                                       val_down, val_right, val_up, latRange, 'lat')
                    if output is not None:
                        lat_lon_value[0] = output
                for r in range(len(lon_lst)):
                    val_left, val_down, val_right, val_up = lon_lst[r][2], lon_lst[r][3], lon_lst[r][4], lon_lst[r][5]
                    output = self.find_proximal_values(parse_left, parse_down, parse_right, parse_up, text, val_left,
                                                       val_down, val_right, val_up, lonRange, 'lon')
                    if output is not None:
                        lat_lon_value[1] = str(abs(float(output)) * -1)

        return lat_lon_value

    def find_bounding_y_coordinates(self, parsed_data):
        y_values_limit = []
        well_page = []
        for i in range(len(parsed_data)):
            for j in range(len(parsed_data[i])):
                text = parsed_data[i][j][4].lower().strip().replace("\n", " ").replace(",", "")
                x1, y1, x2, y2 = parsed_data[i][j][0], parsed_data[i][j][1], parsed_data[i][j][2], parsed_data[i][j][
                    3]  # get the data for the current line
                if 'well position' in text or 'uncertainty' in text or 'geographic coordinates' in text or 'surface location' in text or 'lat / long:' in text:
                    y_values_limit.append(y1)
                    y_values_limit.append(y2)
                    well_page.append(i)

        return well_page

    def find_proximal_values(self, parse_left, parse_down, parse_right, parse_up, text, val_left, val_down, val_right,
                             val_up, range_data, coord_type):
        val_x_avg, val_y_avg = st.mean([val_right, val_left]), st.mean([val_down, val_up])
        parse_x_avg, parse_y_avg = st.mean([parse_right, parse_left]), st.mean([parse_down, parse_up])
        if val_x_avg < parse_x_avg and abs(val_y_avg - parse_y_avg) < 5 or abs(
                val_x_avg - parse_x_avg) < 5 and val_y_avg > parse_y_avg:
            output_dec = self.lat_lon_reg_ex_dec(range_data, text)
            output_deg = self.lat_lon_reg_ex_deg(range_data, text, coord_type)
            if output_dec is not None:
                return output_dec
            elif output_deg is not None:

                return output_deg

    def lat_lon_reg_ex_dec(self, range_data, line):
        for k in range_data:
            regExDecimal = re.compile(re.escape(k) + r"\.\d{4,6}")
            searchDec = regExDecimal.search(line)
            if searchDec is not None:
                return searchDec.group()

    def lat_lon_reg_ex_deg(self, range_data, line, coord_type):
        for k in range_data:
            if coord_type == 'lat':
                regExDegree = re.compile(
                    r"(90[ :°d]*00[ :\'\'m]*00(\.0+)?|[3-4][0-9][ :°d]*[0-5][0-9][ :\'\'m]*[0-5][0-9](\.\d+))[ :\?\"s]*(N|n|S|s)?")
            elif coord_type == 'lon':
                regExDegree = re.compile(
                    r"-?((1[0-7][0-9]|0[0-9][0-9]|0[0-9])[ :°d]*([0-5][0-9]|[0-9])[ :\'\'m]*[0-5][0-9](\.\d+))[ :\?\"s]*(E|e|W|w)?")
            searchLatDeg = regExDegree.search(line)
            if searchLatDeg is not None:
                try:
                    value = self.convert_degree_to_decimal(searchLatDeg.group())
                except ValueError:
                    return 0
                return value
            else:
                regExDegree = re.compile(
                    re.escape(k) + r"[\°]?[\s]?" + r"\d{1,2}[\']?[\s]?" + r"[\d]{1,2}[\.]?[\d]{2,5}?")

    def convert_degree_to_decimal(self, value):
        test = re.sub("[^0-9.]+", " ", value)
        degreeValue, hourValue, minuteValue = float(test.split()[0]), float(test.split()[1]), float(test.split()[2])
        finalValue = round(degreeValue + hourValue / 60 + minuteValue / 3600, 6)

        return finalValue
