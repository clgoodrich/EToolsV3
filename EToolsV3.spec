# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

# Collect data files from problematic packages
welleng_datas = collect_data_files('welleng')
vedo_datas = collect_data_files('vedo')

a = Analysis(
    ['mainProject.py'],
    pathex=[],
    binaries=[],
    datas=welleng_datas + vedo_datas,
    hiddenimports=[
        # Python standard library
        'cProfile', 'pstats', 'sqlite3', 'csv', 'json', 'urllib.parse',
        'contextlib', 'functools', 'itertools', 'collections', 'collections.abc',
        'typing', 'weakref', 'tempfile', 'logging', 'traceback', 'copy',
        'math', 'statistics', 'datetime', 'os', 'sys', 're', 'time',
        
        # Database
        'pyodbc', 'sqlalchemy', 'sqlalchemy.sql.default_comparator', 
        'sqlalchemy.pool', 'sqlalchemy.dialects.sqlite',
        
        # Data science
        'pandas', 'pandas._libs.tslibs.timedeltas', 'pandas._libs.hashtable', 
        'pandas._libs.tslib', 'pandas._libs.interval', 'pandas.core.arrays.numpy_',
        'numpy', 'numpy.core.multiarray', 'numpy.random.common', 
        'numpy.random.bounded_integers', 'numpy.random.entropy',
        
        # PyQt5
        'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
        'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngine',
        
        # Geospatial
        'shapely', 'shapely.geometry', 'shapely.geometry.point', 'shapely.geometry.linestring',
        'shapely.geometry.polygon', 'shapely.affinity', 'shapely.ops',
        'geopandas', 'pyproj', 'pyproj.crs', 'pyproj.transformer', 'utm',
        'fiona', 'Rtree',
        
        # Scientific computing
        'scipy', 'scipy.spatial', 'scipy.spatial.distance', 
        'sklearn', 'sklearn.cluster', 'sklearn.cluster.optics_',
        
        # Visualization
        'matplotlib', 'matplotlib.backends.backend_qt5agg', 'matplotlib.figure',
        'matplotlib.pyplot', 'matplotlib.patches', 'matplotlib.collections',
        'plotly', 'plotly.graph_objects', 'plotly.express',
        
        # Oil & Gas specific
        'welleng', 'wellpathpy', 'welltrajconvert',
        
        # 3D Visualization
        'vedo', 'vtk',
        
        # PDF processing
        'pdfminer', 'pdfminer.pdfinterp', 'pdfminer.converter', 'pdfminer.layout',
        'pdfminer.pdfpage', 'pdfminer.pdfdocument', 'pdfminer.pdfparser',
        'pdfplumber',
        
        # File handling
        'openpyxl', 'xlrd', 'lxml',
        
        # Utilities
        'rdp', 'geographiclib', 'geographiclib.geodesic', 'geopy', 'geopy.distance',
        'tabulate', 'regex', 'requests', 'tqdm', 'tenacity', 'joblib',
        'keyboard', 'cv2'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='EToolsV3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)