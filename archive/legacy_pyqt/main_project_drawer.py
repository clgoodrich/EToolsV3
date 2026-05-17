import decimal
import tempfile
from PyQt5.QtGui import QGuiApplication
from shapely.geometry import Point, LineString
from matplotlib.collections import PatchCollection
from PyQt5.QtCore import Qt
from matplotlib.textpath import TextPath
from matplotlib.patches import PathPatch
import utm
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
import pandas as pd
from PyQt5.QtCore import QUrl
import plotly.graph_objects as go
import numpy as np
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QAbstractItemView, QSizePolicy
from PyQt5.QtWidgets import QHeaderView, QAbstractItemView


class ZoomPan:
    def __init__(self):
        self.press = None
        self.cur_xlim = None
        self.cur_ylim = None
        self.x0 = None
        self.y0 = None
        self.x1 = None
        self.y1 = None
        self.xpress = None
        self.ypress = None
        self.text_objects = []  # Store text annotations

    def zoom_factory(self, ax, base_scale):
        def zoom(event):
            if event.inaxes != ax: return
            cur_xlim = ax.get_xlim()
            cur_ylim = ax.get_ylim()

            xdata = event.xdata  # get event x location
            ydata = event.ydata  # get event y location

            if event.button == 'down':
                # deal with zoom in
                scale_factor = 1 / base_scale
            elif event.button == 'up':
                # deal with zoom out
                scale_factor = base_scale
            else:
                # deal with something that should never happen
                scale_factor = 1

            new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
            new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor

            relx = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
            rely = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])

            ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * (relx)])
            ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * (rely)])

            # Update the font size of text annotations based on the new zoom level
            scale_factor = ax.get_xlim()[1] - ax.get_xlim()[0]
            for text in self.text_objects:
                new_fontsize = 12 / scale_factor * 2500  # Adjust the 10 as needed for desired scale
                text.set_fontsize(new_fontsize)
            ax.figure.canvas.draw()

        fig = ax.get_figure()  # get the figure of interest
        fig.canvas.mpl_connect('scroll_event', zoom)
        return zoom

    def add_text(self, ax, x, y, text_str):
        scale_factor = ax.get_xlim()[1] - ax.get_xlim()[0]
        text = ax.text(x, y, text_str, ha='center', va='center', fontsize=12 / scale_factor * 2500,
                       transform=ax.transData)
        self.text_objects.append(text)

    def pan_factory(self, ax):
        def onPress(event):
            if event.inaxes != ax: return
            self.cur_xlim = ax.get_xlim()
            self.cur_ylim = ax.get_ylim()
            self.press = self.x0, self.y0, event.xdata, event.ydata
            self.x0, self.y0, self.xpress, self.ypress = self.press

        def onRelease(event):
            self.press = None
            ax.figure.canvas.draw()

        def onMotion(event):
            if self.press is None: return
            if event.inaxes != ax: return
            dx = event.xdata - self.xpress
            dy = event.ydata - self.ypress
            self.cur_xlim -= dx
            self.cur_ylim -= dy
            ax.set_xlim(self.cur_xlim)
            ax.set_ylim(self.cur_ylim)

            ax.figure.canvas.draw()

        fig = ax.get_figure()  # get the figure of interest

        # attach the call back
        fig.canvas.mpl_connect('button_press_event', onPress)
        fig.canvas.mpl_connect('button_release_event', onRelease)
        fig.canvas.mpl_connect('motion_notify_event', onMotion)

        # return the function
        return onMotion


class DataDrawer:
    def __init__(self, ui, df_survey):
        def clear_widget(widget):
            for i in reversed(range(widget.layout().count())):
                widget.layout().itemAt(i).widget().setParent(None)

        def clear_layout(layout):
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        self.df_survey = df_survey
        self.ui = ui
        clear_widget(self.ui.well_viz_display)
        self.df_custom_viz_pts = pd.DataFrame(columns=['Label', 'Easting', 'Northing', 'Geometry'])
        self.plat_df = pd.DataFrame()
        self.figure_visual = plt.figure()
        self.canvas_visual = FigureCanvas(self.figure_visual)
        self.ax_visual = self.figure_visual.subplots()
        self.ui.well_viz_display.addWidget(self.canvas_visual)
        self.added_viz_pts_model = QStandardItemModel()
        self.ui.insert_pts_lst.setModel(self.added_viz_pts_model)
        self.added_viz_pts_model.dataChanged.connect(self.update_model_table_when_user_modifies_values)
        self.ui.insert_pts_lst.setEditTriggers(QAbstractItemView.AllEditTriggers)


        self.added_viz_points_data_model = QStandardItemModel()
        self.ui.dx_viz_data_table.setModel(self.added_viz_points_data_model)



        self.canvas_visual.mpl_connect('button_press_event', self.click_on_2d_targeter)
        self.hovertemplate = (
            "<b>Measured Depth:</b> %{customdata[1]:.2f} ft<br>"
            "<b>Inclination:</b> %{customdata[2]:.2f}°<br>"
            "<b>Azimuth:</b> %{customdata[3]:.2f}°<br>"
            "<b>TVD:</b> %{customdata[0]:.2f} ft<br>"
            "<b>Northing:</b> %{x:.2f} m<br>"
            "<b>Easting:</b> %{y:.2f} m<br>"
            "<b>FNL:</b> %{customdata[4]:.2f} ft<br>"
            "<b>FSL:</b> %{customdata[5]:.2f} ft<br>"
            "<b>FEL:</b> %{customdata[6]:.2f} ft<br>"
            "<b>FWL:</b> %{customdata[7]:.2f} ft<br>"
            "<b>Township And Range:</b> %{customdata[8]} ft<br>"
            "<extra></extra>")
        clear_layout(self.ui.well_viz_display_general)
        clear_layout(self.ui.well_viz_display_tsr)

        self.fig_general = go.Figure()
        self.fig_tsr = go.Figure()

        # Create temp files once
        self.temp_file_general = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False)
        self.temp_file_tsr = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False)

        # Setup web views once
        self.web_view_general = QWebEngineView()
        self.ui.well_viz_display_general.addWidget(self.web_view_general)
        self.web_view_general.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ui.well_viz_display_general.setContentsMargins(0, 0, 0, 0)

        self.web_view_tsr = QWebEngineView()
        self.ui.well_viz_display_tsr.addWidget(self.web_view_tsr)
        self.web_view_tsr.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ui.well_viz_display_tsr.setContentsMargins(0, 0, 0, 0)

        self.zp = ZoomPan()
        self.zoom_fac = self.zp.zoom_factory(self.ax_visual, 1.1)
        figPan = self.zp.pan_factory(self.ax_visual)
        self.ax_visual.axis('equal')
        self.ret_pts = self.ax_visual.scatter([], [], c='black', s=50, zorder=2, alpha=0.5)

        self.scatter_custom_pts = self.ax_visual.scatter([], [], c='blue', s=10, zorder=2)
        self.bhl_pts = self.ax_visual.scatter([], [],
                                              marker='o',
                                              color='black',  # filled black circle
                                              s=25,
                                              zorder=1000)
        self.shl_pts = self.ax_visual.scatter([], [],
                                              marker='o',
                                              color='white',  # white-filled circle
                                              edgecolors='black',
                                              s=25,
                                              zorder=1000)
        self.plats = LineCollection([], color='black', linewidth=2,
                                    zorder=2)
        self.plats_100 = LineCollection([], color='black', linewidth=2,
                                        zorder=2)
        self.plats_330 = LineCollection([], color='black', linewidth=2,
                                        zorder=2)
        self.labels_plats_2d = PatchCollection([
            PathPatch(TextPath((coord.x, coord.y), text, size=75), color="red")
            for coord, text in zip([], [])], facecolors="black")  ### graphic for mapping township and range labels
        self.ax_visual.add_collection(self.labels_plats_2d)

    def change_visibility_100(self, state):
        if state == 2:
            self.plats_100.set_visible(True)
        else:
            self.plats_100.set_visible(False)
        self.update_2d_map()

    def change_visibility_330(self, state):
        if state == 2:
            self.plats_330.set_visible(True)
        else:
            self.plats_330.set_visible(False)
        self.update_2d_map()

    def update_2d_map(self):
        self.canvas_visual.blit(self.ax_visual.bbox)
        self.canvas_visual.draw()

    def draw_3d_process(self, df):
        self.fig_general.data = []
        self.fig_tsr.data = []
        plat_color_dict = self.draw_plats()
        self.draw_general_process(self.df_survey, plat_color_dict)
        self.load_figure(self.fig_general, self.web_view_general, self.temp_file_general)
        self.load_figure(self.fig_tsr, self.web_view_tsr, self.temp_file_tsr)

        self.fig_general.write_html(self.temp_file_general.name)
        self.web_view_general.load(QUrl.fromLocalFile(self.temp_file_general.name))

        self.fig_tsr.write_html(self.temp_file_tsr.name)
        self.web_view_tsr.load(QUrl.fromLocalFile(self.temp_file_tsr.name))

    def load_figure(self, fig, view, temp):
        fig.update_layout(
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02,
                font=dict(size=8),
                itemsizing="constant",
                itemwidth=30,
            ),
            hoverlabel=dict(
                bgcolor="rgba(255,255,255,1)",
                bordercolor="rgba(0,0,0,1)",
            ),
            scene=dict(
                aspectmode='data',
                camera=dict(
                    eye=dict(x=1.5, y=1.5, z=0.5),
                )
            ),
            width=1000,
            height=700,
            margin=dict(l=10, r=250, t=30, b=10),
            title='Well Paths and Clearance',
            autosize=True,
        )

    def draw_plats(self):
        def drawer_plat_partial():
            legend_group2 = f'Plat_2d3d {row["label"]}'
            data = list(row['geometry'].exterior.coords)
            data = [list(i) for i in data]
            data = np.array([list(i) + [0] for i in data])
            x_coords, y_coords, z_coords = data.T
            z_coords *= 0.3048  # Convert to meters if necessary
            new_trace = go.Scatter3d(
                x=x_coords,
                y=y_coords,
                z=(z_coords * 0) - 25,
                mode='lines',
                surfaceaxis=2,
                surfacecolor=colors[num_color],
                opacity=0.7,
                hoverinfo='skip',
                name=legend_group2,
                line=dict(color=colors[num_color], width=4))

            return new_trace

        colors = [
            "#000000",  # Black
            "#0072B2",  # Blue
            "#E69F00",  # Orange
            "#009E73",  # Green
            "#CC79A7",  # Pink
            "#56B4E9",  # Sky Blue
            "#D55E00",  # Vermillion
            "#F0E442",  # Yellow
            "#808080",  # Gray
            "#4B0082",  # Indigo
            "#8B4513",  # Saddle Brown
            "#9932CC",  # Dark Orchid
            "#FF8C00",  # Dark Orange
            "#00CED1",  # Dark Turquoise
            "#FFD700",  # Gold
            "#CD5C5C",  # Indian Red
            "#6A5ACD",  # Slate Blue
            "#32CD32",  # Lime Green
            "#8B0000",  # Dark Red
            "#BA55D3",  # Medium Orchid
        ]
        plat_traces = []
        plat_color_dict = {}
        for idx, row in self.plat_df.iterrows():
            num_color = idx % len(colors)

            plat_traces.append(drawer_plat_partial())
            plat_color_dict[row['Conc']] = colors[num_color]
        for trace in plat_traces:
            self.fig_general.add_trace(trace)
            self.fig_tsr.add_trace(trace)
        return plat_color_dict

    def draw_general_process(self, df, plat_color_dict):
        id_dict = {'drl': "black", "pln": "red"}
        for i, v in df.items():
            dataframe = df[i].clearance_data
            color = id_dict[i[:3]]
            self.draw_general_viz_tab(survey_reference=dataframe,
                                      hovertemplate=self.hovertemplate,
                                      fig=self.fig_general,
                                      given_color=color,
                                      label=i)
            self.draw_tsr_vis_tab(survey_reference=dataframe,
                                  hovertemplate=self.hovertemplate,
                                  fig=self.fig_tsr,
                                  label=i,
                                  plat_color_dict=plat_color_dict)

    def draw_tsr_vis_tab(self, survey_reference, hovertemplate, fig, label, plat_color_dict):
        def add_spacer_trace():
            return go.Scatter(
                x=[None], y=[None],
                mode='markers',
                marker=dict(size=0, opacity=0),
                showlegend=True,
                name=' ',  # A single space as the name
                hoverinfo='none'
            )

        dict_translator = {
            'drl_df_true_dx': "AsDrilled: True",
            'drl_df_grid_dx': "AsDrilled: Grid",
            'pln_df_true_dx': "Planned: True",
            'pln_df_grid_dx': "Planned: Grid"}
        used_label = dict_translator[label]
        colors = [
            "#000000",  # Black
            "#0072B2",  # Blue
            "#E69F00",  # Orange
            "#009E73",  # Green
            "#CC79A7",  # Pink
            "#56B4E9",  # Sky Blue
            "#D55E00",  # Vermillion
            "#F0E442",  # Yellow
            "#808080",  # Gray
            "#4B0082",  # Indigo
            "#8B4513",  # Saddle Brown
            "#9932CC",  # Dark Orchid
            "#FF8C00",  # Dark Orange
            "#00CED1",  # Dark Turquoise
            "#FFD700",  # Gold
            "#CD5C5C",  # Indian Red
            "#6A5ACD",  # Slate Blue
            "#32CD32",  # Lime Green
            "#8B0000",  # Dark Red
            "#BA55D3",  # Medium Orchid
        ]
        survey_reference['conc_group'] = (survey_reference['Conc'] != survey_reference['Conc'].shift()).cumsum()
        for name, data in survey_reference.groupby('conc_group'):

            conc_val = data['Conc'].iloc[0]
            if data.index[-1] + 1 <= len(survey_reference):
                end_index = data.index[-1] + 1
                new_df = survey_reference.loc[data.index[0]:end_index]
            else:
                new_df = survey_reference.loc[data.index[0]:]
            used_well = new_df

            customdata_plat = np.column_stack((
                used_well['tvd'] * -1,  # Depth in feet
                used_well['measured_depth'],  # depth in MD
                used_well['inclination'],  # Inclination in degrees
                used_well['azimuth'],
                used_well['FNL'],
                used_well['FSL'],
                used_well['FEL'],
                used_well['FWL'],
                used_well['label'],))

            fig.add_trace(go.Scatter3d(
                x=used_well['easting'],
                y=used_well['northing'],
                z=used_well['tvd'] * -0.3048,
                customdata=customdata_plat,
                mode='lines',
                name=f'3d_{used_label} WellPath Inside Section {conc_val}',
                hovertemplate=hovertemplate,
                line=dict(color=plat_color_dict[conc_val], width=4)))

            fig.add_trace(go.Scatter3d(
                x=used_well['easting'],
                y=used_well['northing'],
                z=used_well['tvd'] * 0,
                customdata=customdata_plat,
                mode='lines',
                name=f'2d_{used_label} WellPath Inside Section {conc_val}',
                hovertemplate=hovertemplate,
                line=dict(color=plat_color_dict[conc_val], width=4)))

        traces_plats = [trace for trace in fig.data if trace.name.startswith('Plat')]
        traces_3d = [trace for trace in fig.data if trace.name.startswith('3d_')]
        traces_3d_planned = [trace for trace in traces_3d if trace.name[3:5] == 'Pl']
        traces_3d_drilled = [trace for trace in traces_3d if trace.name[3:5] != 'Pl']

        traces_2d = [trace for trace in fig.data if trace.name.startswith('2d_')]
        traces_2d_planned = [trace for trace in traces_2d if trace.name[3:5] == 'Pl']
        traces_2d_drilled = [trace for trace in traces_2d if trace.name[3:5] != 'Pl']

        spacer = add_spacer_trace()
        new_traces = (traces_plats + [spacer] +
                      traces_3d_planned + [spacer] +
                      traces_3d_drilled + [spacer] +
                      traces_2d_planned + [spacer] +
                      traces_2d_drilled + [spacer])
        # Remove all existing traces and add the new ones
        fig.data = []
        for trace in new_traces:
            fig.add_trace(trace)

        fig.write_html(self.temp_file_tsr.name, full_html=False, include_plotlyjs='cdn')
        self.web_view_tsr.load(QUrl.fromLocalFile(self.temp_file_tsr.name))

    def draw_general_viz_tab(self, survey_reference, hovertemplate, fig, given_color, label):
        def transform_string(s):
            part1 = str(int(s[:2]))
            part2 = str(int(s[2:4])) + s[4]
            part3 = str(int(s[5:7])) + s[7]
            part4 = s[-1]

            return f"{part1} {part2} {part3} {part4}"

        customdata_full = np.column_stack((
            survey_reference['tvd'] * -1,  # Depth in feet
            survey_reference['measured_depth'],  # depth in MD
            survey_reference['inclination'],  # Inclination in degrees
            survey_reference['azimuth'],  # Azimuth in degrees
            survey_reference['FNL'],
            survey_reference['FSL'],
            survey_reference['FEL'],
            survey_reference['FWL'],
            survey_reference['label'],))
        fig.add_trace(go.Scatter3d(
            x=survey_reference['easting'],
            y=survey_reference['northing'],
            z=survey_reference['tvd'] * -0.3048,
            customdata=customdata_full,

            mode='lines',
            name=f"""{label}_3d""",
            hovertemplate=hovertemplate,
            line=dict(color=given_color, width=4)))

        fig.add_trace(go.Scatter3d(
            x=survey_reference['easting'],
            y=survey_reference['northing'],
            z=survey_reference['tvd'] * 0,
            customdata=customdata_full,
            mode='lines',
            name=f"""{label}_2d""",
            hovertemplate=hovertemplate,

            line=dict(color=given_color, width=4)))

    def check_box_activate_path(self, lbl, state):
        plot_data = getattr(self, f"{lbl}_plot")
        scatter_data = getattr(self, f"{lbl}_scatter")
        bhl_pts = getattr(self, f"{lbl}_bhl")
        shl_pts = getattr(self, f"{lbl}_shl")

        if state == 2:
            plot_data.set_visible(True)
            scatter_data.set_visible(True)
            bhl_pts.set_visible(True)
            shl_pts.set_visible(True)

        else:
            plot_data.set_visible(False)
            scatter_data.set_visible(False)
            bhl_pts.set_visible(False)
            shl_pts.set_visible(False)

        self.update_2d_map()

    def draw_2d_data(self, df_survey, df_plat):
        self.plat_df = df_plat
        self.plat_drawer_process()
        self.plat_draw_wells_process(df_survey)
        # self.plat_draw_bhl_shl(df_survey)
        self.update_2d_map()

    def create_smaller_polygon(self, polygon, buffer):
        inner_polygon = polygon.buffer(-buffer)

        # Check if the operation resulted in a valid polygon
        if inner_polygon.is_empty:
            raise ValueError("Buffer distance too large, resulting polygon disappeared")

        return inner_polygon

    def plat_drawer_process(self):
        self.plat_df['geo_100ft'] = self.plat_df['geometry'].apply(lambda x: self.create_smaller_polygon(x, 100 * 0.3048))
        self.plat_df['geo_330ft'] = self.plat_df['geometry'].apply(lambda x: self.create_smaller_polygon(x, 330 * 0.3048))
        self.plats.set_segments(self.plat_df['geometry'].apply(lambda x: x.exterior.coords))
        self.plats_100.set_segments(self.plat_df['geo_100ft'].apply(lambda x: x.exterior.coords))

        self.plats_330.set_segments(self.plat_df['geo_330ft'].apply(lambda x: x.exterior.coords))
        self.ax_visual.add_collection(self.plats)
        self.ax_visual.add_collection(self.plats_100)
        self.ax_visual.add_collection(self.plats_330)
        self.plats_100.set_visible(False)
        self.plats_330.set_visible(False)
        paths_main = [PathPatch(TextPath((coord.x, coord.y), text, size=75), color="red") for coord, text in
                      zip(self.plat_df['centroid'], self.plat_df['label'])]
        self.labels_plats_2d.set_paths(paths_main)

    def plat_draw_bhl_shl(self, df_survey):
        # Option 1: Use a set to collect unique points during the loop
        shl_pts = set()  # initialize as set instead of list
        bhl_pts = set()
        for k, v in df_survey.items():
            unpacked_data = v.clearance_data
            point_shl = tuple(unpacked_data[['easting', 'northing']].iloc[0].values.tolist())  # convert to tuple for set
            point_bhl = tuple(unpacked_data[['easting', 'northing']].iloc[-1].values.tolist())  # convert to tuple for set

            shl_pts.add(point_shl)
            bhl_pts.add(point_bhl)
        # Convert back to list if needed
        shl_pts = list(shl_pts)
        bhl_pts = list(bhl_pts)

        self.bhl_pts.set_offsets(bhl_pts)
        self.bhl_pts.set_visible(False)

        self.shl_pts.set_offsets(shl_pts)
        self.shl_pts.set_visible(False)

    def plat_draw_wells_process(self, df_survey):
        id_dict = {'drl': "black", "pln": "red"}
        dashed_dict = {'drl': "-", "pln": "--"}
        for k, v in df_survey.items():
            unpacked_data = v.clearance_data
            point_shl = tuple(unpacked_data[['easting', 'northing']].iloc[0].values.tolist())  # convert to tuple for set
            point_bhl = tuple(unpacked_data[['easting', 'northing']].iloc[-1].values.tolist())
            color = id_dict[k[:3]]
            dash_type = dashed_dict[k[:3]]
            line_string_data = LineString(unpacked_data[['easting', 'northing']].values.tolist())
            # Create a new plot line for each key
            new_plot, = self.ax_visual.plot(
                [], [], color=color, linewidth=1, linestyle=dash_type, zorder=5, label=f"{k} Line")
            # Create a new scatter for each key
            new_scatter = self.ax_visual.scatter(
                [], [], c=color, s=8, zorder=5, label=f"{k} Scatter")
            new_bhl_pts = self.ax_visual.scatter([], [],
                                                 marker='o',
                                                 color='black',  # filled black circle
                                                 s=25,
                                                 zorder=1000, label=f"{k} BHL")
            new_shl_pts = self.ax_visual.scatter([], [],
                                                 marker='o',
                                                 color='white',  # white-filled circle
                                                 edgecolors='black',
                                                 s=25,
                                                 zorder=1000, label=f"{k} SHL")
            # Dynamically set the attributes
            setattr(self, f"{k}_plot", new_plot)
            setattr(self, f"{k}_scatter", new_scatter)
            setattr(self, f"{k}_bhl", new_bhl_pts)
            setattr(self, f"{k}_shl", new_shl_pts)

            plot_data = getattr(self, f"{k}_plot")
            scatter_data = getattr(self, f"{k}_scatter")
            bhl_pts = getattr(self, f"{k}_bhl")
            shl_pts = getattr(self, f"{k}_shl")

            x, y = line_string_data.xy
            plot_data.set_data(x, y)
            scatter_data.set_offsets(line_string_data.coords)
            bhl_pts.set_offsets(point_bhl)
            shl_pts.set_offsets(point_shl)

            plot_data.set_visible(False)
            scatter_data.set_visible(False)
            bhl_pts.set_visible(False)
            shl_pts.set_visible(False)

    def deg_to_dec(self, label):
        data_vals = [getattr(self.ui, f"{label}_deg").text(), getattr(self.ui, f"{label}_min").text(),
                     getattr(self.ui, f"{label}_sec").text()]
        data_vals = [abs(float(i)) for i in data_vals]
        data = data_vals[0] + data_vals[1] / 60 + data_vals[2] / 3600
        data = round(data, 6)
        return data

    def convert_lat_lon_pts_to_utm(self, data):
        try:
            utm_pts = utm.from_latlon(data[0], data[1])[:2]
        except utm.error.OutOfRangeError:
            utm_pts = data
        label = [round(data[0], 3), round(data[1], 3), int(utm_pts[0]), int(utm_pts[1])]
        label = [str(i) for i in label]
        label = f"""({label[0]},{label[1]}) | ({label[2]},{label[3]})"""
        return utm_pts, label

    def insert_user_generated_point(self):
        def drop_all_na(df):
            return df.loc[:, df.notna().any()]

        data = self.ui.lat_dec.text(), self.ui.lon_dec.text()
        if all(value == "" for value in data):
            data = self.deg_to_dec('lat'), -1 * self.deg_to_dec('lon')
        data = [float(i) for i in data]
        utm_pts, label = self.convert_lat_lon_pts_to_utm(data)
        new_row = pd.DataFrame(
            {'Label': [label], 'Easting': [utm_pts[0]], 'Northing': [utm_pts[1]], 'Geometry': [Point(utm_pts)]})
        # self.df_custom_viz_pts = pd.concat([self.df_custom_viz_pts, new_row], ignore_index=True).drop_duplicates(
        #     keep="first")
        self.df_custom_viz_pts = pd.concat([drop_all_na(self.df_custom_viz_pts), drop_all_na(new_row)],
                                           ignore_index=True).drop_duplicates(keep="first")
        self.update_plot_values()
        self.update_model_table()

    def update_plot_values(self):
        x = self.df_custom_viz_pts['Easting'].values
        y = self.df_custom_viz_pts['Northing'].values
        points = np.column_stack((x, y))
        self.scatter_custom_pts.set_offsets(points)
        self.update_2d_map()

    def update_model_table(self):
        self.added_viz_pts_model.removeRows(0, self.added_viz_pts_model.rowCount())
        for _, data in self.df_custom_viz_pts.iterrows():
            row = [data['Easting'], data['Northing']]
            items = [QStandardItem(str(item)) for item in row]
            for k in range(2):
                items[k].setData(row[k])
            self.added_viz_pts_model.appendRow(items)
            self.ui.insert_pts_lst.verticalHeader().setVisible(False)
            self.ui.insert_pts_lst.horizontalHeader().setVisible(False)
            self.ui.insert_pts_lst.setShowGrid(True)
            self.ui.insert_pts_lst.show()

    def update_model_table_when_user_modifies_values(self):
        table_data = [[self.added_viz_pts_model.data(self.added_viz_pts_model.index(row, column)) for column in
                       range(self.added_viz_pts_model.columnCount())] for row in
                      range(self.added_viz_pts_model.rowCount())]
        table_data = [i for i in table_data if i and None not in i and '' not in i]
        table_data = [[float(i[0]), float(i[1])] for i in table_data]
        x_data, y_data = [i[0] for i in table_data], [i[1] for i in table_data]
        self.df_custom_viz_pts = self.df_custom_viz_pts[
            (self.df_custom_viz_pts['Easting'].isin(x_data)) & (self.df_custom_viz_pts['Northing'].isin(y_data))]
        self.update_plot_values()
        self.update_model_table()

    def get_checked_surveys(self):
        """
        Retrieves a list of survey names for all checked checkboxes.

        Returns:
            list: A list containing the survey names of checked checkboxes.
        """
        checked_surveys = []
        for i in range(self.ui.surveys_draw_layout.count()):
            widget = self.ui.surveys_draw_layout.itemAt(i).widget()
            if isinstance(widget, QCheckBox) and widget.isChecked():
                survey_name = widget.property('survey_name')
                if survey_name:
                    checked_surveys.append(survey_name)
        return checked_surveys

    def click_on_2d_targeter(self, event):
        def draw_reticule(x, y):
            pts = [float(x), float(y)]
            self.ret_pts.set_offsets(pts)
            self.update_2d_map()

        def manifest_footage_data():
            self.ui.result_FEWL_box.setText(f"FNL: {round(pt_df['FNL'].iloc[0], 2)}")
            self.ui.result_FEWL_val_box.setText(f"FSL: {round(pt_df['FSL'].iloc[0], 2)}")
            self.ui.result_FNSL_box.setText(f"FEL: {round(pt_df['FEL'].iloc[0], 2)}")
            self.ui.result_FNSL_val_box.setText(f"FWL: {round(pt_df['FWL'].iloc[0], 2)}")
            self.ui.display_easting_box.setText(f"{round(x_selected, 0)}")
            self.ui.display_northing_box.setText(f"{round(y_selected, 0)}")
            lat_lon = utm.to_latlon(x_selected, y_selected, 12, 'T')
            self.ui.display_lat_box.setText(f"{round(lat_lon[0], 4)}")
            self.ui.display_lon_box.setText(f"{round(lat_lon[1], 4)}")

        mods = QGuiApplication.queryKeyboardModifiers()
        if event.inaxes is not None:
            if event.button == Qt.LeftButton and mods == Qt.ShiftModifier:
                x_selected, y_selected = event.xdata, event.ydata
                limit = (np.diff(self.ax_visual.get_xlim())[0] + np.diff(self.ax_visual.get_ylim())[0]) / 100
                pt_df = self.check_for_closest_points_on_lines(x_selected, y_selected, limit, self.df_survey)
                if pt_df.empty:
                    vals = [i for i, v in self.df_survey.items()]
                    pt_df = self.df_survey[vals[0]].find_single_point((x_selected, y_selected))
                    draw_reticule(x_selected, y_selected)
                    self.clear_clicked_data_table()
                    self.ui.dx_viz_data_table.setUpdatesEnabled(True)
                else:
                    draw_reticule(pt_df['easting'].iloc[0], pt_df['northing'].iloc[0])
                    self.update_clicked_data_table(pt_df)
                manifest_footage_data()

    def clear_clicked_data_table(self):
        self.added_viz_points_data_model.setRowCount(0)  # Clear existing rows efficiently
        self.ui.dx_viz_data_table.setModel(self.added_viz_points_data_model)
        self.ui.dx_viz_data_table.setUpdatesEnabled(False)


    def update_clicked_data_table(self, pt_df):
        self.clear_clicked_data_table()

        data = pt_df.values.tolist()
        self.added_viz_points_data_model.setRowCount(len(data))
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
                self.added_viz_points_data_model.setItem(row_idx, col_idx, item)





        #
        # for _, data in pt_df.iterrows():
        #     items = [QStandardItem(str(item)) for item in data]
        #     for k in range(len(data)):
        #         items[k].setData(data[k])
        #     self.added_viz_points_data_model.appendRow(items)

        columns = pt_df.columns.values
        self.added_viz_points_data_model.setHorizontalHeaderLabels(columns)
        # Configure the view settings after data insertion
        self.ui.dx_viz_data_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_viz_data_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.ui.dx_viz_data_table.verticalHeader().setVisible(False)
        self.ui.dx_viz_data_table.setShowGrid(True)

        # Re-enable updates and refresh the view
        self.ui.dx_viz_data_table.setUpdatesEnabled(True)
        self.ui.dx_viz_data_table.show()

    def check_for_closest_points_on_lines(self, x, y, limit, surveys):
        out_empty = pd.DataFrame()

        def processDataframeForDistance():
            df = data.clearance_data
            df['distance'] = np.sqrt((df['easting'].astype(float) - x) ** 2 + (
                    df['northing'].astype(float) - y) ** 2)
            closest_points_df = df[df['distance'] < limit]
            return closest_points_df

        surveys_in_use = self.get_checked_surveys()
        if surveys_in_use:
            for i in surveys_in_use:
                data = surveys[i]
                out = processDataframeForDistance()
                out_empty = pd.concat([out_empty, out], ignore_index=True)
            out_empty = out_empty.sort_values('distance').reset_index(drop=True)
            return out_empty.head(1)
        return out_empty

    # def click_on_2d_targeter2(self, event):
    #     def findWhatisChecked():
    #         def processDataframeForDistance(df, var_name):
    #             df['distance'] = np.sqrt((df['Easting'].astype(float) - x_selected) ** 2 + (
    #                     df['Northing'].astype(float) - y_selected) ** 2)
    #
    #             closest_points_df = df[df['distance'] < limit]
    #             closest_points_df['dataframe'] = var_name
    #             return closest_points_df
    #
    #         surveys_in_use = self.get_checked_surveys()
    #         closest_points1, closest_points2, closest_points3, closest_points4 = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    #         if self.ui.well_viz_grid_drilled_check.isChecked():
    #             closest_points1 = processDataframeForDistance(self.base_dx_df_drilled_new_grid,
    #                                                           'base_dx_df_drilled_new_grid')
    #         if self.ui.well_viz_true_drilled_check.isChecked():
    #             closest_points2 = processDataframeForDistance(self.base_dx_df_drilled_new_true,
    #                                                           'base_dx_df_drilled_new_true')
    #         if self.ui.well_viz_grid_planned_check.isChecked():
    #             closest_points3 = processDataframeForDistance(self.base_dx_df_planned_new_grid,
    #                                                           'base_dx_df_planned_new_grid')
    #         if self.ui.well_viz_true_planned_check.isChecked():
    #             closest_points4 = processDataframeForDistance(self.base_dx_df_planned_new_true,
    #                                                           'base_dx_df_planned_new_true')
    #
    #         closest1 = pd.concat([closest_points1, closest_points2], ignore_index=True)
    #         closest2 = pd.concat([closest_points3, closest_points4], ignore_index=True)
    #         closest_points = pd.concat([closest1, closest2], ignore_index=True).drop_duplicates(
    #             keep="first")
    #         # if self.ui.well_viz_drilled_check.isChecked() and not self.ui.well_viz_planned_check.isChecked():
    #         #     used_df = self.base_dx_df_drilled_new
    #         #     used_df = used_df[['Easting', 'Northing', 'shp_pt']]
    #         # elif not self.ui.well_viz_drilled_check.isChecked() and self.ui.well_viz_planned_check.isChecked():
    #         #     used_df = self.base_dx_df_planned_new
    #         #     used_df = used_df[['Easting', 'Northing', 'shp_pt']]
    #         # elif self.ui.well_viz_drilled_check.isChecked() and self.ui.well_viz_planned_check.isChecked():
    #         #     used_df = self.base_dx_df_new
    #         #     used_df = used_df[['Easting', 'Northing', 'shp_pt']]
    #         # else:
    #         #     if len(self.df_custom_viz_pts) == 0:
    #         #         return used_df
    #         # if len(self.df_custom_viz_pts) > 0:
    #         #     extra_df = self.df_custom_viz_pts[['Easting', 'Northing']]
    #         #     extra_df['shp_pt'] = extra_df.apply(lambda row: Point(row['Easting'], row['Northing']), axis=1)
    #         #     used_df = pd.concat([extra_df, used_df], ignore_index=True)
    #         #
    #         # used_df['distance'] = np.sqrt((used_df['Easting'].astype(float) - x_selected) ** 2 + (
    #         #         used_df['Northing'].astype(float) - y_selected) ** 2)
    #         # # Create a dataframe of points that are within the limit distance of the actively found points
    #         # used_df['distance'] = np.sqrt((used_df['Easting'].astype(float) - x_selected) ** 2 + (
    #         #         used_df['Northing'].astype(float) - y_selected) ** 2)
    #         #
    #         # closest_points = used_df[used_df['distance'] < limit]
    #         return closest_points
    #
    #     mods = QGuiApplication.queryKeyboardModifiers()
    #
    #     if event.inaxes is not None:
    #         if event.button == Qt.LeftButton and mods == Qt.ShiftModifier:
    #             self.targeting_reticule_process(event)
    #             x_selected, y_selected = event.xdata, event.ydata
    #             limit = (np.diff(self.ax_visual.get_xlim())[0] + np.diff(self.ax_visual.get_ylim())[0]) / 50
    #             closest_points = findWhatisChecked()
    #     #         if not closest_points.empty:
    #     #             closest_point = closest_points.loc[closest_points['distance'].idxmin()]
    #     #             self.selected_point_viz.set_offsets([closest_point['Easting'], closest_point['Northing']])
    #     #             self.retrieveDistanceMeasurements(closest_point)
    #     #             self.drawReticulePointToTable(closest_point)
    #     #         else:
    #     #             self.selected_point_viz.set_offsets([x_selected, y_selected])
    #     #
    #     # else:
    #     #     self.selected_point_viz.set_offsets([None, None])

    # def targeting_reticule_process(self, event):
    #     for _, row in self.plat_df.iterrows():
    #         if row['geometry'].contains(Point(event.xdata, event.ydata)):
    #             poly = list(row['geometry'].exterior.coords)
    #             point_used = [float(event.xdata), float(event.ydata)]
    #             data = [{'Easting': float(event.xdata), 'Northing': float(event.ydata)}]
    #             test_df = pd.DataFrame(data=data)
    #             test_df['Conc'] = row['Conc']
    #             test_df['point_index'] = 0
    #             # output_df, _ = self.clearance_for_points(test_df, self.plat_df)
    #             # dist_ns, dist_ew, mp_ns, mp_ew, original_ns_segment, original_ew_segment, pts, output_all, all_footage = self.process_point(poly,point_used)
    #             # self.drawReticule(pts, original_ew_segment, original_ns_segment, dist_ew, dist_ns)
    #             # self.ui.result_FEWL_box.setText(f"FNL - {output_df['FNL'].iloc[0]}")
    #             # self.ui.result_FEWL_val_box.setText(f"FSL - {output_df['FSL'].iloc[0]}")
    #             # self.ui.result_FNSL_box.setText(f"FEL - {output_df['FEL'].iloc[0]}")
    #             # self.ui.result_FNSL_val_box.setText(f"FWL - {output_df['FWL'].iloc[0]}")

    # def clearance_for_points(self, df_used, df_plat):
    #     def calculate_well_to_line_clearance_detailed(well_trajectory, line_points):
    #         well_trajectory = np.array(well_trajectory)
    #         line_points = np.array(line_points)
    #         p1, p2 = line_points
    #         line_vector = p2 - p1
    #         line_length_squared = np.sum(line_vector ** 2)
    #
    #         detailed_results = []
    #         for i, well_point in enumerate(well_trajectory):
    #             # Vector from line start to well point
    #             t = np.divide(np.dot(well_point - p1, line_vector), line_length_squared,
    #                           where=line_length_squared != 0,
    #                           out=np.zeros_like(line_length_squared))
    #             # Clamp t to [0, 1] to keep point on the segment
    #             t = max(0, min(1, t))
    #
    #             # Calculate the closest point on the line segment
    #             closest_point = p1 + t * line_vector
    #             # Calculate the distance
    #             distance = np.linalg.norm(well_point - closest_point)
    #
    #             # Calculate the angle
    #             well_to_closest = well_point - closest_point
    #             epsilon = 1e-10  # Adjust this value as needed
    #             angle = np.degrees(np.arccos(np.dot(well_to_closest, line_vector) /
    #                                          (np.linalg.norm(well_to_closest) * np.linalg.norm(line_vector) + epsilon)))
    #             # Ensure the angle is the smaller one (acute angle)
    #             if angle > 90:
    #                 angle = 180 - angle
    #
    #             result = {
    #                 "point_index": i,
    #                 "well_point": well_point,
    #                 "distance": distance,
    #                 "closest_surface_point": closest_point,
    #                 "intersection_angle": angle,
    #                 "original_segment": line_points
    #             }
    #             detailed_results.append(result)
    #
    #         return detailed_results
