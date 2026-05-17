"""
UI visualization helpers for EToolsV3.

This module provides wrappers for matplotlib and plotly integration with PyQt5.
"""

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl
import plotly.graph_objects as go
import tempfile
from pathlib import Path


class MatplotlibCanvas(FigureCanvas):
    """Canvas for embedding matplotlib figures in PyQt5."""

    def __init__(self, figure: Figure, parent=None):
        """
        Initialize canvas.

        Args:
            figure: Matplotlib Figure object.
            parent: Parent QWidget.
        """
        super().__init__(figure)
        self.setParent(parent)


class PlotlyWidget(QWebEngineView):
    """Widget for displaying plotly figures in PyQt5."""

    def __init__(self, parent=None):
        """
        Initialize plotly widget.

        Args:
            parent: Parent QWidget.
        """
        super().__init__(parent)
        self.temp_file = None

    def set_figure(self, fig: go.Figure):
        """
        Display a plotly figure.

        Args:
            fig: Plotly Figure object.
        """
        # Create temporary HTML file
        if self.temp_file:
            try:
                self.temp_file.unlink()
            except:
                pass

        self.temp_file = Path(tempfile.mktemp(suffix='.html'))

        # Write figure to HTML
        fig.write_html(str(self.temp_file))

        # Load in web view
        self.load(QUrl.fromLocalFile(str(self.temp_file)))

    def cleanup(self):
        """Clean up temporary file."""
        if self.temp_file and self.temp_file.exists():
            try:
                self.temp_file.unlink()
            except:
                pass
