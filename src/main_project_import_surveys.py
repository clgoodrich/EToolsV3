"""
Oil and Gas Directional Survey Import and PDF Processing Module

This module provides comprehensive functionality for importing directional drilling survey data
from PDF documents and tabular formats (CSV, Excel). Specialized for oil and gas industry
survey reports containing measured depth, inclination, and azimuth data.

Core Features:
    - PDF text extraction using PDFMiner with spatial coordinate analysis
    - Survey data parsing with pattern recognition and blacklist filtering
    - Automatic detection of measured depth, inclination, and azimuth values
    - Surface hole location (latitude/longitude) extraction from PDF documents
    - North reference identification (true, magnetic, grid)
    - Ground elevation extraction and database integration
    - Statistical outlier detection and removal
    - Support for CSV/Excel import with header parsing

Industry Context:
    - Processes standard directional survey reports from drilling contractors
    - Handles various PDF formats and layouts commonly used in oil and gas
    - Integrates with regulatory databases for elevation and location validation
    - Supports both planned and as-drilled survey data types

Author: Oil & Gas Engineering Team
Version: 3.2
Python: 3.12+
Dependencies: PDFMiner, PyQt5, pandas, numpy, sklearn, shapely, regex

Typical Usage:
    # Initialize survey importer
    importer = SurveyImporter()

    # Process PDF survey document
    survey_df, north_ref = importer.load_and_process_data(
        'as_drilled', db_connection, api_number, file_paths
    )

    # Process Excel/CSV survey data
    survey_df, north_ref = importer.process_table_data(
        'survey.xlsx', 'planned', 'xl'
    )
"""

import csv
import os
import statistics as st
import sys
from itertools import chain
from typing import Dict, List, Optional, Tuple, Union, Any

import numpy as np
import pandas as pd
import regex as re
import sqlite3
import utm
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTAnno, LTChar, LTPage, LTTextBox, LTTextLine
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from PyQt5.QtCore import QAbstractTableModel, Qt
from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QProgressDialog,
    QTableView, QVBoxLayout, QWidget
)
from scipy.spatial import Delaunay
from shapely.geometry import Point, Polygon
from sklearn.cluster import OPTICS

# import ModuleAgnostic as ma


class PandasModel(QAbstractTableModel):
    """Qt table model for displaying pandas DataFrames in PyQt5 applications.

    Provides read-only tabular display of DataFrame data with proper header
    handling and type conversion for GUI presentation.
    """

    def __init__(self, data: pd.DataFrame) -> None:
        """Initialize model with DataFrame data."""
        super().__init__()
        self._data = data

    def rowCount(self, parent=None) -> int:
        """Return number of rows in the DataFrame."""
        return len(self._data)

    def columnCount(self, parent=None) -> int:
        """Return number of columns in the DataFrame."""
        return len(self._data.columns)

    def data(self, index, role=Qt.DisplayRole):
        """Return data for display in table cells."""
        if role == Qt.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]
            return str(value)
        return None

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        """Return header data for table display."""
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._data.columns[section])
            if orientation == Qt.Vertical:
                return str(self._data.index[section])
        return None


class DataFrameViewer(QMainWindow):
    """Interactive PyQt5 viewer for DataFrame data with sorting and column manipulation.

    Provides professional data inspection interface for survey data validation
    and quality control during import processing.
    """

    def __init__(self, df: pd.DataFrame, title: str = "DataFrame Viewer") -> None:
        """Initialize viewer window with DataFrame content and table configuration."""
        super().__init__()
        self.setWindowTitle(title)
        self.resize(800, 600)

        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Configure table view with DataFrame model
        table_view = QTableView()
        model = PandasModel(df)
        table_view.setModel(model)

        # Configure table properties for professional data display
        table_view.horizontalHeader().setStretchLastSection(True)
        table_view.horizontalHeader().setSectionsMovable(True)
        table_view.verticalHeader().setSectionsMovable(True)
        table_view.setSortingEnabled(True)

        layout.addWidget(table_view)


class PDFPageDetailedAggregator(PDFPageAggregator):
    """Enhanced PDF page aggregator for extracting text with spatial coordinates.

    Extends PDFPageAggregator to capture text positioning data essential for
    survey data extraction from complex PDF layouts. Maintains text bounding
    boxes and page relationships for spatial analysis.
    """

    def __init__(self, rsrcmgr: PDFResourceManager, pageno: int = 1,
                 laparams: Optional[LAParams] = None) -> None:
        """Initialize aggregator with resource manager and layout parameters."""
        PDFPageAggregator.__init__(self, rsrcmgr, pageno=pageno, laparams=laparams)
        self.rows: List[Tuple[int, float, float, float, float, str]] = []
        self.page_number: int = 0

    def receive_layout(self, ltpage: LTPage) -> None:
        """Process PDF page layout to extract text with spatial coordinates.

        Recursively traverses PDF layout objects to extract text content with
        precise coordinate information. Filters empty text and sorts by page
        and Y-coordinate for logical reading order.

        Args:
            ltpage: PDF page layout object from PDFMiner
        """
        def render(item: Union[LTPage, LTTextBox, LTTextLine], page_number: int) -> None:
            """Recursively extract text and coordinates from layout items."""
            if isinstance(item, (LTPage, LTTextBox)):
                for child in item:
                    render(child, page_number)
            elif isinstance(item, LTTextLine):
                child_str = ''
                for child in item:
                    if isinstance(child, (LTChar, LTAnno)):
                        child_str += child.get_text()

                # Clean whitespace and validate content
                child_str = ' '.join(child_str.split()).strip()
                if child_str:
                    # Store page, bbox coordinates (x1, y1, x2, y2), and text
                    row = (page_number, item.bbox[0], item.bbox[1],
                           item.bbox[2], item.bbox[3], child_str)
                    self.rows.append(row)

                # Continue processing child elements
                for child in item:
                    render(child, page_number)

        render(ltpage, self.page_number)
        self.page_number += 1
        # Sort by page number, then by Y-coordinate (descending for reading order)
        self.rows = sorted(self.rows, key=lambda x: (x[0], -x[2]))
        self.result = ltpage


def _parse_and_find(parsed_data: List[List[Tuple]], search_term: str,
                   blacklist: List[str]) -> List[List[Union[int, str, float]]]:
    """Search parsed PDF data for specific terms while applying blacklist filtering.

    Processes multi-page PDF text data to locate survey-related terms with spatial
    coordinates. Applies text normalization and blacklist filtering to reduce
    false positives.

    Args:
        parsed_data: Multi-page text data with coordinates
        search_term: Target term to search for (e.g., 'measured', 'azimuth')
        blacklist: Terms to exclude from results

    Returns:
        List of matches with page number, text, and coordinate data
    """
    def _process_item(page_num: int, item: Tuple) -> Optional[List]:
        """Process individual text item for term matching."""
        x1, y1, x2, y2, txt = item
        # Normalize text for comparison
        txt = re.sub(r'[\n,]', ' ', txt.lower().strip())

        # Check for search term and apply blacklist filtering
        if (search_term in txt and
            (blacklist == [''] or not any(word.lower() in txt for word in blacklist))):
            return [page_num, txt, x1, y1, x2, y2]
        return None

    return [
        result for page_num, page in enumerate(parsed_data)
        for result in map(lambda item: _process_item(page_num, item), page)
        if result is not None
    ]


def _gather_process(parsed_data: List[List[Tuple]]) -> List[List[float]]:
    """Main processing pipeline for extracting survey data from parsed PDF content.

    Orchestrates the complete survey data extraction workflow including:
    1. Search for measured depth, inclination, and azimuth references
    2. Spatial coordinate matching between survey parameters
    3. Data grouping and statistical processing
    4. Outlier detection and removal
    5. Final survey point validation

    Args:
        parsed_data: Multi-page PDF text data with spatial coordinates

    Returns:
        List of validated survey points [MD, Inc, Azi] as floats
    """

    def _find_blacklist(line: str) -> bool:
        """Identify and filter non-survey text content using industry blacklists.

        Applies comprehensive filtering to exclude headers, legal text, and
        non-data content commonly found in drilling reports.
        """
        black_lst = {
            "start", "drop", "hold", "dls", "casing", "surface", "kick", "lp", "shl",
            "water", "pbhl", "build", "tangent", "3d", "inch", "inches", "includes",
            "sincerely", "reference", "referenced", "end", "correct", "west", "east",
            "american", "county", "plan", "tgr", "fnl", "fel", "fsl", "fwl", "tgr3"
        }
        white_lst = {"azimuth", "inclination"}

        line = line.replace("\n", " ").lower()
        words = set(re.findall(r'\b\w+\b', line))

        # Apply blacklist filtering with whitelist exceptions
        if black_lst.intersection(words) and not white_lst.intersection(words):
            return True

        # Filter lines with low numeric content ratio
        data = re.sub(r'[^0-9. ]+', '', line)
        if 0 < len(data) / len(line) < 0.15:
            return True
        return False

    def _find_md_data() -> List[List]:
        """Extract measured depth references from PDF data."""
        measured_depth_lst1 = _parse_and_find(parsed_data, 'measured', [''])
        md_lst_found = _parse_and_find(parsed_data, 'md', [''])
        md_all_lst = measured_depth_lst1 + md_lst_found

        # Apply blacklist filtering and remove duplicates
        md_edited = [md_all_lst[i] for i in range(len(md_all_lst))
                    if not _find_blacklist(md_all_lst[i][1])]
        md_edited = [list(t) for t in set(tuple(element) for element in md_edited)]
        return sorted(md_edited)

    def _find_inc_data() -> List[List]:
        """Extract inclination references from PDF data."""
        inclination_lst = _parse_and_find(parsed_data, 'inclination', [''])
        inc_lst_found = _parse_and_find(parsed_data, 'inc', [''])
        inc_all_lst = inclination_lst + inc_lst_found

        # Apply filtering and deduplication
        inc_edited = [inc_all_lst[i] for i in range(len(inc_all_lst))
                     if not _find_blacklist(inc_all_lst[i][1])]
        inc_edited = [list(t) for t in set(tuple(element) for element in inc_edited)]
        return sorted(inc_edited)

    def _find_azi_data() -> List[List]:
        """Extract azimuth references from PDF data."""
        azimuth_lst = _parse_and_find(parsed_data, 'azimuth', [''])
        azi_lst_found = _parse_and_find(parsed_data, 'azi', [''])
        azi_all_lst = azi_lst_found + azimuth_lst

        # Filter and process azimuth data
        azi_edited = [azi_all_lst[i] for i in range(len(azi_all_lst))
                     if not _find_blacklist(azi_all_lst[i][1])]
        azi_edited = [list(t) for t in set(tuple(element) for element in azi_edited)]
        azi_edited = sorted(azi_edited)

        # Clean extrapolated station references
        for i in range(len(azi_edited)):
            if "extrapolated station" in azi_edited[i][1]:
                index_cut = azi_edited[i][1].index('azimuth')
                azi_edited[i][1] = azi_edited[i][1][index_cut:].strip()
        return azi_edited

    def _compare_page_coordinates() -> Tuple[List, set, List]:
        """Match survey parameters by spatial proximity on PDF pages.

        Uses coordinate analysis to identify survey data tables by finding
        measured depth, inclination, and azimuth values with aligned spatial
        positioning indicating tabular data structure.
        """
        def _create_dataframe(lst: List, columns: List[str]) -> pd.DataFrame:
            """Convert coordinate list to DataFrame for spatial analysis."""
            return pd.DataFrame(lst, columns=['page', 'text'] + columns)

        # Create DataFrames for coordinate analysis
        md_df = _create_dataframe(md_lst, ['x1', 'y1', 'x2', 'y2'])
        inc_df = _create_dataframe(inc_lst, ['x1', 'y1', 'x2', 'y2'])
        azi_df = _create_dataframe(azi_lst, ['x1', 'y1', 'x2', 'y2'])

        # Merge inclination and azimuth by page for spatial analysis
        inc_azi_df = pd.merge(inc_df, azi_df, on='page', suffixes=('_inc', '_azi'))

        # Filter based on Y-coordinate alignment (same table row)
        inc_azi_df = inc_azi_df[
            (inc_azi_df['y2_inc'] / inc_azi_df['y2_azi']).between(0.95, 1.05)
        ]

        # Merge with measured depth data
        result_df = pd.merge(md_df, inc_azi_df, on='page')

        # Apply spatial alignment conditions for tabular data identification
        result_df = result_df[
            (result_df['y2_inc'] / result_df['y2']).between(0.95, 1.05) &
            (result_df['x2_azi'] < 330) &
            (result_df['x2_azi'] >= result_df['x1_azi']) &
            (result_df['x2_azi'] >= result_df['x1_inc']) &
            (result_df['x2_inc'] >= result_df['x1_inc']) &
            (result_df['x2_inc'] >= result_df['x2']) &
            (result_df['x2'] >= result_df['x1']) &
            (
                ((result_df['x1'] < result_df['x2']) &
                 (result_df['x2'] <= result_df['x1_inc']) &
                 (result_df['x1_inc'] < result_df['x2_inc'])) |
                ((result_df['x1'] <= result_df['x1_inc']) &
                 (result_df['x2'] <= result_df['x2_inc']))
            )
        ]

        # Prepare coordinate groupings for table extraction
        md_inc_azi_found = result_df.apply(lambda row: [
            [row['page']],
            [row['x1'], row['x2'], row['y1'], row['y2']],
            [row['x1_inc'], row['x2_inc'], row['y1_inc'], row['y2_inc']],
            [row['x1_azi'], row['x2_azi'], row['y1_azi'], row['y2_azi']]
        ], axis=1).tolist()

        page_lst_found = sorted(result_df['page'].unique())
        inc_azi_lst_found = inc_azi_df[[
            'page', 'text_inc', 'x1_inc', 'y1_inc', 'x2_inc', 'y2_inc',
            'text_azi', 'x1_azi', 'y1_azi', 'x2_azi', 'y2_azi'
        ]].values.tolist()

        return md_inc_azi_found, set(page_lst_found), inc_azi_lst_found

    def _grouper_process() -> List[List[float]]:
        """Extract and validate numerical survey data from identified table regions.

        Processes identified survey table areas to extract numerical values,
        applies statistical validation, and groups data points into survey stations.
        """
        def _grouper(iterable: List[float], val: float):
            """Group similar values within tolerance for column identification."""
            prev = None
            group = []
            for item in iterable:
                if not prev or item - prev <= val:
                    group.append(item)
                else:
                    yield group
                    group = [item]
                prev = item
            if group:
                yield group

        def _find_corresponding_data(grouper_func: List[List[float]],
                                   data_list: List, checker: str) -> List[List]:
            """Map text data to spatial groupings for table reconstruction."""
            df = pd.DataFrame(data_list, columns=['x1', 'y1', 'x2', 'y2', 'text'])
            df['avg_x'] = (df['x1'] + df['x2']) / 2
            df['avg_y'] = (df['y1'] + df['y2']) / 2

            flat_grouper = [item for sublist in grouper_func for item in sublist]

            # Group by spatial coordinate (X or Y average)
            group_col = 'avg_x' if checker == 'x_avg' else 'avg_y'

            def _find_closest(val: float) -> float:
                """Find closest grouper value for spatial assignment."""
                return min(flat_grouper, key=lambda x: abs(x - val))

            df['group'] = df[group_col].apply(_find_closest)
            grouped = df.groupby('group').apply(
                lambda x: x.sort_values('y1', ascending=False)
            )

            return [group[['x1', 'y1', 'x2', 'y2', 'text']].values.tolist()
                   for _, group in grouped.groupby(level=0)]

        def _stats_processor(data_x: List, data_y: List,
                           md_limit: List) -> Tuple[List, List, float]:
            """Apply statistical validation and extract numerical values.

            Processes grouped data to extract clean numerical values and
            applies boundary conditions based on spatial analysis.
            """
            def _data_gather(lst: str) -> List[str]:
                """Extract and validate numerical data from text strings."""
                lst = str(lst)
                data = lst.replace("\n", " ").replace("†", "").lower().strip().replace(",", "")
                data = re.sub(r'[^0-9. ]+', '', data).strip()
                data_lst = data.split(" ")
                data_lst = [i for i in data_lst if i]

                # Validate extracted numerical content
                if (len(data_lst) > 1 or data_lst == [] or data_lst == ['.'] or
                    (len(data_lst) == 1 and len(data_lst[0]) * 2 < len(lst))):
                    return []
                return data_lst

            # Calculate Y-coordinate boundary from survey header locations
            y_avg_limit = [st.mean([md_limit[i][2], md_limit[i][3]])
                          for i in range(1, len(md_limit))]
            y_avg_all = st.mean(y_avg_limit)

            # Process Y-grouped data (typical table rows)
            for i in range(len(data_y)):
                data_y[i] = [j for j in data_y[i]
                           if (_data_gather(j[-1]) != [] and
                               st.mean([j[1], j[3]]) < y_avg_all)]
                for j in range(len(data_y[i])):
                    data_y[i][j][-1] = _data_gather(data_y[i][j][-1])[0]

            # Process X-grouped data (typical table columns)
            for i in range(len(data_x)):
                data_x[i] = [j for j in data_x[i]
                           if (_data_gather(j[-1]) != [] and
                               st.mean([j[1], j[3]]) < y_avg_all)]
                data_x[i] = sorted(data_x[i], key=lambda x: x[3])
                for j in range(len(data_x[i])):
                    data_x[i][j][-1] = _data_gather(data_x[i][j][-1])[0]

            # Filter unrealistic inclination values and small datasets
            data_y = [group for group in data_y
                     if len(group) > 1 and float(group[1][-1]) < 100]
            data_x = [group for group in data_x
                     if len(group) > 1 and float(group[1][-1]) < 100]

            return data_x, data_y, y_avg_all

        # Process each page containing survey data
        parsed_data_used = [parsed_data[i] for i in range(len(parsed_data))
                           if i in page_lst]
        all_x_data, all_y_data = [], []
        mode_row_returner = []

        for i in range(len(parsed_data_used)):
            # Create spatial groupings for X and Y coordinates
            group_lst = [st.mean([parsed_data_used[i][j][0], parsed_data_used[i][j][2]])
                        for j in range(len(parsed_data_used[i]))]
            group_lst_y = [st.mean([parsed_data_used[i][j][1], parsed_data_used[i][j][3]])
                          for j in range(len(parsed_data_used[i]))]

            # Generate coordinate groupings with tolerance
            grouper_func = [j for i, j in dict(enumerate(_grouper(sorted(group_lst), 3), 1)).items()]
            grouper_func_y = [j for i, j in dict(enumerate(_grouper(sorted(group_lst_y), 2), 1)).items()]

            # Map data to spatial groups
            grouper_full_data = _find_corresponding_data(grouper_func, parsed_data_used[i], 'x_avg')
            grouper_full_data_y = _find_corresponding_data(grouper_func_y, parsed_data_used[i], 'y_avg')
            grouper_full_data_y = sorted(grouper_full_data_y, key=lambda x: x[0][1], reverse=True)

            # Apply statistical processing and boundary conditions
            grouper_full_data, grouper_full_data_y, boundary_line = _stats_processor(
                grouper_full_data, grouper_full_data_y, md_inc_azi[i]
            )

            grouper_full_data_y = sorted(grouper_full_data_y, key=lambda x: x[1], reverse=True)
            all_x_data.append(grouper_full_data)

            # Filter data with minimum row count and track row length distribution
            grouper_full_data_y = [r for r in grouper_full_data_y if len(r) >= 3]
            all_lengths = [len(r) for r in grouper_full_data_y if len(r) > 0]
            mode_row_returner = mode_row_returner + all_lengths
            all_y_data.append(grouper_full_data_y)

        # Determine most common row structure and filter accordingly
        mode_row = st.mode(mode_row_returner)
        all_y_data = list(chain.from_iterable(all_y_data))
        all_y_data = [i for i in all_y_data if mode_row + 1 >= len(i) >= mode_row - 1]
        all_y_data = [i[:3] for i in all_y_data]  # Take first 3 columns (MD, Inc, Azi)
        all_y_data = [i for i in all_y_data if len(i) == 3]

        # Convert to numerical format
        all_y_data = [[float(i[0][-1]), float(i[1][-1]), float(i[2][-1])]
                     for i in all_y_data]
        return all_y_data

    def _error_finder(data_1: List[float]) -> List[List]:
        """Identify statistical outliers using Z-score analysis.

        Applies 3-sigma outlier detection to remove erroneous survey readings
        that could affect trajectory calculations.
        """
        outliers = []
        threshold = 3
        mean_1 = np.mean(data_1)
        std_1 = np.std(data_1)

        for counter_errors, y in enumerate(data_1):
            z_score = (y - mean_1) / std_1
            if np.abs(z_score) > threshold:
                outliers.append([y, counter_errors])
        return outliers

    # Execute main processing pipeline
    md_lst = _find_md_data()
    inc_lst = _find_inc_data()
    azi_lst = _find_azi_data()
    md_inc_azi, page_lst, inc_azi_lst = _compare_page_coordinates()
    page_lst = sorted(list(page_lst))
    returned_data = _grouper_process()

    # Extract individual parameter arrays for outlier analysis
    md_lst = [float(i[0]) for i in returned_data]
    inc_lst = [float(i[1]) for i in returned_data]
    azi_lst = [float(i[2]) for i in returned_data]

    # Identify and remove outliers
    md_outliers = _error_finder(md_lst)
    inc_outliers = _error_finder(inc_lst)
    azi_outliers = _error_finder(azi_lst)
    outliers_lst = md_outliers + inc_outliers + azi_outliers
    outliers_lst = list(set(i[1] for i in outliers_lst))

    # Remove outlier data points
    for i in outliers_lst:
        returned_data[i] = []
    returned_data = [i for i in returned_data if i]

    return returned_data


def _gather_elevation(parsed_data: List[List[Tuple]], shl: List[float]) -> Optional[float]:
    """Extract ground level elevation from PDF survey documents.

    Searches for elevation values near 'ground level' text references using
    spatial coordinate analysis. Provides fallback elevation data for wells
    without database elevation records.

    Args:
        parsed_data: Multi-page PDF text data with coordinates
        shl: Surface hole location [latitude, longitude]

    Returns:
        Elevation value in feet above sea level, or None if not found
    """
    n_lst = _parse_and_find(parsed_data, 'ground level', [''])

    for i in range(len(parsed_data)):
        for j in range(len(parsed_data[i])):
            text = parsed_data[i][j][4].lower().strip().replace("\n", " ").replace(",", "")
            x1, y1, x2, y2 = parsed_data[i][j][0], parsed_data[i][j][1], parsed_data[i][j][2], parsed_data[i][j][3]

            for k in range(len(n_lst)):
                if i == n_lst[k][0]:  # Same page
                    x3, y3, x4, y4 = n_lst[k][2], n_lst[k][3], n_lst[k][4], n_lst[k][5]
                    # Check spatial proximity to ground level reference
                    if x4 < x1 and abs(y1 - y3) < 2 and abs(y2 - y4) < 4:
                        try:
                            return float(text)
                        except ValueError:
                            pass
    return None


def _find_bounding_y_coordinates(parsed_data: List[List[Tuple]]) -> List[int]:
    """Identify pages containing well position and coordinate information.

    Searches for key phrases indicating location data sections to focus
    coordinate extraction efforts on relevant PDF pages.

    Args:
        parsed_data: Multi-page PDF text data

    Returns:
        List of page numbers containing location information
    """
    well_page = []

    for i in range(len(parsed_data)):
        for j in range(len(parsed_data[i])):
            text = parsed_data[i][j][4].lower().strip().replace("\n", " ").replace(",", "")

            # Search for standard well location terminology
            location_indicators = [
                'well position', 'uncertainty', 'geographic coordinates',
                'surface location', 'lat / long:'
            ]

            if any(indicator in text for indicator in location_indicators):
                well_page.append(i)

    return well_page


def _lat_lon_reg_ex_dec(range_data: List[str], line: str) -> Optional[str]:
    """Extract decimal latitude/longitude coordinates using regex pattern matching.

    Searches for decimal coordinate formats within specified numeric ranges
    appropriate for Utah oil and gas operations.

    Args:
        range_data: List of valid coordinate prefixes (e.g., ['40', '41'])
        line: Text line to search for coordinates

    Returns:
        Matched decimal coordinate string, or None if not found
    """
    for k in range_data:
        regExDecimal = re.compile(re.escape(k) + r"\.\d{4,6}")
        searchDec = regExDecimal.search(line)
        if searchDec is not None:
            return searchDec.group()
    return None


def _convert_degree_to_decimal(value: str) -> float:
    """Convert degree-minute-second coordinate format to decimal degrees.

    Processes coordinates in DMS format (e.g., "40°12'30.5\"") to decimal
    degrees with 6-digit precision for survey accuracy requirements.

    Args:
        value: Coordinate string in degree-minute-second format

    Returns:
        Decimal degree coordinate value

    Raises:
        ValueError: If coordinate format is invalid
    """
    test = re.sub("[^0-9.]+", " ", value)
    parts = test.split()

    if len(parts) < 3:
        raise ValueError(f"Invalid coordinate format: {value}")

    degree_value = float(parts[0])
    minute_value = float(parts[1])
    second_value = float(parts[2])

    final_value = round(degree_value + minute_value / 60 + second_value / 3600, 6)
    return final_value


def _lat_lon_reg_ex_deg(range_data: List[str], line: str, coord_type: str) -> Optional[float]:
    """Extract degree-minute-second coordinates using type-specific regex patterns.

    Applies coordinate-specific regex patterns to handle different formats
    and validation ranges for latitude vs longitude extraction.

    Args:
        range_data: Valid coordinate range prefixes
        line: Text line to search
        coord_type: 'lat' for latitude, 'lon' for longitude

    Returns:
        Decimal coordinate value, or None if not found
    """
    for k in range_data:
        if coord_type == 'lat':
            # Latitude pattern: handles 30-49° range typical for US oil fields
            regExDegree = re.compile(
                r"(90[ :°d]*00[ :\'\'m]*00(\.0+)?|[3-4][0-9][ :°d]*[0-5][0-9][ :\'\'m]*[0-5][0-9](\.\d+))[ :\?\"s]*(N|n|S|s)?"
            )
        elif coord_type == 'lon':
            # Longitude pattern: handles western US longitude ranges
            regExDegree = re.compile(
                r"-?((1[0-7][0-9]|0[0-9][0-9]|0[0-9])[ :°d]*([0-5][0-9]|[0-9])[ :\'\'m]*[0-5][0-9](\.\d+))[ :\?\"s]*(E|e|W|w)?"
            )

        searchLatDeg = regExDegree.search(line)
        if searchLatDeg is not None:
            try:
                value = _convert_degree_to_decimal(searchLatDeg.group())
                return value
            except ValueError:
                return None
    return None


def _find_proximal_values(parse_left: float, parse_down: float, parse_right: float,
                         parse_up: float, text: str, val_left: float, val_down: float,
                         val_right: float, val_up: float, range_data: List[str],
                         coord_type: str) -> Optional[Union[str, float]]:
    """Extract coordinate values based on spatial proximity to reference text.

    Uses spatial coordinate analysis to identify numerical values that are
    positioned near latitude/longitude reference text on PDF pages.

    Args:
        parse_left/down/right/up: Bounding box of potential coordinate text
        text: Text content to search for coordinates
        val_left/down/right/up: Bounding box of reference text
        range_data: Valid coordinate ranges for validation
        coord_type: 'lat' or 'lon' for coordinate-specific processing

    Returns:
        Extracted coordinate value (decimal or string), or None
    """
    val_x_avg = st.mean([val_right, val_left])
    val_y_avg = st.mean([val_down, val_up])
    parse_x_avg = st.mean([parse_right, parse_left])
    parse_y_avg = st.mean([parse_down, parse_up])

    # Check spatial proximity conditions
    proximity_condition = (
        (val_x_avg < parse_x_avg and abs(val_y_avg - parse_y_avg) < 5) or
        (abs(val_x_avg - parse_x_avg) < 5 and val_y_avg > parse_y_avg)
    )

    if proximity_condition:
        # Try decimal format first
        output_dec = _lat_lon_reg_ex_dec(range_data, text)
        if output_dec is not None:
            return output_dec

        # Fallback to degree-minute-second format
        output_deg = _lat_lon_reg_ex_deg(range_data, text, coord_type)
        if output_deg is not None:
            return output_deg

    return None


def _process_shl(parsed_data: List[List[Tuple]]) -> List[Union[float, str]]:
    """Extract surface hole location coordinates from PDF survey documents.

    Processes PDF content to identify and extract latitude/longitude coordinates
    for the surface hole location. Handles multiple coordinate formats and
    applies Utah-specific coordinate ranges for validation.

    Args:
        parsed_data: Multi-page PDF text data with spatial coordinates

    Returns:
        List containing [latitude, longitude] as float/string values
    """
    lat_lst_o = _parse_and_find(parsed_data, 'latitude', [''])
    lon_lst_o = _parse_and_find(parsed_data, 'longitude', [''])

    # Utah-specific coordinate ranges for validation
    latRange = ['35', '36', '37', '38', '39', '40', '41', '42', '43', '44']
    lonRange = ['115', '114', '113', '112', '111', '110', '109', '108']

    lat_lon_value = [0, 0]
    page_no = _find_bounding_y_coordinates(parsed_data)
    page_no = list(set(page_no))

    for k in page_no:
        # Filter coordinate references to current page
        lat_lst = [i for i in lat_lst_o if i[0] == k]
        lon_lst = [i for i in lon_lst_o if i[0] == k]

        for j in range(len(parsed_data[k])):
            parse_left, parse_down, parse_right, parse_up = (
                parsed_data[k][j][0], parsed_data[k][j][1],
                parsed_data[k][j][2], parsed_data[k][j][3]
            )
            text = parsed_data[k][j][4].lower().strip().replace("\n", " ").replace(",", "")

            # Process latitude references
            for r in range(len(lat_lst)):
                val_left, val_down, val_right, val_up = (
                    lat_lst[r][2], lat_lst[r][3], lat_lst[r][4], lat_lst[r][5]
                )
                output = _find_proximal_values(
                    parse_left, parse_down, parse_right, parse_up, text,
                    val_left, val_down, val_right, val_up, latRange, 'lat'
                )
                if output is not None:
                    lat_lon_value[0] = output

            # Process longitude references
            for r in range(len(lon_lst)):
                val_left, val_down, val_right, val_up = (
                    lon_lst[r][2], lon_lst[r][3], lon_lst[r][4], lon_lst[r][5]
                )
                output = _find_proximal_values(
                    parse_left, parse_down, parse_right, parse_up, text,
                    val_left, val_down, val_right, val_up, lonRange, 'lon'
                )
                if output is not None:
                    # Convert to negative longitude for western hemisphere
                    lat_lon_value[1] = str(abs(float(output)) * -1)

    return lat_lon_value


def _modify_north_ref_for_incomplete_data(reference_text: str, input_text: str,
                                        y3: float, y4: float, y1: float,
                                        y2: float) -> float:
    """Handle incomplete north reference data by adjusting coordinate boundaries.

    Provides coordinate adjustment for cases where north reference information
    spans multiple lines or has formatting inconsistencies in PDF documents.

    Args:
        reference_text: Reference text containing coordinate info
        input_text: Input text being processed
        y3, y4: Reference text Y-coordinates
        y1, y2: Input text Y-coordinates

    Returns:
        Adjusted Y4 coordinate value
    """
    re_text = re.search(r"\b{}\b".format('local co-ordinate reference'),
                       reference_text, re.IGNORECASE)
    re_text2 = re.search(r"\b{}\b".format('md reference'),
                        reference_text, re.IGNORECASE)

    if re_text is None and re_text2 is not None:
        if abs(y3 - y1) < 2 < abs(y4 - y2):
            if y4 < y2:
                return y2
    return y4


def _find_proximal_values_north_ref(x1: float, y1: float, x2: float, y2: float,
                                   input_text: str, x3: float, y3: float,
                                   x4: float, y4: float, reference_text: str) -> Union[str, int]:
    """Extract north reference type using spatial proximity analysis.

    Identifies magnetic, true, or grid north references by analyzing text
    positioned near 'north reference' labels in PDF documents.

    Args:
        x1, y1, x2, y2: Input text bounding coordinates
        input_text: Text content to search for north reference
        x3, y3, x4, y4: Reference text bounding coordinates
        reference_text: Reference text context

    Returns:
        North reference type ('magnetic', 'true', 'grid') or -1 if not found
    """
    y4 = _modify_north_ref_for_incomplete_data(reference_text, input_text, y3, y4, y1, y2)
    type_lst = ['magnetic', 'true', 'grid']

    # Check spatial alignment conditions
    spatial_condition_1 = (x3 < x4 < x1 < x2 and abs(y1 - y3) < 2 and abs(y2 - y4) < 4)
    spatial_condition_2 = (x3 == x1 and x4 == x2 and abs(y1 - y3) < 2 and abs(y2 - y4) < 4)

    if spatial_condition_1 or spatial_condition_2:
        for k in type_lst:
            re_text2 = re.search(r"\b{}\b".format(k), input_text, re.IGNORECASE)
            if re_text2 is not None:
                return re_text2.group()

    return -1


def _process_north_reference(parsed_data: List[List[Tuple]]) -> Optional[str]:
    """Extract north reference type from PDF survey documents.

    Identifies the azimuth reference system used in the survey (magnetic, true, or grid north)
    by searching for 'north reference' text and nearby reference type indicators.

    Args:
        parsed_data: Multi-page PDF text data with spatial coordinates

    Returns:
        North reference type string ('magnetic', 'true', 'grid'), or None if not found
    """
    n_lst = _parse_and_find(parsed_data, 'north reference', [''])

    for i in range(len(parsed_data)):
        for j in range(len(parsed_data[i])):
            text = parsed_data[i][j][4].lower().strip().replace("\n", " ").replace(",", "")
            x1, y1, x2, y2 = (parsed_data[i][j][0], parsed_data[i][j][1],
                             parsed_data[i][j][2], parsed_data[i][j][3])

            for k in range(len(n_lst)):
                if i == n_lst[k][0]:  # Same page
                    x3, y3, x4, y4 = (n_lst[k][2], n_lst[k][3], n_lst[k][4], n_lst[k][5])
                    o_text = n_lst[k][1]

                    value_ret_d = _find_proximal_values_north_ref(
                        x1, y1, x2, y2, text, x3, y3, x4, y4, o_text
                    )
                    if value_ret_d != -1:
                        return value_ret_d

    return None


def _text_box_grouper_manager(device: PDFPageDetailedAggregator,
                             counter: int) -> List[List[List]]:
    """Organize extracted PDF text data by page and apply coordinate sorting.

    Processes the aggregated PDF text extraction results to create page-organized
    data structures sorted by spatial coordinates for systematic analysis.

    Args:
        device: PDF aggregator containing extracted text with coordinates
        counter: Total number of pages processed

    Returns:
        List of pages, each containing sorted text elements with coordinates
    """
    data_lst = [[] for p in range(counter + 1)]

    # Organize text data by page number
    for (page_nb, x_min, y_min, x_max, y_max, txt) in device.rows:
        data_lst[page_nb].append([x_min, y_min, x_max, y_max, txt])

    # Sort each page's content by X then Y coordinates
    for i in range(len(data_lst)):
        if data_lst[i]:
            data_lst[i] = sorted(data_lst[i], key=lambda x: (x[0], x[1]))

    return data_lst


def _text_box_data_gather(path: str) -> Optional[List[List[List]]]:
    """Extract text and coordinate data from PDF files with progress tracking.

    Main PDF processing function that handles file opening, page iteration,
    and text extraction with spatial coordinates. Includes user cancellation
    support via progress dialog.

    Args:
        path: File path to PDF document

    Returns:
        Organized text data by page with coordinates, or None if cancelled

    Raises:
        FileNotFoundError: If PDF file cannot be opened
    """
    # Initialize PDF processing components
    try:
        fp = open(path, 'rb')
    except FileNotFoundError:
        return None

    rsrcmgr = PDFResourceManager()
    laparams = LAParams(char_margin=0.1)
    device = PDFPageDetailedAggregator(rsrcmgr, laparams=laparams)
    interpreter = PDFPageInterpreter(rsrcmgr, device)

    # Get total page count for progress tracking
    pages = list(PDFPage.get_pages(fp, caching=False))
    total_pages = len(pages)

    # Create progress dialog for user feedback
    progress = QProgressDialog("Processing PDF...", "Cancel", 0, total_pages)
    progress.setWindowTitle("Processing PDF")
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0)

    # Reset file pointer and restart page iteration
    fp.seek(0)
    pages = PDFPage.get_pages(fp, caching=False)

    counter = 0
    for page in pages:
        if progress.wasCanceled():
            fp.close()
            return None

        try:
            interpreter.process_page(page)
            device.get_result()
        except TypeError:
            # Handle PDF processing errors gracefully
            pass

        counter += 1
        progress.setValue(counter)
        QApplication.processEvents()  # Keep UI responsive

    # Organize extracted data and cleanup
    data_lst = _text_box_grouper_manager(device, counter)
    fp.close()
    return data_lst


class SurveyImporter:
    """Main survey data import and processing class for oil and gas operations.

    Handles import of directional survey data from multiple file formats including
    PDF documents and tabular data (CSV, Excel). Provides comprehensive processing
    pipeline for survey validation, coordinate extraction, and database integration.

    Key Features:
        - PDF survey document parsing with spatial text analysis
        - Table format import with header processing
        - Surface location and elevation extraction
        - North reference identification
        - Database integration for validation and enhancement
        - Support for both planned and as-drilled survey types

    Attributes:
        api (Optional[str]): API well number for database queries
        db (Optional[Any]): Database connection for elevation and validation
        file_path (Optional[str]): Current file path being processed
    """

    def __init__(self) -> None:
        """Initialize survey importer with empty state for processing configuration."""
        self.api: Optional[str] = None
        self.db: Optional[Any] = None
        self.file_path: Optional[str] = None

    def load_and_process_data(self, label: str, db: Any, api: str,
                            file_path_dict: Dict[str, str]) -> Tuple[pd.DataFrame, str, Optional[Any]]:
        """Main entry point for survey data loading and processing.

        Routes file processing based on extension and handles the complete import
        workflow including validation, coordinate extraction, and format standardization.

        Args:
            label: Survey type identifier ('planned' or 'as_drilled')
            db: Database connection for validation and enhancement
            api: API well number for identification and validation
            file_path_dict: Dictionary mapping survey types to file paths

        Returns:
            Tuple containing:
                - DataFrame with processed survey data
                - North reference type string
                - Additional platform data (if applicable)

        Raises:
            NameError: If PDF processing encounters critical errors
        """
        # Store processing parameters
        self.db = db
        self.api = api
        used_file = file_path_dict[label]

        # Determine processing method based on file extension
        _, extension = os.path.splitext(used_file)
        extension = extension.lower()

        # Initialize return values
        df, north_ref, extra_plats = pd.DataFrame(), "", None

        if extension == '.pdf':
            try:
                return self._process_pdf_data(used_file, label)
            except NameError:
                # Handle PDF processing failures gracefully
                pass
        elif extension == '.csv':
            return self.process_table_data(used_file, label, 'csv')
        elif extension in ['.xls', '.xlsx', '.xlsm', '.xlsb']:
            return self.process_table_data(used_file, label, 'xl')

        return df, north_ref, extra_plats

    def process_table_data(self, directory: str, label: str,
                          table_doc_type: str) -> Tuple[pd.DataFrame, str]:
        """Process survey data from tabular formats (CSV, Excel) with header parsing.

        Handles structured survey data files with standardized header formats containing
        metadata and tabular survey measurements. Processes header information for
        surface coordinates, elevation, and north reference data.

        Args:
            directory: File path to tabular data file
            label: Survey type ('planned' or 'as_drilled')
            table_doc_type: Format type ('csv' or 'xl')

        Returns:
            Tuple containing processed DataFrame and north reference string
        """
        header_dict = {}
        north_ref_dict = {'t': 'true', 'g': 'grid'}
        header_info, data_table = pd.DataFrame(), pd.DataFrame()

        if table_doc_type == 'xl':
            # Process Excel files with separate header and data sections
            header_info = pd.read_excel(directory, nrows=6, header=None)
            data_table = pd.read_excel(directory, skiprows=6)
            header_dict = {header_info.iloc[i, 0]: header_info.iloc[i, 1]
                          for i in range(len(header_info))}

        elif table_doc_type == 'csv':
            # Process CSV files with manual header extraction
            with open(directory, 'r') as file:
                csv_reader = csv.reader(file)
                header_rows = [next(csv_reader) for _ in range(6)]
            header_dict = {row[0]: row[1] if len(row) > 1 else None for row in header_rows}
            data_table = pd.read_csv(directory, skiprows=6)

        # Enhance survey data with header metadata
        data_table['SurfaceLatitude'] = header_dict['surface_latitude']
        data_table['SurfaceLongitude'] = abs(float(header_dict['surface_longitude'])) * -1
        data_table['SurveySurfaceElevation'] = header_dict['surface_elevation']
        data_table['CitingType'] = 'Planned' if label == 'planned' else 'AsDrilled'

        return data_table, north_ref_dict[header_dict['north_ref'].lower()]

    def _process_pdf_data(self, directory: str, label: str) -> Tuple[pd.DataFrame, str]:
        """Process PDF survey documents through complete extraction and validation pipeline.

        Orchestrates the full PDF processing workflow including text extraction,
        survey data parsing, coordinate extraction, and database validation.
        Creates standardized DataFrame output with industry-standard column names.

        Args:
            directory: File path to PDF survey document
            label: Survey type identifier for processing context

        Returns:
            Tuple containing processed survey DataFrame and north reference type
        """
        # Extract text data with spatial coordinates
        parsed_text_data = _text_box_data_gather(directory)

        # Handle user cancellation during PDF processing
        if parsed_text_data is None:
            return None

        # Execute main survey data extraction pipeline
        returned_data = _gather_process(parsed_text_data)
        shl = _process_shl(parsed_text_data)

        # Retrieve elevation data with database fallback
        elevation = self._find_elevation()
        if elevation is None:
            elevation = _gather_elevation(parsed_text_data, shl)

        # Convert extracted data to structured format
        output_data = [
            {"measured_depth": i[0], "inclination": i[1], "azimuth": i[2]}
            for i in returned_data
        ]
        df = pd.DataFrame(data=output_data, columns=["measured_depth", "inclination", "azimuth"])

        # Enhance with surface location and metadata
        df['SurfaceLatitude'] = shl[0]
        df['SurfaceLongitude'] = shl[1]
        df['SurveySurfaceElevation'] = elevation
        df['CitingType'] = 'Planned' if label == 'planned' else 'AsDrilled'

        # Extract north reference and perform final cleanup
        north_ref = _process_north_reference(parsed_text_data)
        df = df.drop_duplicates(keep="first")
        df = df.sort_values(by=['CitingType', 'measured_depth'])

        return df, north_ref

    def _find_elevation(self) -> Optional[float]:
        """Retrieve surface elevation from regulatory database using API number.

        Queries the well database to find ground level elevation for the specified
        API number. Provides primary elevation source with PDF fallback option.

        Returns:
            Ground elevation in feet above sea level, or None if not found

        Raises:
            Database connection errors are handled gracefully
        """
        try:
            query = f"""SELECT l.GRELEV
              FROM Well w
              LEFT JOIN Construct c ON c.WellKey = w.PKey
              LEFT JOIN loc l ON l.ConstructKey = c.pkey
              WHERE WellID = '{self.api}'
              AND LocType IN ('SURF')"""

            loc_df = self.db.query_to_dataframe(query)
            if not loc_df.empty:
                elevation = loc_df['GRELEV'].iloc[0]
                return elevation
        except Exception:
            # Handle database errors gracefully
            pass

        return None