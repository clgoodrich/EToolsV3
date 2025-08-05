import sys
import os


def get_resource_path(relative_path):
    """Get the absolute path to a resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # If not running as executable, use the current directory
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def get_db_path(db_filename):
    """Get correct path to database file"""
    # Get src directory (where this .py file is)
    src_dir = os.path.dirname(__file__)
    # Get main directory (parent of src)
    main_dir = os.path.dirname(src_dir)
    # Return path to database
    return os.path.join(main_dir, 'data', 'databases', db_filename)


def get_excel_path(excel_name):
    """Get the path to an Excel file"""
    return get_resource_path(os.path.join('data', 'excel_files', excel_name))


def get_data_path(folder_name, file_name):
    """Get path to any data file"""
    return get_resource_path(os.path.join('data', folder_name, file_name))


# For your specific database paths used in the code
def get_board_db_path():
    """Get path to Board_DB.db"""
    return get_db_path('Board_DB.db')


def get_dx_sample_path():
    """Get path to DX_sample.db"""
    return get_db_path('DX_sample.db')


def get_plss_sections_path():
    """Get path to Board_DB_Plss_Sections.db"""
    return get_db_path('Board_DB_Plss_Sections.db')


def get_template_excel_path():
    """Get path to template Excel file"""
    return get_excel_path('template_excel_load.csv')