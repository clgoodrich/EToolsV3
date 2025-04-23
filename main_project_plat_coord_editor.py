import sqlite3
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
import os
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QTableWidgetItem
import utm
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
from pyproj import Transformer

class PlatCoordEditor:
    def __init__(self, section_df, ui):
        self.section_df = section_df
        self.ui = ui
        self.db = self.setup_sqlite_db()
        self.dict_utm = {}
        self.dict_latlon = {}
        for i in range(8):
            setattr(self, f"plat_table_model_coords_{i + 1}", QStandardItemModel())
            model = getattr(self, f"plat_table_model_coords_{i + 1}")
            ui_element = getattr(self.ui, f"table_coords_{i + 1}")
            ui_element.setModel(model)
            self.setup_radio_buttons(i)
        self.write_all_data()

    def setup_radio_buttons(self, i):
        button_group = getattr(self.ui, f"bg_coords_{i + 1}")
        button = getattr(self.ui, f"utm_radio_coords_{i + 1}")
        button_group.blockSignals(True)
        button.blockSignals(True)
        button.setChecked(True)
        button_group.blockSignals(False)
        button.blockSignals(True)

    def setup_sqlite_db(self):
        path_used_db = r'C:\Work\Databases'
        apd_data_dir = os.path.join(path_used_db, 'Board_DB_Plss_Sections.db')
        return sqlite3.connect(apd_data_dir)

    # def tester_function(self):
    #     cur = self.db.cursor()
    #
    #     # 2) grab all table names
    #     cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    #     tables = [row[0] for row in cur.fetchall()]
    #
    #     # 3) for each table, pull its column info
    #     for tbl in tables:
    #         print(f"Table: {tbl}")
    #         cur.execute(f"PRAGMA table_info({tbl});")
    #         cols = cur.fetchall()
    #         # PRAGMA table_info returns rows: (cid, name, type, notnull, dflt_value, pk)
    #         for cid, name, typ, notnull, dflt, pk in cols:
    #             nn = "NOT NULL" if notnull else "NULLABLE"
    #             pk_flag = "PK" if pk else ""
    #             print(f"   • {name} — {typ} {nn} {pk_flag}")
    #         print()
    #
    #     self.db.close()
    def write_all_data(self):
        def write_coordinates():
            main_table = getattr(self.ui, f"table_coords_{i + 1}")
            model = getattr(self, f"plat_table_model_coords_{i + 1}")
            main_table.setUpdatesEnabled(False)
            main_table.verticalHeader().setVisible(False)
            main_table.setShowGrid(True)
            model.setHorizontalHeaderLabels(['X', 'Y'])
            points = list(row['geometry'].exterior.coords)
            for val, (x, y) in enumerate(points):
                model.setItem(val, 0, QStandardItem(f"{x:.3f}"))
                model.setItem(val, 1, QStandardItem(f"{y:.3f}"))
            main_table.setUpdatesEnabled(True)
            main_table.show()
            self.dict_utm[str(i+1)] = row['geometry']

        def write_tsr():
            tsr_info = getattr(self.ui, f"plat_table_coords_{i + 1}")
            parameters = row['label'].split(" ")
            section = int(float(parameters[0]))
            township = int(float(parameters[1][:-1]))
            township_dir = parameters[1][-1:]
            rng = int(float(parameters[2][:-1]))
            rng_dir = parameters[2][-1:]
            meridian = parameters[3]
            data = [section, township, township_dir, rng, rng_dir, meridian]
            tsr_info.clearContents()  # optional: clear old items
            tsr_info.setRowCount(len(data))
            tsr_info.setColumnCount(1)
            tsr_info.setHorizontalHeaderLabels(['Value'])  # adjust header text as needed

            for row2, val in enumerate(data):
                tsr_info.setItem(row2, 0, QTableWidgetItem(str(val)))
        def convert_utm_to_latlon():
            utm_poly = row['geometry']  # a shapely Polygon in UTM zone 12N

            # 3) build a transformer from UTM 12N → WGS84
            #    (northern hemisphere uses 326##; southern is 327##)
            transformer = Transformer.from_crs("EPSG:32612", "EPSG:4326", always_xy=True)

            # 4) transform each exterior coordinate
            lonlat = [transformer.transform(x, y) for x, y in utm_poly.exterior.coords]
            self.dict_latlon[str(i+1)] = Polygon(lonlat)

        for i, row in self.section_df.iterrows():
            write_coordinates()
            write_tsr()
            convert_utm_to_latlon()


