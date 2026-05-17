"""
Visualization service for EToolsV3.

This service creates 2D and 3D visualizations of wellbore trajectories and plats.
"""

from typing import Optional, Tuple
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import plotly.graph_objects as go
import pandas as pd
import geopandas as gpd

from data.models.survey import ProcessedSurvey
from data.models.clearance import ClearanceResults
from config.logging_config import get_logger

logger = get_logger(__name__)


class VisualizationService:
    """Service for creating wellbore visualizations."""

    def __init__(self):
        """Initialize visualization service."""
        self.logger = logger

    def create_2d_plot(
        self,
        survey: ProcessedSurvey,
        plat_gdf: Optional[gpd.GeoDataFrame] = None,
        clearances: Optional[ClearanceResults] = None,
        figsize: Tuple[int, int] = (12, 10)
    ) -> Figure:
        """
        Create 2D matplotlib plot of wellbore trajectory and sections.

        Args:
            survey: Processed survey data.
            plat_gdf: Optional plat GeoDataFrame.
            clearances: Optional clearance results.
            figsize: Figure size (width, height).

        Returns:
            Matplotlib Figure object.
        """
        try:
            self.logger.info("Creating 2D plot")

            fig, ax = plt.subplots(figsize=figsize)

            # Plot plat sections if provided
            if plat_gdf is not None and not plat_gdf.empty:
                plat_gdf.plot(
                    ax=ax,
                    facecolor='lightgray',
                    edgecolor='black',
                    alpha=0.3,
                    linewidth=1
                )

                # Add section labels
                for _, plat in plat_gdf.iterrows():
                    if 'label' in plat and plat['centroid']:
                        ax.text(
                            plat['centroid'].x,
                            plat['centroid'].y,
                            plat['label'],
                            fontsize=8,
                            ha='center',
                            va='center'
                        )

            # Plot wellbore trajectory
            ax.plot(
                survey.data['easting'],
                survey.data['northing'],
                'b-',
                linewidth=2,
                label='Wellbore Trajectory'
            )

            # Mark surface location
            ax.plot(
                survey.data['easting'].iloc[0],
                survey.data['northing'].iloc[0],
                'go',
                markersize=10,
                label='Surface Location'
            )

            # Mark KOP if available
            if survey.kop_md is not None:
                kop_point = survey.data[survey.data['measured_depth'] >= survey.kop_md].iloc[0]
                ax.plot(
                    kop_point['easting'],
                    kop_point['northing'],
                    'ro',
                    markersize=8,
                    label=f'KOP @ {survey.kop_md:.0f} ft'
                )

            # Set labels and title
            ax.set_xlabel('Easting (ft)', fontsize=12)
            ax.set_ylabel('Northing (ft)', fontsize=12)
            ax.set_title(
                f'Wellbore Trajectory - API: {survey.header.api_number}, Lateral: {survey.header.lateral_name}',
                fontsize=14,
                fontweight='bold'
            )

            ax.legend()
            ax.grid(True, alpha=0.3)
            ax.set_aspect('equal')

            plt.tight_layout()

            return fig

        except Exception as e:
            self.logger.error(f"Failed to create 2D plot: {e}", exc_info=True)
            raise

    def create_3d_plot(
        self,
        survey: ProcessedSurvey,
        plat_gdf: Optional[gpd.GeoDataFrame] = None
    ) -> go.Figure:
        """
        Create 3D plotly plot of wellbore trajectory.

        Args:
            survey: Processed survey data.
            plat_gdf: Optional plat GeoDataFrame.

        Returns:
            Plotly Figure object.
        """
        try:
            self.logger.info("Creating 3D plot")

            fig = go.Figure()

            # Plot wellbore trajectory
            fig.add_trace(go.Scatter3d(
                x=survey.data['easting'],
                y=survey.data['northing'],
                z=-survey.data['tvd'],  # Negative for depth below surface
                mode='lines',
                name='Wellbore',
                line=dict(color='blue', width=4),
                hovertemplate='<b>MD:</b> %{text} ft<br>' +
                              '<b>TVD:</b> %{z:.1f} ft<br>' +
                              '<b>Easting:</b> %{x:.1f} ft<br>' +
                              '<b>Northing:</b> %{y:.1f} ft<br>',
                text=survey.data['measured_depth'].round(1)
            ))

            # Mark surface location
            fig.add_trace(go.Scatter3d(
                x=[survey.data['easting'].iloc[0]],
                y=[survey.data['northing'].iloc[0]],
                z=[0],
                mode='markers',
                name='Surface',
                marker=dict(size=10, color='green'),
                hovertext='Surface Location'
            ))

            # Mark KOP if available
            if survey.kop_md is not None:
                kop_point = survey.data[survey.data['measured_depth'] >= survey.kop_md].iloc[0]
                fig.add_trace(go.Scatter3d(
                    x=[kop_point['easting']],
                    y=[kop_point['northing']],
                    z=[-kop_point['tvd']],
                    mode='markers',
                    name=f'KOP @ {survey.kop_md:.0f} ft',
                    marker=dict(size=8, color='red'),
                    hovertext=f'Kick-Off Point: {survey.kop_md:.0f} ft MD'
                ))

            # Update layout
            fig.update_layout(
                title=f'3D Wellbore Trajectory - API: {survey.header.api_number}',
                scene=dict(
                    xaxis_title='Easting (ft)',
                    yaxis_title='Northing (ft)',
                    zaxis_title='TVD (ft)',
                    aspectmode='data'
                ),
                hovermode='closest',
                showlegend=True
            )

            return fig

        except Exception as e:
            self.logger.error(f"Failed to create 3D plot: {e}", exc_info=True)
            raise

    def create_vertical_section_plot(self, survey: ProcessedSurvey) -> Figure:
        """
        Create vertical section view (MD vs TVD).

        Args:
            survey: Processed survey data.

        Returns:
            Matplotlib Figure object.
        """
        try:
            fig, ax = plt.subplots(figsize=(10, 8))

            # Plot trajectory
            ax.plot(
                survey.data['measured_depth'],
                survey.data['tvd'],
                'b-',
                linewidth=2,
                label='Trajectory'
            )

            # Mark KOP if available
            if survey.kop_md is not None:
                kop_point = survey.data[survey.data['measured_depth'] >= survey.kop_md].iloc[0]
                ax.plot(
                    kop_point['measured_depth'],
                    kop_point['tvd'],
                    'ro',
                    markersize=8,
                    label=f'KOP @ {survey.kop_md:.0f} ft'
                )

            ax.set_xlabel('Measured Depth (ft)', fontsize=12)
            ax.set_ylabel('True Vertical Depth (ft)', fontsize=12)
            ax.set_title('Vertical Section View', fontsize=14, fontweight='bold')
            ax.legend()
            ax.grid(True, alpha=0.3)
            ax.invert_yaxis()  # Depth increases downward

            plt.tight_layout()

            return fig

        except Exception as e:
            self.logger.error(f"Failed to create vertical section plot: {e}", exc_info=True)
            raise
