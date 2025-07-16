import decimal
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union
from PyQt5.QtGui import QGuiApplication, QStandardItemModel, QStandardItem
from shapely.geometry import Point, LineString
from matplotlib.collections import PatchCollection, LineCollection, PolyCollection
from PyQt5.QtCore import Qt, QUrl
from matplotlib.textpath import TextPath
from matplotlib.patches import PathPatch
import utm
from PyQt5.QtWidgets import QCheckBox, QHeaderView, QAbstractItemView, QSizePolicy
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from PyQt5.QtWebEngineWidgets import QWebEngineView


def clear_widget(widget: Any) -> None:
    """Remove all child widgets from a container to prevent memory leaks.

    Iterates through container layout in reverse order to safely remove
    all child widgets. Reverse iteration prevents index shifting issues
    that can cause widgets to be skipped during removal process.

    Args:
        widget: Qt widget container with layout containing child widgets
    """
    for i in reversed(range(widget.layout().count())):
        widget.layout().itemAt(i).widget().setParent(None)


def clear_layout(layout: Any) -> None:
    """Clear all items from a layout and properly dispose of widgets.

    Performs comprehensive cleanup by removing layout items and explicitly
    deleting associated widgets. This prevents memory leaks and ensures
    clean slate for new visualizations.

    Args:
        layout: Qt layout object containing items to be removed
    """
    while layout.count():
        child = layout.takeAt(0)
        if child.widget():
            child.widget().deleteLater()
class ZoomPan:
    """Handles interactive zoom and pan functionality for matplotlib plots.

    This class provides a comprehensive solution for mouse-based navigation in 2D plots,
    implementing both scroll-wheel zooming and click-drag panning. It maintains state
    information about current view limits and mouse positions to enable smooth interaction.

    The zoom functionality uses a scaling approach where the zoom center point remains
    fixed under the mouse cursor, providing intuitive navigation. Pan functionality
    tracks mouse movement during drag operations to translate the view accordingly.

    Attributes:
        press: Stores mouse press state data during pan operations as tuple of
               (x0, y0, initial_xdata, initial_ydata) or None when not pressed
        cur_xlim: Current x-axis limits as numpy array during pan operations
        cur_ylim: Current y-axis limits as numpy array during pan operations
        x0, y0: Initial mouse coordinates when pan operation begins
        x1, y1: Current mouse coordinates during pan operation (reserved for future use)
        xpress, ypress: Mouse coordinates at the moment of initial press
        text_objects: List of matplotlib text objects that need font size updates during zoom
    """

    def __init__(self) -> None:
        """Initialize ZoomPan with default values for event handling.

        Sets all tracking variables to None or empty states. This initialization
        ensures clean state before any mouse interactions begin. The text_objects
        list is particularly important for maintaining readable text annotations
        as zoom levels change.
        """
        self.press: Optional[Tuple[float, float, float, float]] = None
        self.cur_xlim: Optional[np.ndarray] = None
        self.cur_ylim: Optional[np.ndarray] = None
        self.x0: Optional[float] = None
        self.y0: Optional[float] = None
        self.x1: Optional[float] = None
        self.y1: Optional[float] = None
        self.xpress: Optional[float] = None
        self.ypress: Optional[float] = None
        self.text_objects: List[Any] = []

    def zoom_factory(self, ax: plt.Axes, base_scale: float) -> Any:
        """Creates a zoom function for the given axes with adaptive text scaling.

        This method implements a sophisticated zoom system that maintains the point under
        the mouse cursor as the zoom center. The algorithm calculates new axis limits
        based on the scroll direction and applies proportional scaling. Additionally,
        it dynamically adjusts text annotation sizes to maintain readability across
        different zoom levels.

        The zoom implementation uses relative positioning to ensure the zoom center
        remains stationary. This is achieved by calculating the relative position of
        the mouse cursor within the current view bounds, then applying the zoom scale
        while maintaining that relative position.

        Args:
            ax: The matplotlib axes object to add zoom functionality to. This becomes
                the target for all zoom operations and limit adjustments.
            base_scale: The multiplicative zoom factor applied per scroll increment.
                       Values > 1.0 create zoom-out on scroll-up, < 1.0 creates zoom-in.
                       Typical values range from 1.1 to 1.5 for smooth interaction.

        Returns:
            The zoom function that handles mouse scroll events. This function can be
            stored for later disconnection if needed, though typically it remains
            active for the lifetime of the plot.

        Implementation Details:
            1. Captures current axis limits for baseline calculations
            2. Determines zoom direction from scroll event properties
            3. Calculates new view dimensions using scale factor
            4. Computes relative mouse position within current view
            5. Applies zoom while preserving mouse cursor position
            6. Updates text annotation sizes proportionally to zoom level
            7. Triggers canvas redraw to reflect changes
        """

        def zoom(event: Any) -> None:
            """Handle zoom events based on mouse scroll direction.

            This inner function performs the actual zoom calculations and axis updates.
            It implements a center-point zoom where the point under the mouse cursor
            remains fixed during the zoom operation, providing intuitive user experience.

            The text scaling feature ensures that annotations remain readable by
            inversely scaling font sizes relative to the zoom level. This prevents
            text from becoming too large when zoomed in or too small when zoomed out.

            Args:
                event: Mouse scroll event containing position data (xdata, ydata) and
                      scroll direction (button: 'up'/'down'). Also includes inaxes
                      property to verify the event occurred within the target axes.
            """
            # Verify event occurred within target axes to avoid interference
            if event.inaxes != ax:
                return

            # Capture current view state for calculations
            cur_xlim = ax.get_xlim()
            cur_ylim = ax.get_ylim()

            # Extract mouse position in data coordinates
            xdata = event.xdata
            ydata = event.ydata

            # Determine zoom direction and calculate scale factor
            # 'down' scroll typically indicates zoom-in, 'up' indicates zoom-out
            if event.button == 'down':
                scale_factor = 1 / base_scale  # Zoom in (smaller view)
            elif event.button == 'up':
                scale_factor = base_scale  # Zoom out (larger view)
            else:
                scale_factor = 1  # No change for other events

            # Calculate new view dimensions by scaling current dimensions
            new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
            new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor

            # Calculate relative position of mouse within current view
            # This ensures the zoom center remains under the mouse cursor
            relx = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
            rely = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])

            # Apply new limits centered on mouse position
            # The math ensures the point under cursor remains stationary
            ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * (relx)])
            ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * (rely)])

            # Update text annotation font sizes to maintain readability
            # Scale factor based on total view width for consistent sizing
            scale_factor = ax.get_xlim()[1] - ax.get_xlim()[0]
            for text in self.text_objects:
                new_fontsize = 12 / scale_factor * 2500  # Magic number for optimal scaling
                text.set_fontsize(new_fontsize)

            # Redraw canvas to reflect all changes
            ax.figure.canvas.draw()

        # Connect zoom function to scroll events and return for potential disconnection
        fig = ax.get_figure()
        fig.canvas.mpl_connect('scroll_event', zoom)
        return zoom

    def pan_factory(self, ax: plt.Axes) -> Any:
        """Creates comprehensive pan functionality for the given axes.

        This method implements a three-phase pan system: press, motion, and release.
        The pan operation tracks mouse movement during drag operations and translates
        the view accordingly. The implementation maintains smooth interaction by
        capturing initial state during press, tracking movement during motion, and
        cleaning up during release.

        The pan algorithm works by calculating the delta between current mouse position
        and the initial press position, then applying this delta as an offset to the
        axis limits. This creates the visual effect of "dragging" the plot content.

        Args:
            ax: The matplotlib axes object to add pan functionality to. This axes
                will respond to mouse drag operations for view translation.

        Returns:
            The motion function that handles mouse drag events. This allows for
            potential disconnection of the pan functionality if needed.

        Implementation Strategy:
            1. Press handler: Captures initial state and mouse position
            2. Motion handler: Calculates movement delta and updates view
            3. Release handler: Cleans up state and triggers final redraw
            4. All handlers include bounds checking to ensure events are valid
        """

        def onPress(event: Any) -> None:
            """Handle mouse press events to initiate pan operations.

            This function captures the initial state needed for pan calculations,
            including current axis limits and mouse position. The captured state
            is stored in instance variables for use during motion tracking.

            State capture is essential for smooth panning because it provides the
            baseline for calculating movement deltas during drag operations.

            Args:
                event: Mouse press event containing position and button information.
                      Must include inaxes property and coordinate data (xdata, ydata).
            """
            # Verify event occurred within target axes
            if event.inaxes != ax:
                return

            # Capture current axis limits for delta calculations
            self.cur_xlim = ax.get_xlim()
            self.cur_ylim = ax.get_ylim()

            # Store press state: (x0, y0, initial_xdata, initial_ydata)
            self.press = self.x0, self.y0, event.xdata, event.ydata
            self.x0, self.y0, self.xpress, self.ypress = self.press

        def onRelease(event: Any) -> None:
            """Handle mouse release events to complete pan operations.

            This function cleans up the pan state and triggers a final canvas redraw
            to ensure all visual changes are properly rendered. The state cleanup
            prevents interference with future pan operations.

            Args:
                event: Mouse release event (coordinates not needed for cleanup).
            """
            # Clear pan state to end drag operation
            self.press = None
            # Final redraw to ensure clean display
            ax.figure.canvas.draw()

        def onMotion(event: Any) -> None:
            """Handle mouse motion events during active panning.

            This function performs the core pan logic by calculating the movement
            delta since the initial press and applying it as an offset to the axis
            limits. The calculation preserves the visual relationship between mouse
            movement and plot content movement.

            The pan operation works by subtracting the movement delta from the axis
            limits, creating the effect of "dragging" the plot content in the
            opposite direction of mouse movement (standard pan behavior).

            Args:
                event: Mouse motion event containing current position data (xdata, ydata)
                      and inaxes property for bounds checking.
            """
            # Verify pan operation is active and event is within bounds
            if self.press is None:
                return
            if event.inaxes != ax:
                return

            # Calculate movement delta since initial press
            dx = event.xdata - self.xpress
            dy = event.ydata - self.ypress

            # Apply movement offset to axis limits (negative for intuitive panning)
            self.cur_xlim -= dx
            self.cur_ylim -= dy

            # Update axis limits with new calculated bounds
            ax.set_xlim(self.cur_xlim)
            ax.set_ylim(self.cur_ylim)

            # Immediate redraw for smooth visual feedback
            ax.figure.canvas.draw()

        # Connect all event handlers to the figure
        fig = ax.get_figure()
        fig.canvas.mpl_connect('button_press_event', onPress)
        fig.canvas.mpl_connect('button_release_event', onRelease)
        fig.canvas.mpl_connect('motion_notify_event', onMotion)

        # Return motion function for potential disconnection
        return onMotion


class DataDrawer:
    """Comprehensive visualization system for well survey data and geological plat information.

    This class serves as the central visualization engine for the engineering tools application,
    handling both 2D matplotlib-based plots and 3D plotly-based interactive visualizations.
    It manages complex geological survey data, plat boundaries, well trajectories, and user
    interaction features like point targeting and data inspection.

    The class integrates multiple visualization technologies:
    - Matplotlib for 2D engineering drawings with precise measurements
    - Plotly for 3D interactive visualizations with hover information
    - PyQt5 models for tabular data display and editing
    - Shapely geometries for spatial calculations and boundary handling

    Key Features:
        * Real-time survey path visualization with multiple data sources
        * Interactive plat boundary display with setback calculations
        * Point-and-click data inspection with detailed hover information
        * Coordinate system conversion between lat/lon and UTM
        * Dynamic text scaling and zoom/pan functionality
        * User-defined point insertion and management
        * Multi-format data export and display capabilities

    Attributes:
        df_survey: Dictionary containing survey datasets keyed by survey type
        ui: PyQt5 user interface object containing all visual components
        df_custom_viz_pts: DataFrame tracking user-added visualization points
        plat_df: DataFrame containing plat boundary and metadata information
        figure_visual: Matplotlib figure object for 2D visualizations
        canvas_visual: Qt canvas widget embedding the matplotlib figure
        ax_visual: Primary matplotlib axes for plot content
        Various scatter plot and line collection objects for different data layers
        Plotly figure objects for 3D visualizations with web-based rendering
    """

    def __init__(self, ui: Any, df_survey: Dict[str, Any]) -> None:
        """Initialize comprehensive visualization system with UI integration and data management.

        This constructor performs extensive setup of the visualization infrastructure,
        including matplotlib figure creation, PyQt5 model initialization, plotly figure
        setup, and event handler connection. The initialization process is designed to
        create a fully functional visualization system ready for immediate use.

        The setup process follows a specific order to ensure proper dependency resolution:
        1. UI cleanup and widget clearing to prevent memory leaks
        2. Data structure initialization for tracking points and boundaries
        3. Matplotlib figure and canvas setup for 2D visualization
        4. PyQt5 model creation for tabular data display and editing
        5. Event handler connection for interactive functionality
        6. Plotly figure initialization for 3D visualization capabilities
        7. Web view setup for rendering plotly content
        8. Zoom/pan functionality activation for smooth user interaction

        Args:
            ui: PyQt5 user interface object containing visual components including:
                - well_viz_display: Container for 2D matplotlib visualization
                - insert_pts_lst: Table view for user-added points
                - dx_viz_data_table: Table for displaying clicked point data
                - Various input fields for coordinate entry and display
                - Layout containers for organizing visualization components
            df_survey: Dictionary containing survey datasets where keys are survey
                      identifiers (e.g., 'drl_df_true_dx', 'pln_df_grid_dx') and
                      values are survey data objects containing clearance_data
                      DataFrames with well trajectory information

        Implementation Details:
            * Widget clearing prevents memory leaks from previous visualizations
            * Data structure initialization uses pandas for efficient data management
            * Event connections enable real-time user interaction
            * Temporary file creation supports plotly HTML rendering
            * Zoom/pan setup provides industry-standard navigation controls
        """



        # Store core data references for use throughout class
        self.df_survey = df_survey
        self.ui = ui

        # Clear existing visualization to prevent interference
        clear_widget(self.ui.well_viz_display)

        # Initialize data structures for tracking user interactions and custom points
        # DataFrame structure optimized for spatial data with Shapely integration
        self.df_custom_viz_pts = pd.DataFrame(columns=['Label', 'Easting', 'Northing', 'Geometry'])
        self.plat_df = pd.DataFrame()

        # Setup matplotlib infrastructure for 2D technical drawings
        # Figure size and DPI optimized for engineering visualization requirements
        self.figure_visual = plt.figure()
        self.canvas_visual = FigureCanvas(self.figure_visual)
        self.ax_visual = self.figure_visual.subplots()
        self.ui.well_viz_display.addWidget(self.canvas_visual)

        # Initialize PyQt5 data models for tabular display and editing
        # StandardItemModel provides flexible data management with Qt integration
        self.added_viz_pts_model = QStandardItemModel()
        self.ui.insert_pts_lst.setModel(self.added_viz_pts_model)

        # Connect model change signals to update functions for real-time synchronization
        self.added_viz_pts_model.dataChanged.connect(self.update_model_table_when_user_modifies_values)
        # Enable full editing capabilities for user point management
        self.ui.insert_pts_lst.setEditTriggers(QAbstractItemView.AllEditTriggers)

        # Setup secondary model for displaying clicked point detailed information
        self.added_viz_points_data_model = QStandardItemModel()
        self.ui.dx_viz_data_table.setModel(self.added_viz_points_data_model)

        # Connect mouse events for interactive point targeting and data inspection
        # Button press events enable click-to-inspect functionality
        self.canvas_visual.mpl_connect('button_press_event', self.click_on_2d_targeter)

        # Define comprehensive hover template for 3D plotly visualizations
        # Template includes all critical survey and geometric information
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

        # Prepare clean layout containers for 3D visualization components
        clear_layout(self.ui.well_viz_display_general)
        clear_layout(self.ui.well_viz_display_tsr)

        # Initialize plotly figures for interactive 3D visualization
        # Separate figures allow specialized display of different data aspects
        self.fig_general = go.Figure()  # General survey and well path visualization
        self.fig_tsr = go.Figure()  # Township, section, and range visualization

        # Create temporary HTML files for plotly rendering in Qt web views
        # Named temporary files persist for the session duration
        self.temp_file_general = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False)
        self.temp_file_tsr = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False)

        # Setup web view widgets for displaying plotly HTML content
        # Web views provide full plotly interactivity within Qt application
        self.web_view_general = QWebEngineView()
        self.ui.well_viz_display_general.addWidget(self.web_view_general)
        self.web_view_general.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ui.well_viz_display_general.setContentsMargins(0, 0, 0, 0)

        self.web_view_tsr = QWebEngineView()
        self.ui.well_viz_display_tsr.addWidget(self.web_view_tsr)
        self.web_view_tsr.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ui.well_viz_display_tsr.setContentsMargins(0, 0, 0, 0)

        # Initialize interactive zoom and pan functionality for professional navigation
        self.zp = ZoomPan()
        # Zoom factor of 1.1 provides smooth incremental zooming
        self.zoom_fac = self.zp.zoom_factory(self.ax_visual, 1.1)
        figPan = self.zp.pan_factory(self.ax_visual)
        # Equal aspect ratio ensures accurate geometric representation
        self.ax_visual.axis('equal')

        # Setup specialized scatter plots for different data visualization needs
        # Reticule for targeting specific points during user interaction
        self.ret_pts = self.ax_visual.scatter([], [], c='black', s=50, zorder=2, alpha=0.5)
        # Custom user-added points with distinct blue color
        self.scatter_custom_pts = self.ax_visual.scatter([], [], c='blue', s=10, zorder=2)
        # Bottom hole location markers (filled black circles)
        self.bhl_pts = self.ax_visual.scatter([], [], marker='o', color='black', s=25, zorder=1000)
        # Surface hole location markers (white with black outline for visibility)
        self.shl_pts = self.ax_visual.scatter([], [], marker='o', color='white',
                                              edgecolors='black', s=25, zorder=1000)

        # Setup line collections for efficient boundary visualization
        # Primary plat boundaries (section lines)
        self.plats = LineCollection([], color='black', linewidth=2, zorder=2)
        # 100-foot setback boundaries for regulatory compliance
        self.plats_100 = LineCollection([], color='black', linewidth=2, zorder=2)
        # 330-foot setback boundaries for additional regulatory requirements
        self.plats_330 = LineCollection([], color='black', linewidth=2, zorder=2)

        # Setup text label collection for township and range identification
        # PatchCollection allows efficient rendering of multiple text elements
        self.labels_plats_2d = PatchCollection([
            PathPatch(TextPath((coord.x, coord.y), text, size=75), color="red")
            for coord, text in zip([], [])], facecolors="black")
        self.ax_visual.add_collection(self.labels_plats_2d)

    def change_visibility_100(self, state: int) -> None:
        """Toggle visibility of 100-foot setback boundary lines based on checkbox state.

        This function manages the display of regulatory setback boundaries that are
        typically required for oil and gas operations. The 100-foot setback represents
        a common regulatory requirement for well spacing from property boundaries.

        The visibility toggle allows users to show or hide these boundaries as needed
        for different analysis purposes, reducing visual clutter when not required
        while maintaining easy access when regulatory compliance checking is needed.

        Args:
            state: Integer representing checkbox state where 2 indicates checked
                  (Qt.Checked) and any other value indicates unchecked. This
                  follows standard Qt checkbox state enumeration values.

        Implementation Notes:
            * Uses matplotlib LineCollection.set_visible() for efficient rendering
            * Triggers immediate map update to reflect visibility changes
            * Preserves line collection data - only changes visibility flag
            * Z-order maintained to ensure proper layering when visible
        """
        if state == 2:  # Qt.Checked state
            self.plats_100.set_visible(True)
        else:
            self.plats_100.set_visible(False)
        # Trigger immediate visual update to reflect change
        self.update_2d_map()

    def change_visibility_330(self, state: int) -> None:
        """Toggle visibility of 330-foot setback boundary lines based on checkbox state.

        This function controls the display of extended setback boundaries that may be
        required for certain types of wells or in specific regulatory jurisdictions.
        The 330-foot setback often represents requirements for horizontal wells or
        special environmental protection zones.

        Like the 100-foot setback, this toggle provides flexible visualization control
        allowing users to display only the relevant regulatory boundaries for their
        current analysis needs.

        Args:
            state: Integer representing checkbox state where 2 indicates checked
                  (Qt.Checked) and any other value indicates unchecked. This
                  follows standard Qt checkbox state enumeration values.

        Implementation Notes:
            * Parallel implementation to 100-foot setback for consistency
            * Maintains separate line collection for independent control
            * Efficient rendering through matplotlib visibility flags
            * Immediate visual feedback through map update call
        """
        if state == 2:  # Qt.Checked state
            self.plats_330.set_visible(True)
        else:
            self.plats_330.set_visible(False)
        # Trigger immediate visual update to reflect change
        self.update_2d_map()

    def update_2d_map(self) -> None:
        """Refresh the 2D visualization display with optimized rendering performance.

        This function performs efficient redrawing of the matplotlib canvas using
        blitting techniques to minimize computational overhead. Blitting redraws
        only the changed portions of the plot rather than the entire figure,
        providing smooth real-time interaction performance.

        The update process focuses on the main axes bounding box, which contains
        all the dynamic plot elements (survey lines, points, boundaries) while
        preserving static elements like axis labels and titles.

        Implementation Strategy:
            * Uses canvas.blit() for optimized partial redrawing
            * Targets specific axes bbox to minimize update area
            * Follows matplotlib best practices for interactive applications
            * Maintains smooth user experience during zoom/pan operations
        """
        # Perform optimized redraw of only the changed plot area
        self.canvas_visual.blit(self.ax_visual.bbox)
        # Complete the drawing operation to display changes
        self.canvas_visual.draw()

    def draw_3d_process(self, df: Dict[str, Any]) -> None:
        """Generate comprehensive 3D visualizations with interactive plotly figures.

        This function orchestrates the complete 3D visualization pipeline, combining
        plat boundary data with well survey information to create interactive 3D
        representations. The process involves data preparation, color assignment,
        figure generation, and web view rendering.

        The 3D visualization provides critical spatial understanding that 2D views
        cannot convey, particularly for complex well trajectories that may have
        significant vertical components or multiple horizontal sections.

        The function coordinates multiple visualization components:
        1. Plat boundary visualization with color coding for identification
        2. Survey path rendering with depth information and hover details
        3. HTML generation for web-based interactive display
        4. Web view loading for Qt application integration

        Args:
            df: Dictionary containing survey datasets where keys identify survey
                types and values contain survey objects with clearance_data
                DataFrames. Expected to include both planned and as-drilled
                surveys with complete trajectory information.

        Processing Pipeline:
            1. Clear existing figure data to prevent overlap
            2. Generate plat visualizations with color assignments
            3. Process survey data for 3D display
            4. Configure figure layouts and rendering options
            5. Generate HTML files for web view display
            6. Load content into Qt web view widgets
        """
        # Clear existing plot data to prevent accumulation and visual artifacts
        self.fig_general.data = []
        self.fig_tsr.data = []

        # Generate plat boundary visualizations and obtain color mapping
        # Color mapping ensures consistent identification across visualizations
        plat_color_dict = self.draw_plats()

        # Process survey data for interactive 3D display
        self.draw_general_process(self.df_survey, plat_color_dict)

        # Configure figure layouts and prepare for rendering
        self.load_figure(self.fig_general, self.web_view_general, self.temp_file_general)
        self.load_figure(self.fig_tsr, self.web_view_tsr, self.temp_file_tsr)

        # Generate HTML content and load into web views for display
        self.fig_general.write_html(self.temp_file_general.name)
        self.web_view_general.load(QUrl.fromLocalFile(self.temp_file_general.name))

        self.fig_tsr.write_html(self.temp_file_tsr.name)
        self.web_view_tsr.load(QUrl.fromLocalFile(self.temp_file_tsr.name))

    def load_figure(self, fig: go.Figure, view: QWebEngineView, temp: Any) -> None:
        """Configure comprehensive layout settings for professional plotly figure display.

        This function applies industry-standard layout configurations to plotly figures
        to ensure professional presentation and optimal user interaction. The layout
        settings are specifically tuned for engineering and geological data visualization
        requirements.

        The configuration includes legend positioning, axis labeling, aspect ratio
        management, and margin optimization. These settings ensure that the 3D
        visualizations are both informative and visually appealing while maintaining
        scientific accuracy.

        Args:
            fig: Plotly figure object to configure. Must be a valid go.Figure instance
                with traces already added. Configuration applies to the entire figure
                including all traces and layout elements.
            view: QWebEngineView widget for HTML display. Used for reference but not
                 directly modified by this function. The view will display the
                 configured figure after HTML generation.
            temp: Temporary file object for HTML output. Referenced for future
                 HTML generation but not used within this configuration function.

        Configuration Details:
            * Legend: Positioned vertically on the right side for easy access
            * Axes: Properly labeled with engineering units (meters)
            * Aspect: Data aspect mode ensures accurate geometric representation
            * Margins: Minimized to maximize plot area within available space
            * Scene: 3D scene configured for optimal spatial visualization
        """
        fig.update_layout(
            # Position legend outside plot area to avoid obscuring data
            legend=dict(
                orientation="v",  # Vertical orientation for space efficiency
                yanchor="top",  # Anchor to top for consistent positioning
                y=1,  # Full height utilization
                xanchor="left",  # Left-anchored for right-side placement
                x=1.02,  # Slight offset from plot area
            ),
            # Configure 3D scene for engineering visualization
            scene=dict(
                xaxis_title="Easting (m)",  # Standard surveying coordinate system
                yaxis_title="Northing (m)",  # UTM coordinate conventions
                zaxis_title="Depth (m)",  # Depth below surface reference
                aspectmode="data"  # Maintain true geometric proportions
            ),
            # Minimize margins to maximize plot utilization
            margin=dict(l=0, r=0, t=0, b=0)
        )

    def draw_plats(self) -> Dict[str, str]:
        """Generate comprehensive plat boundary visualizations with systematic color assignment.

        This function creates 3D representations of geological plat boundaries, applying
        systematic color coding for easy identification and visual differentiation.
        Plat boundaries represent legal land divisions that are critical for regulatory
        compliance and spatial analysis in oil and gas operations.

        The visualization process involves extracting boundary coordinates from shapely
        geometry objects, applying color assignments from a predefined palette, and
        creating 3D traces for plotly display. The function also manages the TSR
        (Township, Section, Range) specific visualization.

        The color assignment system uses a rotating palette to ensure visual distinction
        between different plats while maintaining consistency across visualization
        sessions. This systematic approach aids in rapid visual identification during
        analysis and regulatory review.

        Returns:
            Dictionary mapping plat identifiers (labels) to assigned colors. This
            mapping enables consistent color usage across different visualizations
            and ensures that the same plat always displays with the same color.
            Keys are plat label strings, values are color name strings from the
            predefined palette.

        Processing Steps:
            1. Initialize color palette with visually distinct colors
            2. Iterate through plat DataFrame extracting boundary geometries
            3. Assign colors using modulo operation for palette rotation
            4. Extract coordinate arrays from Shapely polygon boundaries
            5. Create plotly 3D traces with appropriate styling
            6. Add traces to TSR figure for township/range visualization
            7. Return color mapping (HTML generation moved to draw_3d_process)
        """
        # Initialize color mapping dictionary and define visual palette
        color_map = {}
        # Color palette selected for maximum visual distinction and professional appearance
        color_palette = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'gray']

        # Process each plat boundary for visualization
        for idx, (_, plat_row) in enumerate(self.plat_df.iterrows()):
            # Assign color using modulo to cycle through palette
            color = color_palette[idx % len(color_palette)]
            # Store color mapping for consistent usage across visualizations
            color_map[plat_row['label']] = color

            # Extract boundary coordinates from Shapely polygon geometry
            # exterior.coords provides the boundary points as coordinate pairs
            boundary_coords = list(plat_row['geometry'].exterior.coords)
            x_coords = [coord[0] for coord in boundary_coords]  # Easting values
            y_coords = [coord[1] for coord in boundary_coords]  # Northing values
            z_coords = [0] * len(boundary_coords)  # Ground level reference

            # Create 3D trace for plat boundary visualization
            trace = go.Scatter3d(
                x=x_coords,
                y=y_coords,
                z=z_coords,
                mode='lines',  # Line-only display for boundaries
                name=f"Plat {plat_row['label']}",  # Descriptive name for legend
                line=dict(color=color, width=2)  # Styled line with assigned color
            )
            # Add trace to township/section/range specific figure
            self.fig_tsr.add_trace(trace)

        # Return color mapping for use by other visualization functions
        # Note: HTML generation moved to draw_3d_process to ensure survey data is included
        return color_map

    def draw_general_process(self, survey_dict: Dict[str, Any], plat_color_dict: Dict[str, str]) -> None:
        """Process and visualize comprehensive survey data with color coordination.

        This function serves as the main coordinator for survey data visualization,
        handling multiple survey datasets and ensuring consistent color coding with
        plat boundaries. It processes each survey type (planned, as-drilled, true north,
        grid north) and creates appropriate 3D visualizations.

        The function implements a systematic approach to survey visualization that
        maintains visual consistency while providing clear differentiation between
        different survey types. Color assignments follow industry conventions where
        applicable (e.g., black for as-drilled, red for planned).

        Survey data processing involves extracting clearance data from survey objects,
        preparing hover information templates, and creating both 3D trajectory traces
        and 2D projection traces for comprehensive spatial understanding.

        Args:
            survey_dict: Dictionary containing survey datasets where keys are survey
                        type identifiers (e.g., 'drl_df_true_dx', 'pln_df_grid_dx')
                        and values are survey objects containing clearance_data
                        DataFrames with complete trajectory information.
            plat_color_dict: Color mapping from plat visualization to ensure consistent
                           color usage across all visualization components. Keys are
                           plat identifiers, values are color strings.

        Processing Strategy:
            1. Define color palette with industry-standard color conventions
            2. Iterate through survey datasets applying systematic color assignment
            3. Generate human-readable labels from technical survey identifiers
            4. Extract clearance data containing trajectory coordinates and measurements
            5. Call specialized visualization function for each survey dataset
            6. Maintain color consistency across all visualization elements
        """
        # Define color palette following industry conventions for survey visualization
        # Black: As-drilled surveys (actual well path)
        # Red: Planned surveys (proposed well path)
        # Blue: Alternative or comparison surveys
        # Green: Secondary reference surveys
        color_palette = ['black', 'red', 'blue', 'green']

        # Process each survey dataset with systematic color assignment
        for idx, (survey_key, survey_data) in enumerate(survey_dict.items()):
            # Assign color using modulo to cycle through palette
            color = color_palette[idx % len(color_palette)]

            # Generate human-readable label from technical survey identifier
            # Replace underscores with spaces and apply title case for presentation
            label = survey_key.replace('_', ' ').title()

            # Extract clearance data containing trajectory coordinates and measurements
            survey_reference = survey_data.clearance_data

            # Create comprehensive 3D visualization for this survey dataset
            self.draw_general_viz_tab(survey_reference, self.hovertemplate,
                                      self.fig_general, color, label)

    def draw_general_viz_tab(self, survey_reference: pd.DataFrame, hovertemplate: str,
                             fig: go.Figure, given_color: str, label: str) -> None:
        """Create detailed 3D survey visualization traces with comprehensive hover information.

        This function generates sophisticated 3D plotly traces for survey data, including
        both the actual 3D trajectory and a 2D surface projection. The implementation
        includes comprehensive hover information displaying all critical survey parameters
        and geometric measurements.

        The function creates two traces for each survey:
        1. 3D trajectory trace showing the actual well path in three dimensions
        2. 2D projection trace showing the surface projection for reference

        Both traces are added to BOTH the general figure and the TSR figure to ensure
        survey data appears in both visualization tabs. This allows users to see well
        paths in context with both general 3D visualization and township/range overlay.

        The hover template system provides instant access to critical information
        including measured depth, inclination, azimuth, true vertical depth, and
        boundary distance measurements (FNL, FSL, FEL, FWL).

        Args:
            survey_reference: DataFrame containing complete survey trajectory data with
                            columns for easting, northing, tvd (true vertical depth),
                            measured_depth, inclination, azimuth, and boundary distances.
                            Must include 'label' column for township/range identification.
            hovertemplate: HTML template string defining hover information layout and
                         formatting. Uses plotly template syntax with placeholder
                         references to customdata array indices.
            fig: Plotly figure object to receive the generated traces. Must be a
                valid go.Figure instance ready to accept 3D scatter traces.
            given_color: Color string for trace styling. Should be a valid CSS color
                        name or hex code for consistent visualization appearance.
            label: Human-readable identifier for the survey type, used in trace names
                  and legend entries. Typically derived from survey key with formatting.

        Data Processing Steps:
            1. Transform township/range labels for readable display
            2. Compile custom data array with all survey parameters
            3. Create 3D trajectory trace with depth conversion
            4. Create 2D surface projection trace for boundary analysis
            5. Apply consistent styling and hover information to both traces
            6. Add traces to BOTH general and TSR figures for complete visualization
        """

        def transform_string(s: str) -> str:
            """Transform township/range string format for human-readable display.

            Converts compressed township/range format (e.g., "01023N02E") into
            readable format (e.g., "1 23N 2E"). This transformation improves
            readability in hover displays and legend entries.

            Args:
                s: Township/range string in compressed format

            Returns:
                Formatted string with proper spacing and grouping
            """
            part1 = str(int(s[:2]))  # Section number
            part2 = str(int(s[2:4])) + s[4]  # Township with direction
            part3 = str(int(s[5:7])) + s[7]  # Range with direction
            part4 = s[-1]  # Additional identifier
            return f"{part1} {part2} {part3} {part4}"

        # Compile comprehensive custom data array for hover information
        # Array structure: [tvd, md, inc, az, fnl, fsl, fel, fwl, label]
        customdata_full = np.column_stack((
            survey_reference['tvd'] * -1,  # Depth (negative for below surface)
            survey_reference['measured_depth'],  # Measured depth along wellbore
            survey_reference['inclination'],  # Wellbore inclination angle
            survey_reference['azimuth'],  # Wellbore azimuth direction
            survey_reference['FNL'],  # From North Line distance
            survey_reference['FSL'],  # From South Line distance
            survey_reference['FEL'],  # From East Line distance
            survey_reference['FWL'],  # From West Line distance
            survey_reference['label'],  # Township/range identifier
        ))

        # Create 3D trajectory trace showing actual well path with depth
        trace_3d = go.Scatter3d(
            x=survey_reference['easting'],  # UTM easting coordinates
            y=survey_reference['northing'],  # UTM northing coordinates
            z=survey_reference['tvd'] * -0.3048,  # Depth in meters (feet to meters conversion)
            customdata=customdata_full,  # Complete data array for hover
            mode='lines',  # Line-only display for trajectory
            name=f"{label}_3d",  # Descriptive name for legend
            hovertemplate=hovertemplate,  # Comprehensive hover information
            line=dict(color=given_color, width=4)  # Styled line with specified color
        )

        # Create 2D surface projection trace for boundary analysis
        trace_2d = go.Scatter3d(
            x=survey_reference['easting'],  # Same X coordinates
            y=survey_reference['northing'],  # Same Y coordinates
            z=survey_reference['tvd'] * 0,  # Surface level (Z=0)
            customdata=customdata_full,  # Identical hover data
            mode='lines',  # Line-only display
            name=f"{label}_2d",  # Descriptive name indicating projection
            hovertemplate=hovertemplate,  # Same hover information template
            line=dict(color=given_color, width=4)  # Consistent styling
        )

        # Add traces to the passed figure (general figure)
        fig.add_trace(trace_3d)
        fig.add_trace(trace_2d)

        # Also add traces to TSR figure so survey data appears on both tabs
        # Create copies with TSR-specific names to avoid legend conflicts
        trace_3d_tsr = go.Scatter3d(
            x=survey_reference['easting'],
            y=survey_reference['northing'],
            z=survey_reference['tvd'] * -0.3048,
            customdata=customdata_full,
            mode='lines',
            name=f"{label}_3d_TSR",
            hovertemplate=hovertemplate,
            line=dict(color=given_color, width=4)
        )

        trace_2d_tsr = go.Scatter3d(
            x=survey_reference['easting'],
            y=survey_reference['northing'],
            z=survey_reference['tvd'] * 0,
            customdata=customdata_full,
            mode='lines',
            name=f"{label}_2d_TSR",
            hovertemplate=hovertemplate,
            line=dict(color=given_color, width=4)
        )

        # Add survey traces to TSR figure for combined plat/survey visualization
        self.fig_tsr.add_trace(trace_3d_tsr)
        self.fig_tsr.add_trace(trace_2d_tsr)

    def check_box_activate_path(self, lbl: str, state: int) -> None:
        """Manage visibility of survey path visualization elements through checkbox controls.

        This function provides centralized control over the visibility of all visual
        elements associated with a specific survey path. Each survey type has multiple
        associated visual elements (trajectory line, scatter points, hole locations)
        that must be controlled as a cohesive group.

        The function uses dynamic attribute access to manage survey-specific plot
        elements, allowing the same control logic to work with any number of survey
        types without requiring survey-specific code branches.

        Survey visualization elements controlled:
        - Main trajectory line showing the well path
        - Scatter points marking survey measurement locations
        - Bottom hole location (BHL) marker showing well terminus
        - Surface hole location (SHL) marker showing well origin

        Args:
            lbl: Survey identifier string used as suffix for plot element attribute
                names. Must match the naming convention used during plot element
                creation (e.g., 'drl_df_true_dx' creates 'drl_df_true_dx_plot').
            state: Integer representing checkbox state where 2 indicates checked
                  (Qt.Checked) and any other value indicates unchecked. This
                  follows standard Qt checkbox state enumeration values.

        Implementation Details:
            * Uses getattr() for dynamic access to survey-specific plot elements
            * Controls four distinct visual elements per survey for complete management
            * Triggers immediate map update to reflect visibility changes
            * Maintains element data - only changes visibility flags for efficiency
        """
        # Access survey-specific plot elements using dynamic attribute names
        plot_data = getattr(self, f"{lbl}_plot")  # Main trajectory line
        scatter_data = getattr(self, f"{lbl}_scatter")  # Survey measurement points
        bhl_pts = getattr(self, f"{lbl}_bhl")  # Bottom hole location marker
        shl_pts = getattr(self, f"{lbl}_shl")  # Surface hole location marker

        # Apply visibility state to all associated visual elements
        if state == 2:  # Qt.Checked - show all elements
            plot_data.set_visible(True)
            scatter_data.set_visible(True)
            bhl_pts.set_visible(True)
            shl_pts.set_visible(True)
        else:  # Unchecked - hide all elements
            plot_data.set_visible(False)
            scatter_data.set_visible(False)
            bhl_pts.set_visible(False)
            shl_pts.set_visible(False)

        # Trigger immediate visual update to reflect visibility changes
        self.update_2d_map()

    def draw_2d_data(self, df_survey: Dict[str, Any], df_plat: pd.DataFrame) -> None:
        """Coordinate comprehensive 2D visualization of integrated survey and plat data.

        This function serves as the main coordinator for 2D technical drawing generation,
        combining geological plat boundaries with well survey trajectories to create
        comprehensive engineering visualizations. The process follows a specific order
        to ensure proper layering and visual hierarchy.

        The 2D visualization provides the technical accuracy required for engineering
        analysis, regulatory compliance, and field operations planning. It combines
        multiple data sources into a unified view that supports both high-level
        planning and detailed technical review.

        The visualization process is structured to handle complex datasets efficiently
        while maintaining the precision required for engineering applications. Proper
        layering ensures that critical information remains visible and accessible.

        Args:
            df_survey: Dictionary containing survey datasets where keys identify survey
                      types (e.g., 'drl_df_true_dx', 'pln_df_grid_dx') and values
                      contain survey objects with clearance_data DataFrames containing
                      complete trajectory information and boundary calculations.
            df_plat: DataFrame containing plat boundary information with geometry
                    columns containing Shapely polygon objects representing legal
                    land boundaries, and label columns for identification.

        Processing Sequence:
            1. Store plat data reference for use throughout visualization process
            2. Process plat boundaries including setback calculations and labels
            3. Process well trajectories with proper styling and identification
            4. Trigger map update to display all processed visualization elements

        Layer Organization:
            * Base layer: Plat boundaries and labels for spatial reference
            * Middle layer: Setback boundaries for regulatory compliance
            * Top layer: Well trajectories and measurement points for analysis focus
        """
        # Store plat data reference for use throughout visualization process
        self.plat_df = df_plat

        # Process plat boundaries, setbacks, and identification labels
        # This creates the base layer providing spatial and regulatory context
        self.plat_drawer_process()

        # Process well survey trajectories with appropriate styling and markers
        # This creates the analysis layer containing well path and measurement data
        self.plat_draw_wells_process(df_survey)

        # Trigger comprehensive map update to display all processed elements
        self.update_2d_map()

    def create_smaller_polygon(self, polygon: Any, buffer: float) -> Any:
        """Generate inset polygons for regulatory setback boundary visualization.

        This function creates reduced-size polygons by applying negative buffer
        operations to existing polygon boundaries. The technique is essential for
        visualizing regulatory setback requirements in oil and gas operations,
        where wells must maintain specified distances from property boundaries.

        The buffer operation uses computational geometry to create parallel
        boundaries at specified distances from the original boundary lines.
        Negative buffer values create inward offsets, representing the area
        that remains available for well placement after setback requirements.

        The function includes error handling for cases where the buffer distance
        exceeds the polygon size, which would result in empty geometries that
        cannot be visualized or analyzed.

        Args:
            polygon: Shapely polygon object representing the original boundary.
                    Must be a valid polygon with sufficient area to accommodate
                    the specified buffer distance without disappearing.
            buffer: Buffer distance in meters for inward offset. Positive values
                   create outward expansion, negative values create inward reduction.
                   For setback visualization, negative values are typically used.

        Returns:
            Shapely polygon object representing the buffered boundary. Will be
            smaller than the original polygon when using negative buffer values.
            Maintains the same coordinate system and projection as input polygon.

        Raises:
            ValueError: When buffer distance is too large relative to polygon size,
                       resulting in complete polygon disappearance. This typically
                       occurs when setback requirements exceed available space.

        Implementation Notes:
            * Uses Shapely's buffer() method with standard resolution settings
            * Negative buffer values create inward offsets for setback visualization
            * Error checking prevents invalid geometry generation
            * Maintains coordinate precision throughout buffering operation
        """
        # Apply negative buffer to create inward offset for setback visualization
        inner_polygon = polygon.buffer(-buffer)

        # Verify that buffering operation produced valid geometry
        if inner_polygon.is_empty:
            raise ValueError("Buffer distance too large, resulting polygon disappeared")

        return inner_polygon

    def plat_drawer_process(self) -> None:
        """Generate comprehensive plat boundary visualizations with regulatory setback calculations.

        This function performs the complete processing of plat boundary data to create
        multi-layered boundary visualizations including primary boundaries and regulatory
        setback boundaries. The process involves geometric calculations, line collection
        setup, and text label generation for comprehensive spatial reference.

        The function creates three distinct boundary layers:
        1. Primary plat boundaries (legal property lines)
        2. 100-foot setback boundaries (common regulatory requirement)
        3. 330-foot setback boundaries (extended regulatory requirement)

        Each boundary layer is managed as a separate matplotlib LineCollection for
        efficient rendering and independent visibility control. The setback calculations
        use computational geometry to ensure accurate distance measurements.

        Text labeling provides township, section, and range identification using
        matplotlib's TextPath system for precise positioning and professional
        appearance. Labels are positioned at polygon centroids for optimal visibility.

        Processing Steps:
            1. Calculate 100-foot setback boundaries using negative buffering
            2. Calculate 330-foot setback boundaries using negative buffering
            3. Extract coordinate arrays from polygon geometries for line collections
            4. Configure line collections with appropriate styling and z-ordering
            5. Add line collections to axes with proper layering
            6. Set initial visibility states (setbacks hidden by default)
            7. Generate text labels at centroid positions with professional styling
            8. Add text labels to axes for township/range identification

        Geometric Calculations:
            * Buffer distances converted from feet to meters (multiplication by 0.3048)
            * Negative buffering creates inward offsets representing available area
            * Error handling for cases where setbacks exceed available space
            * Coordinate extraction preserves precision for accurate visualization
        """
        # Calculate regulatory setback boundaries using computational geometry
        # 100-foot setback (common regulatory requirement converted to meters)
        self.plat_df['geo_100ft'] = self.plat_df['geometry'].apply(
            lambda x: self.create_smaller_polygon(x, 100 * 0.3048))
        # 330-foot setback (extended regulatory requirement converted to meters)
        self.plat_df['geo_330ft'] = self.plat_df['geometry'].apply(
            lambda x: self.create_smaller_polygon(x, 330 * 0.3048))

        # Configure line collections for efficient boundary rendering
        # Primary boundaries: Legal property lines in black
        self.plats.set_segments(self.plat_df['geometry'].apply(lambda x: x.exterior.coords))
        # 100-foot setbacks: Regulatory compliance boundaries
        self.plats_100.set_segments(self.plat_df['geo_100ft'].apply(lambda x: x.exterior.coords))
        # 330-foot setbacks: Extended regulatory compliance boundaries
        self.plats_330.set_segments(self.plat_df['geo_330ft'].apply(lambda x: x.exterior.coords))

        # Add line collections to axes with proper z-ordering for layering
        self.ax_visual.add_collection(self.plats)  # Base layer: primary boundaries
        self.ax_visual.add_collection(self.plats_100)  # Middle layer: 100ft setbacks
        self.ax_visual.add_collection(self.plats_330)  # Top layer: 330ft setbacks

        # Set initial visibility states (setbacks hidden to reduce visual clutter)
        self.plats_100.set_visible(False)
        self.plats_330.set_visible(False)

        # Generate professional text labels for township/range identification
        # TextPath creates vector-based text for scalable, high-quality labels
        paths_main = [PathPatch(TextPath((coord.x, coord.y), text, size=75), color="red")
                      for coord, text in zip(self.plat_df['centroid'], self.plat_df['label'])]
        # Apply generated text paths to label collection for display
        self.labels_plats_2d.set_paths(paths_main)

    def plat_draw_wells_process(self, df_survey: Dict[str, Any]) -> None:
        """Generate comprehensive well trajectory visualizations with industry-standard styling.

        This function creates detailed 2D visualizations of well trajectories, including
        trajectory lines, measurement points, and critical location markers. The
        implementation follows industry conventions for color coding and styling to
        ensure immediate visual identification of different survey types.

        The function processes each survey dataset to create four distinct visual
        elements:
        1. Trajectory line showing the complete well path
        2. Scatter points marking survey measurement locations
        3. Bottom Hole Location (BHL) marker indicating well terminus
        4. Surface Hole Location (SHL) marker indicating well origin

        Industry-standard color conventions are applied:
        - Black: As-drilled surveys (actual well path)
        - Red: Planned surveys (proposed well path)
        - Dashed lines: Planned surveys for easy distinction from actual
        - Solid lines: As-drilled surveys for definitive representation

        The function uses dynamic attribute assignment to create survey-specific
        plot elements that can be controlled independently for flexible visualization
        management. All elements are initially hidden to allow user-controlled
        display through checkbox interfaces.

        Args:
            df_survey: Dictionary containing survey datasets where keys are survey
                      type identifiers (e.g., 'drl_df_true_dx', 'pln_df_grid_dx')
                      and values are survey objects containing clearance_data
                      DataFrames with easting, northing, and measurement information.

        Processing Steps for Each Survey:
            1. Extract clearance data containing trajectory coordinates
            2. Identify surface and bottom hole locations from trajectory endpoints
            3. Apply industry-standard color coding based on survey type
            4. Create LineString geometry for efficient coordinate handling
            5. Generate matplotlib plot elements with appropriate styling
            6. Use dynamic attribute assignment for flexible element management
            7. Update plot elements with coordinate data and styling
            8. Set initial visibility state (hidden for user control)

        Styling Conventions:
            * Line colors: Black for drilled, red for planned
            * Line styles: Solid for drilled, dashed for planned
            * Point markers: Filled black circles for BHL, white with black edge for SHL
            * Z-order: High values ensure visibility above background elements
        """
        # Define industry-standard color and style conventions
        id_dict = {'drl': "black", "pln": "red"}  # Color coding by survey type
        dashed_dict = {'drl': "-", "pln": "--"}  # Line style by survey type

        # Process each survey dataset for comprehensive visualization
        for k, v in df_survey.items():
            # Extract trajectory data from survey clearance calculations
            unpacked_data = v.clearance_data

            # Identify critical well locations from trajectory endpoints
            # Surface Hole Location: First point in trajectory (well origin)
            point_shl = tuple(unpacked_data[['easting', 'northing']].iloc[0].values.tolist())
            # Bottom Hole Location: Last point in trajectory (well terminus)
            point_bhl = tuple(unpacked_data[['easting', 'northing']].iloc[-1].values.tolist())

            # Apply styling based on survey type identification
            color = id_dict[k[:3]]  # Extract survey type prefix for color lookup
            dash_type = dashed_dict[k[:3]]  # Extract survey type prefix for line style

            # Create LineString geometry for efficient coordinate manipulation
            line_string_data = LineString(unpacked_data[['easting', 'northing']].values.tolist())

            # Generate matplotlib plot elements with professional styling
            # Trajectory line: Complete well path visualization
            new_plot, = self.ax_visual.plot(
                [], [],  # Empty data for initial creation
                color=color,  # Survey-type specific color
                linewidth=1,  # Standard line width for clarity
                linestyle=dash_type,  # Survey-type specific line style
                zorder=5,  # High z-order for visibility
                label=f"{k} Line"  # Descriptive label for legend
            )
            # Measurement points: Survey station locations
            new_scatter = self.ax_visual.scatter(
                [], [],  # Empty data for initial creation
                c=color,  # Consistent color with trajectory
                s=8,  # Small point size to avoid clutter
                zorder=5,  # High z-order for visibility
                label=f"{k} Scatter"  # Descriptive label for legend
            )
            # Bottom Hole Location: Well terminus marker
            new_bhl_pts = self.ax_visual.scatter(
                [], [],  # Empty data for initial creation
                marker='o',  # Circle marker for clear identification
                color='black',  # Standard black fill for BHL
                s=25,  # Larger size for importance
                zorder=1000,  # Very high z-order for prominence
                label=f"{k} BHL"  # Descriptive label for legend
            )
            # Surface Hole Location: Well origin marker
            new_shl_pts = self.ax_visual.scatter(
                [], [],  # Empty data for initial creation
                marker='o',  # Circle marker for clear identification
                color='white',  # White fill for contrast
                edgecolors='black',  # Black outline for definition
                s=25,  # Larger size for importance
                zorder=1000,  # Very high z-order for prominence
                label=f"{k} SHL"  # Descriptive label for legend
            )

            # Use dynamic attribute assignment for flexible plot element management
            # This enables survey-specific control through checkbox interfaces
            setattr(self, f"{k}_plot", new_plot)  # Store trajectory line reference
            setattr(self, f"{k}_scatter", new_scatter)  # Store scatter points reference
            setattr(self, f"{k}_bhl", new_bhl_pts)  # Store BHL marker reference
            setattr(self, f"{k}_shl", new_shl_pts)  # Store SHL marker reference

            # Access stored plot elements for data assignment
            plot_data = getattr(self, f"{k}_plot")
            scatter_data = getattr(self, f"{k}_scatter")
            bhl_pts = getattr(self, f"{k}_bhl")
            shl_pts = getattr(self, f"{k}_shl")

            # Update plot elements with actual coordinate data
            x, y = line_string_data.xy  # Extract coordinates from LineString
            plot_data.set_data(x, y)  # Assign trajectory coordinates
            scatter_data.set_offsets(line_string_data.coords)  # Assign measurement points
            bhl_pts.set_offsets(point_bhl)  # Assign bottom hole location
            shl_pts.set_offsets(point_shl)  # Assign surface hole location

            # Set initial visibility state (hidden for user-controlled display)
            plot_data.set_visible(False)
            scatter_data.set_visible(False)
            bhl_pts.set_visible(False)
            shl_pts.set_visible(False)

    def deg_to_dec(self, label: str) -> float:
        """Convert degrees/minutes/seconds coordinate format to decimal degrees.

        This function performs precise coordinate conversion from traditional
        surveying format (degrees, minutes, seconds) to decimal degrees required
        for modern GIS and mapping applications. The conversion maintains high
        precision suitable for engineering and surveying applications.

        The function uses dynamic UI field access to retrieve coordinate components
        from user interface elements, allowing the same conversion logic to work
        for both latitude and longitude coordinates through the label parameter.

        Mathematical conversion follows standard geodetic formulas:
        decimal_degrees = degrees + (minutes / 60) + (seconds / 3600)

        Args:
            label: Coordinate type prefix for UI field identification. Expected
                  values are 'lat' for latitude or 'lon' for longitude. This
                  prefix is used to construct UI field names for data retrieval
                  (e.g., 'lat_deg', 'lat_min', 'lat_sec').

        Returns:
            Decimal degree value with 6-decimal-place precision suitable for
            engineering applications. Precision level supports meter-level
            accuracy for survey and mapping purposes.

        Implementation Details:
            * Uses getattr() for dynamic UI field access based on label prefix
            * Applies abs() to handle both positive and negative coordinate values
            * Rounds result to 6 decimal places for consistent precision
            * Follows standard geodetic conversion formulas for accuracy
        """
        # Retrieve coordinate components from UI fields using dynamic access
        data_vals = [getattr(self.ui, f"{label}_deg").text(),  # Degrees component
                     getattr(self.ui, f"{label}_min").text(),  # Minutes component
                     getattr(self.ui, f"{label}_sec").text()]  # Seconds component

        # Convert to absolute float values to handle negative coordinates properly
        data_vals = [abs(float(i)) for i in data_vals]

        # Apply standard geodetic conversion formula
        data = data_vals[0] + data_vals[1] / 60 + data_vals[2] / 3600

        # Round to 6 decimal places for consistent precision
        data = round(data, 6)
        return data

    def convert_lat_lon_pts_to_utm(self, data: List[float]) -> Tuple[Tuple[float, float], str]:
        """Convert latitude/longitude coordinates to UTM projection with error handling.

        This function performs coordinate system conversion from geographic coordinates
        (latitude/longitude) to Universal Transverse Mercator (UTM) projection,
        which is the standard for engineering and surveying applications. The conversion
        includes comprehensive error handling for coordinates outside valid UTM zones.

        The function applies standard longitude sign conventions for Western Hemisphere
        coordinates and includes fallback handling for coordinates that cannot be
        converted to UTM. The generated label provides both coordinate systems for
        user reference and verification.

        UTM conversion is essential for accurate distance and area calculations in
        engineering applications, as it provides a metric coordinate system with
        minimal distortion over local areas.

        Args:
            data: List containing [latitude, longitude] values in decimal degrees.
                 Latitude should be positive for Northern Hemisphere, longitude
                 should be negative for Western Hemisphere (standard conventions).

        Returns:
            Tuple containing:
            - UTM coordinates as (easting, northing) tuple in meters
            - Formatted label string showing both lat/lon and UTM coordinates
              for user reference and verification purposes

        Error Handling:
            * OutOfRangeError: Returns original coordinates if UTM conversion fails
            * Label generation continues with available coordinate data
            * Graceful degradation maintains functionality with invalid coordinates

        Implementation Notes:
            * Applies Western Hemisphere longitude sign convention automatically
            * Uses utm library for accurate zone determination and conversion
            * Label format: "(lat,lon) | (easting,northing)" for easy reference
            * Coordinate rounding provides appropriate precision for display
        """
        try:
            # Apply Western Hemisphere longitude sign convention
            data[1] = abs(data[1]) * -1
            # print('data', data)  # Debug output for coordinate verification
            # Perform UTM conversion using standard algorithms
            utm_pts = utm.from_latlon(data[0], data[1])[:2]
        except utm.error.OutOfRangeError:
            # Fallback: use original coordinates if UTM conversion fails
            utm_pts = data

        # Generate formatted label showing both coordinate systems
        label = [round(data[0], 3),  # Latitude with 3 decimal places
                 round(data[1], 3),  # Longitude with 3 decimal places
                 int(utm_pts[0]),  # UTM easting as integer
                 int(utm_pts[1])]  # UTM northing as integer
        label = [str(i) for i in label]
        # Format: "(lat,lon) | (easting,northing)"
        label = f"({label[0]},{label[1]}) | ({label[2]},{label[3]})"
        return utm_pts, label

    def insert_user_generated_point(self) -> None:
        """Add user-specified coordinate point to visualization with comprehensive data management.

        This function enables users to add custom reference points to the visualization
        by converting coordinate inputs to appropriate formats and integrating them
        into the existing data management system. The function handles multiple input
        formats and maintains data consistency across visualization updates.

        The implementation supports two input methods:
        1. Direct decimal degree entry through dedicated UI fields
        2. Degrees/minutes/seconds entry through component fields

        The function performs coordinate system conversion, creates appropriate geometry
        objects, and updates both the visual display and underlying data structures
        to maintain synchronization across all visualization components.

        Data Management Process:
            1. Retrieve coordinate data from UI input fields
            2. Apply coordinate conversion (degrees/minutes/seconds if needed)
            3. Perform coordinate system conversion (lat/lon to UTM)
            4. Create Shapely Point geometry for spatial operations
            5. Update DataFrame with new point data
            6. Refresh visualization displays to show new point
            7. Update table models for user interface consistency

        Implementation Details:
            * Handles empty input fields with fallback to DMS conversion
            * Removes NaN columns to maintain clean data structure
            * Duplicates are automatically removed to prevent visual confusion
            * Immediate visual feedback through plot and table updates
        """

        def drop_all_na(df: pd.DataFrame) -> pd.DataFrame:
            """Remove columns that contain only NaN values for clean data management.

            Filters DataFrame to remove columns where all values are NaN, preventing
            empty columns from interfering with data operations and visualization.
            This ensures consistent data structure and prevents pandas warnings.

            Args:
                df: Input DataFrame that may contain all-NaN columns

            Returns:
                Filtered DataFrame with only columns containing valid data
            """
            return df.loc[:, df.notna().any()]

        # Retrieve coordinate data from UI input fields
        data = self.ui.lat_dec.text(), self.ui.lon_dec.text()

        # Handle empty decimal fields by falling back to degrees/minutes/seconds conversion
        if all(value == "" for value in data):
            data = self.deg_to_dec('lat'), -1 * self.deg_to_dec('lon')

        # Convert string inputs to float values for mathematical operations
        data = [float(i) for i in data]

        # Perform coordinate system conversion and generate display label
        utm_pts, label = self.convert_lat_lon_pts_to_utm(data)

        # Create new DataFrame row with complete point information
        new_row = pd.DataFrame({
            'Label': [label],  # Human-readable coordinate label
            'Easting': [utm_pts[0]],  # UTM easting coordinate
            'Northing': [utm_pts[1]],  # UTM northing coordinate
            'Geometry': [Point(utm_pts)]  # Shapely Point geometry for spatial operations
        })

        # Integrate new point into existing data structure
        # Concatenate with existing points, remove duplicates, and maintain index integrity
        self.df_custom_viz_pts = pd.concat([drop_all_na(self.df_custom_viz_pts), drop_all_na(new_row)],
                                           ignore_index=True).drop_duplicates(keep="first")

        # Update visualization displays to reflect new point addition
        self.update_plot_values()  # Refresh scatter plot display
        self.update_model_table()  # Refresh table model display

    def update_plot_values(self) -> None:
        """Refresh scatter plot visualization with current custom point coordinates.

        This function updates the matplotlib scatter plot display with the current
        set of user-defined custom points. The update process extracts coordinate
        arrays from the DataFrame and applies them to the scatter plot object for
        immediate visual feedback.

        The function uses efficient numpy array operations to prepare coordinate
        data in the format required by matplotlib's scatter plot offset system.
        This approach provides optimal performance for real-time updates during
        user interaction.

        Implementation Process:
            1. Extract coordinate arrays from custom points DataFrame
            2. Combine coordinates into numpy array format for matplotlib
            3. Update scatter plot object with new coordinate data
            4. Trigger map redraw to display changes immediately

        Performance Considerations:
            * Uses numpy column_stack for efficient array operations
            * Direct scatter plot offset updates avoid plot recreation overhead
            * Immediate map update provides responsive user feedback
        """
        # Extract coordinate arrays from custom points DataFrame
        x = self.df_custom_viz_pts['Easting'].values  # UTM easting coordinates
        y = self.df_custom_viz_pts['Northing'].values  # UTM northing coordinates

        # Combine coordinates into format required by matplotlib scatter plots
        points = np.column_stack((x, y))

        # Update scatter plot object with new coordinate data
        self.scatter_custom_pts.set_offsets(points)

        # Trigger immediate map update to display changes
        self.update_2d_map()

    def update_model_table(self) -> None:
        """Synchronize table model display with current custom point data.

        This function maintains synchronization between the underlying DataFrame
        containing custom point data and the PyQt5 table model that displays this
        information in the user interface. The update process completely refreshes
        the table display to ensure accuracy and consistency.

        The function follows a complete refresh strategy to avoid synchronization
        issues that can occur with incremental updates. This approach ensures that
        the table display exactly matches the underlying data at all times.

        Table Configuration Process:
            1. Clear existing table rows to prevent data accumulation
            2. Iterate through DataFrame rows creating table items
            3. Apply proper data types and formatting for display
            4. Configure table appearance and interaction settings
            5. Display updated table with current data

        Implementation Details:
            * Complete model refresh prevents synchronization issues
            * Data type preservation ensures proper sorting and display
            * Table configuration provides professional appearance
            * Headers hidden to focus on coordinate data
        """
        # Clear existing table rows to prevent data accumulation
        self.added_viz_pts_model.removeRows(0, self.added_viz_pts_model.rowCount())

        # Process each custom point for table display
        for _, data in self.df_custom_viz_pts.iterrows():
            # Extract coordinate values for table display
            row = [data['Easting'], data['Northing']]

            # Create table items with string representation for display
            items = [QStandardItem(str(item)) for item in row]

            # Preserve original data types for proper sorting and manipulation
            for k in range(2):
                items[k].setData(row[k])

            # Add row to table model
            self.added_viz_pts_model.appendRow(items)

        # Configure table appearance for professional display
        self.ui.insert_pts_lst.verticalHeader().setVisible(False)  # Hide row numbers
        self.ui.insert_pts_lst.horizontalHeader().setVisible(False)  # Hide column headers
        self.ui.insert_pts_lst.setShowGrid(True)  # Show grid for clarity
        self.ui.insert_pts_lst.show()  # Ensure table visibility

    def update_model_table_when_user_modifies_values(self) -> None:
        """Synchronize custom points DataFrame when user directly edits table values.

        This function maintains bi-directional synchronization between the table
        display and the underlying DataFrame when users edit coordinate values
        directly in the table interface. The process includes data validation,
        filtering, and comprehensive updates to all visualization components.

        The synchronization process handles the complexity of maintaining consistency
        across multiple data representations (DataFrame, table model, scatter plot)
        while providing immediate visual feedback for user edits.

        Synchronization Process:
            1. Extract all current data from table model
            2. Filter out empty or invalid entries
            3. Convert string values to appropriate numeric types
            4. Filter DataFrame to match table contents
            5. Update visualization displays to reflect changes
            6. Refresh table display to maintain consistency

        Data Validation:
            * Removes rows with None or empty string values
            * Converts all coordinate values to float type
            * Filters DataFrame using coordinate matching for accuracy

        Implementation Notes:
            * Comprehensive validation prevents data corruption
            * Coordinate-based filtering ensures exact DataFrame matching
            * Multiple display updates maintain complete synchronization
        """
        # Extract complete table data using model interface
        table_data = [[self.added_viz_pts_model.data(self.added_viz_pts_model.index(row, column))
                       for column in range(self.added_viz_pts_model.columnCount())]
                      for row in range(self.added_viz_pts_model.rowCount())]

        # Filter out empty or invalid entries to maintain data quality
        table_data = [i for i in table_data if i and None not in i and '' not in i]

        # Convert string representations to numeric values for mathematical operations
        table_data = [[float(i[0]), float(i[1])] for i in table_data]

        # Extract coordinate arrays for DataFrame filtering
        x_data, y_data = [i[0] for i in table_data], [i[1] for i in table_data]

        # Filter DataFrame to match current table contents exactly
        # This approach ensures that only points present in the table remain in the DataFrame
        self.df_custom_viz_pts = self.df_custom_viz_pts[
            (self.df_custom_viz_pts['Easting'].isin(x_data)) &
            (self.df_custom_viz_pts['Northing'].isin(y_data))]

        # Update all visualization components to reflect changes
        self.update_plot_values()  # Refresh scatter plot display
        self.update_model_table()  # Refresh table model display

    def get_checked_surveys(self) -> List[str]:
        """Retrieve survey identifiers for all currently checked survey type checkboxes.

        This function scans the dynamic checkbox layout to identify which survey
        types are currently selected for display. The function supports flexible
        survey management by working with dynamically created checkboxes rather
        than hard-coded survey lists.

        The function uses Qt's property system to associate survey identifiers
        with checkbox widgets, enabling robust identification even when checkbox
        text labels are modified for user-friendly display.

        Survey Selection Process:
            1. Iterate through all widgets in the survey layout
            2. Identify checkbox widgets using type checking
            3. Check checkbox state using Qt state enumeration
            4. Retrieve survey identifier from widget properties
            5. Compile list of active survey identifiers

        Returns:
            List of survey identifier strings for checked surveys. These identifiers
            correspond to keys in the survey data dictionary and can be used for
            data access and visualization control. Empty list if no surveys selected.

        Implementation Notes:
            * Uses isinstance() for robust widget type identification
            * Relies on widget properties for survey identification
            * Filters out checkboxes without valid survey properties
            * Supports dynamic checkbox creation and management
        """
        checked_surveys = []

        # Iterate through all widgets in the survey checkbox layout
        for i in range(self.ui.surveys_draw_layout.count()):
            widget = self.ui.surveys_draw_layout.itemAt(i).widget()

            # Identify checkbox widgets and check their state
            if isinstance(widget, QCheckBox) and widget.isChecked():
                # Retrieve survey identifier from widget properties
                survey_name = widget.property('survey_name')
                if survey_name:
                    checked_surveys.append(survey_name)

        return checked_surveys

    def click_on_2d_targeter(self, event: Any) -> None:
        """Handle sophisticated mouse click targeting for detailed survey data inspection.

        This function implements a comprehensive point targeting and data inspection
        system that responds to modified mouse clicks (Shift+Click) to provide
        detailed information about survey points and measurements. The system
        includes proximity-based point finding, data table updates, and coordinate
        display across multiple systems.

        The targeting system uses intelligent point finding that searches for the
        closest survey point within a reasonable distance threshold. If no survey
        points are found nearby, it falls back to general coordinate display and
        data lookup functionality.

        The function integrates multiple coordinate systems (UTM and lat/lon) and
        measurement systems (feet and meters) to provide comprehensive spatial
        reference information useful for engineering analysis and field operations.

        User Interaction Process:
            1. Detect Shift+Left-click combination for targeting activation
            2. Calculate dynamic search radius based on current zoom level
            3. Search for closest survey points within search radius
            4. Display targeting reticule at selected or found point location
            5. Update data tables with detailed point information
            6. Display coordinate information in multiple reference systems
            7. Show boundary distance measurements for regulatory analysis

        Args:
            event: Mouse click event containing position data, button information,
                  and modifier key states. Must include inaxes verification and
                  coordinate data (xdata, ydata) for valid processing.

        Implementation Features:
            * Dynamic search radius adapts to current zoom level for usability
            * Fallback point finding ensures functionality at all scales
            * Multi-system coordinate display supports various analysis needs
            * Comprehensive data table updates provide detailed inspection capability
        """

        def draw_reticule(x: float, y: float) -> None:
            """Display visual targeting reticule at specified coordinates.

            Creates a visual indicator showing the exact location being targeted
            for data inspection. The reticule provides clear visual feedback
            about which point is being analyzed.

            Args:
                x: X-coordinate (easting) for reticule placement
                y: Y-coordinate (northing) for reticule placement
            """
            pts = [float(x), float(y)]
            self.ret_pts.set_offsets(pts)
            self.update_2d_map()

        def manifest_footage_data() -> None:
            """Display comprehensive coordinate and measurement information in UI fields.

            Updates multiple UI display fields with coordinate information in
            various systems and measurement units. Includes boundary distance
            measurements critical for regulatory compliance analysis.

            The function handles coordinate system conversion and unit conversion
            to provide information in the most useful formats for different
            analysis purposes.
            """
            # Display boundary distance measurements (regulatory compliance)
            self.ui.result_FEWL_box.setText(f"FNL: {round(pt_df['FNL'].iloc[0], 2)}")
            self.ui.result_FEWL_val_box.setText(f"FSL: {round(pt_df['FSL'].iloc[0], 2)}")
            self.ui.result_FNSL_box.setText(f"FEL: {round(pt_df['FEL'].iloc[0], 2)}")
            self.ui.result_FNSL_val_box.setText(f"FWL: {round(pt_df['FWL'].iloc[0], 2)}")

            # Display UTM coordinates (engineering reference)
            self.ui.display_easting_box.setText(f"{round(x_selected, 0)}")
            self.ui.display_northing_box.setText(f"{round(y_selected, 0)}")

            # Convert and display geographic coordinates (general reference)
            lat_lon = utm.to_latlon(x_selected, y_selected, 12, 'T')
            self.ui.display_lat_box.setText(f"{round(lat_lon[0], 4)}")
            self.ui.display_lon_box.setText(f"{round(lat_lon[1], 4)}")

        # Check for Shift+Left-click combination to activate targeting
        mods = QGuiApplication.queryKeyboardModifiers()
        if event.inaxes is not None:
            if event.button == Qt.LeftButton and mods == Qt.ShiftModifier:
                # Extract click coordinates in data coordinate system
                x_selected, y_selected = event.xdata, event.ydata

                # Calculate dynamic search radius based on current zoom level
                # Larger radius when zoomed out, smaller when zoomed in for usability
                limit = (np.diff(self.ax_visual.get_xlim())[0] + np.diff(self.ax_visual.get_ylim())[0]) / 100

                # Search for closest survey points within calculated radius
                pt_df = self.check_for_closest_points_on_lines(x_selected, y_selected, limit, self.df_survey)

                # Handle case where no survey points found within search radius
                if pt_df.empty:
                    # Fallback: use general point finding from first available survey
                    vals = [i for i, v in self.df_survey.items()]
                    pt_df = self.df_survey[vals[0]].find_single_point((x_selected, y_selected))
                    # Display reticule at clicked location
                    draw_reticule(x_selected, y_selected)
                    # Clear data table and prepare for updates
                    self.clear_clicked_data_table()
                    self.ui.dx_viz_data_table.setUpdatesEnabled(True)
                else:
                    # Display reticule at found survey point location
                    draw_reticule(pt_df['easting'].iloc[0], pt_df['northing'].iloc[0])
                    # Update data table with detailed point information
                    self.update_clicked_data_table(pt_df)

                # Display coordinate and measurement information
                manifest_footage_data()

    def clear_clicked_data_table(self) -> None:
        """Clear data table displaying detailed information about clicked survey points.

        This function resets the data inspection table to prepare for new point
        data display. The clearing process removes all existing rows and temporarily
        disables updates to prevent visual flicker during data loading.

        The function maintains table model integrity while providing clean slate
        for new data display, ensuring that users see only relevant information
        for the currently selected point.

        Implementation Details:
            * Complete row removal prevents data accumulation from previous selections
            * Update disabling prevents visual artifacts during data loading
            * Model reassignment ensures proper table configuration
        """
        # Remove all existing rows to prevent data accumulation
        self.added_viz_points_data_model.setRowCount(0)
        # Reassign model to ensure proper configuration
        self.ui.dx_viz_data_table.setModel(self.added_viz_points_data_model)
        # Temporarily disable updates to prevent visual flicker
        self.ui.dx_viz_data_table.setUpdatesEnabled(False)

    def update_clicked_data_table(self, pt_df: pd.DataFrame) -> None:
        """Display comprehensive survey point information in formatted data table.

        This function creates a detailed tabular display of all available information
        for a selected survey point, including coordinate data, measurements, and
        calculated values. The display includes intelligent number formatting to
        maintain readability while preserving precision.

        The function handles various data types and applies appropriate formatting
        to ensure that numerical data is displayed in a readable format without
        losing precision critical for engineering analysis.

        Data Processing Features:
            * Intelligent number formatting based on magnitude and precision
            * Scientific notation for very large or very small numbers
            * Consistent decimal place handling for similar measurement types
            * Automatic column header generation from DataFrame structure

        Args:
            pt_df: DataFrame containing complete point information including
                  coordinates, measurements, survey data, and calculated values.
                  Must contain valid numerical data in standard survey format.

        Table Configuration:
            * Automatic row and column sizing for optimal data display
            * Hidden row headers to focus attention on data content
            * Grid display for clear data organization
            * Professional formatting for engineering review purposes
        """
        # Clear existing table content to prepare for new data
        self.clear_clicked_data_table()

        # Extract data array for table population
        data = pt_df.values.tolist()
        self.added_viz_points_data_model.setRowCount(len(data))

        # Process each data row with intelligent formatting
        for row_idx, row in enumerate(data):
            for col_idx, value in enumerate(row):
                try:
                    # Apply intelligent number formatting for readability
                    num_places_decimal = abs(decimal.Decimal(str(value)).as_tuple().exponent)
                    num_places_whole = len(str(int(value)))

                    # Format numbers with excessive precision for readability
                    if num_places_whole + num_places_decimal > 10:
                        if num_places_whole > 2:
                            value = round(value, 4)  # Standard precision for large numbers
                        else:
                            value = f'{value:.8g}'  # Scientific notation for precision
                except (TypeError, decimal.InvalidOperation):
                    # Handle non-numeric data without modification
                    pass

                # Create table item with formatted value
                item = QStandardItem(str(value))
                self.added_viz_points_data_model.setItem(row_idx, col_idx, item)

        # Configure table headers from DataFrame column structure
        columns = pt_df.columns.values
        self.added_viz_points_data_model.setHorizontalHeaderLabels(columns)

        # Apply professional table formatting for engineering review
        self.ui.dx_viz_data_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_viz_data_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.dx_viz_data_table.verticalHeader().setVisible(False)  # Hide row numbers
        self.ui.dx_viz_data_table.setShowGrid(True)  # Show grid for clarity
        self.ui.dx_viz_data_table.setUpdatesEnabled(True)  # Re-enable updates
        self.ui.dx_viz_data_table.show()  # Ensure table visibility

    def check_for_closest_points_on_lines(self, x: float, y: float, limit: float,
                                          surveys: Dict[str, Any]) -> pd.DataFrame:
        """Perform sophisticated proximity search for survey points within specified distance.

        This function implements an intelligent point finding system that searches
        through multiple survey datasets to locate the closest survey point within
        a specified distance threshold. The search process respects user survey
        selections and applies distance calculations using appropriate coordinate
        systems.

        The function uses efficient distance calculations and filtering to quickly
        identify relevant points while maintaining accuracy suitable for engineering
        applications. The search prioritizes currently selected surveys to focus
        results on data of immediate interest to the user.

        Search Algorithm Process:
            1. Identify currently selected survey datasets from checkbox states
            2. Iterate through selected surveys extracting clearance data
            3. Calculate Euclidean distances from target point to all survey points
            4. Filter points within specified distance threshold
            5. Combine results from all selected surveys into unified dataset
            6. Sort by distance to prioritize closest points
            7. Return single closest point or empty DataFrame if none found

        Args:
            x: Target X-coordinate (easting) in UTM coordinate system for search center
            y: Target Y-coordinate (northing) in UTM coordinate system for search center
            limit: Maximum search distance in coordinate system units (meters for UTM).
                  Points beyond this distance are excluded from results.
            surveys: Dictionary containing all available survey datasets where keys
                    are survey identifiers and values are survey objects containing
                    clearance_data DataFrames with coordinate information.

        Returns:
            DataFrame containing the single closest survey point within the search
            limit, including all associated survey data and measurements. Returns
            empty DataFrame if no points found within the specified distance limit.

        Performance Considerations:
            * Uses vectorized numpy operations for efficient distance calculations
            * Processes only currently selected surveys to minimize computation
            * Applies distance filtering before sorting for optimal performance
            * Returns single result to minimize data transfer and display complexity
        """
        out_empty = pd.DataFrame()

        def processDataframeForDistance() -> pd.DataFrame:
            """Calculate distances and filter survey points within search limit.

            Performs vectorized distance calculation using standard Euclidean
            distance formula and filters results to include only points within
            the specified search radius. This approach provides optimal performance
            for real-time interactive searching.

            Returns:
                DataFrame containing survey points within search limit with
                added distance column for sorting and analysis purposes.
            """
            # Extract clearance data containing survey point coordinates
            df = data.clearance_data

            # Calculate Euclidean distances using vectorized operations
            df['distance'] = np.sqrt((df['easting'].astype(float) - x) ** 2 +
                                     (df['northing'].astype(float) - y) ** 2)

            # Filter points within search limit
            closest_points_df = df[df['distance'] < limit]
            return closest_points_df

        # Identify currently selected surveys from user interface
        surveys_in_use = self.get_checked_surveys()

        # Process selected surveys if any are chosen
        if surveys_in_use:
            # Search each selected survey for points within limit
            for i in surveys_in_use:
                data = surveys[i]
                out = processDataframeForDistance()
                # Combine results from all selected surveys
                out_empty = pd.concat([out_empty, out], ignore_index=True)

            # Sort by distance and return closest point only
            out_empty = out_empty.sort_values('distance').reset_index(drop=True)
            return out_empty.head(1)  # Return single closest point

        # Return empty DataFrame if no surveys selected
        return out_empty