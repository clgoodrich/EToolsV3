import sys
import os


def get_project_root():
    """
    Gets the absolute path to the project's root folder.
    This is the most reliable way to find data files.
    """
    # __file__ is the path to this file (file_helper.py), which is in 'src'
    # The first dirname gets the 'src' folder.
    # The second dirname gets the parent of 'src', which is the project root.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_data_file_path(*path_segments):
    """
    Builds a full path to any data file from the project root.
    Example: get_data_file_path('data', 'databases', 'Board_DB.db')
    """
    project_root = get_project_root()
    return os.path.join(project_root, *path_segments)


# --- Your Specific Helper Functions ---

def get_board_db_path():
    """Get path to Board_DB.db"""
    return get_data_file_path('data', 'databases', 'Board_DB.db')


def get_dx_sample_path():
    """Get path to DX_sample.db"""
    return get_data_file_path('data', 'databases', 'DX_sample.db')


def get_plss_sections_path():
    """Get path to Board_DB_Plss_Sections.db"""
    return get_data_file_path('data', 'databases', 'Board_DB_Plss_Sections.db')


def get_template_tracking_excel_path():
    """Get path to template tracking Excel file"""
    return get_data_file_path('data', 'excel_files', 'TrackingWCR.xlsx')


def get_template_excel_path():
    """Get path to template CSV file"""
    # Your screenshot shows this is a .csv file, not .xlsx
    return get_data_file_path('data', 'excel_files', 'template_excel_load.csv')
