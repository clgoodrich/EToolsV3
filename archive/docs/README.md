# ETools V3 - Directional Drilling Engineering Tools

A comprehensive PyQt5 application for processing directional drilling surveys, calculating clearances, and generating Well Completion Reports (WCR) for oil and gas wells.

## Architecture

ETools V3 has been rebuilt from the ground up with clean, maintainable architecture:

```
┌─────────────────────────────────────────────────────┐
│                  UI Layer (PyQt5)                   │
│            main.py + mainProject_new.py             │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│              Application Services                    │
│  - WellService                                       │
│  - SurveyService                                     │
│  - ClearanceService                                  │
│  - WCRService                                        │
│  - VisualizationService                              │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│                Business Logic                        │
│  - SurveyProcessor (minimum curvature)              │
│  - ClearanceCalculator                               │
│  - CoordinateConverter                               │
│  - MagneticFieldCalculator                           │
│  - PlatLocator                                       │
│  - KOPDetector                                       │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│              Data Access Layer                       │
│  - WellRepository (parameterized queries)           │
│  - SurveyRepository (parameterized queries)         │
│  - PlatRepository (parameterized queries)           │
│  - CasingRepository                                  │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│                  Data Layer                          │
│  SQL Server (wells, surveys, construction)           │
│  SQLite (plats, casing specs, reference data)        │
└──────────────────────────────────────────────────────┘
```

## Features

### Core Capabilities
- **Directional Survey Processing**: Minimum curvature calculations using welleng library
- **Coordinate Transformations**: Lat/Lon ↔ UTM with grid convergence corrections
- **Magnetic Field Calculations**: Automatic declination and dip using World Magnetic Model
- **KOP Detection**: Multi-method kick-off point detection with consensus algorithm
- **Clearance Calculations**: FNL/FSL/FEL/FWL distances from PLSS section boundaries
- **Section Footage**: Automatic calculation of drilled footage by section
- **WCR Generation**: Complete Well Completion Report generation to Excel
- **2D/3D Visualization**: Matplotlib and Plotly trajectory plots

### Key Improvements
- ✅ **No SQL Injection**: All queries use parameterized statements
- ✅ **Separation of Concerns**: Clean layered architecture
- ✅ **Error Handling**: Comprehensive exception hierarchy with user-friendly messages
- ✅ **Logging**: Structured logging throughout application
- ✅ **Configuration**: Centralized environment-based configuration
- ✅ **Type Safety**: Data Transfer Objects (DTOs) with type hints
- ✅ **Testing**: Integration test framework with pytest
- ✅ **No Code Duplication**: DRY principles applied throughout

## Installation

### Prerequisites
- Python 3.12+
- SQL Server (or local SQL Server Express)
- Windows OS (for ODBC drivers)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd etoolsv3
```

2. Create virtual environment:
```bash
python -m venv .venv
.venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements_new.txt
```

4. Configure database connection:
   - Option 1: Create `.env` file:
```env
DB_HOST=your-server
DB_NAME=UTRBDMSNET
DB_USER=your-username
DB_PASSWORD=your-password
```

   - Option 2: Update `logininfo.txt`:
```
user = your-username
password = your-password
```

5. Verify plat database exists:
```
data/Board_DB_Plss_Sections.db
data/CasingStrength.db
data/location_data.db
```

## Usage

### Running the Application

```bash
python main.py
```

### Basic Workflow

1. **Load Well Data**
   - Enter API number (10 digits)
   - Enter lateral name
   - Click "Load Well"

2. **Process Survey**
   - Click "Process Survey"
   - Survey is automatically:
     - Retrieved from database
     - Processed with minimum curvature
     - Converted to multiple coordinate systems
     - KOP detected
     - Displayed in table

3. **Calculate Clearances**
   - Click "Calculate Clearances"
   - System automatically:
     - Identifies intersecting plat sections
     - Segments section boundaries
     - Calculates distances to N/S/E/W lines
     - Displays results

4. **Generate WCR**
   - Click "Generate WCR"
   - Complete Excel report created with:
     - Well information
     - Survey data
     - Clearance measurements
     - Section footage
     - Saved to `output/` directory

### Configuration

Edit `config/settings.py` or use environment variables:

```python
# Database
DB_HOST=server-name
DB_NAME=database-name
DB_USER=username
DB_PASSWORD=password

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR

# Environment
ETOOLS_ENV=development  # or production
```

## Project Structure

```
etoolsv3/
├── main.py                     # Application entry point
├── mainProject_new.py          # UI controller
├── EToolsLimited.py            # PyQt5 UI definition (unchanged)
│
├── config/
│   ├── settings.py             # Centralized configuration
│   └── logging_config.py       # Logging setup
│
├── services/                   # Application services
│   ├── well_service.py
│   ├── survey_service.py
│   ├── clearance_service.py
│   ├── wcr_service.py
│   └── visualization_service.py
│
├── core/                       # Business logic
│   ├── survey/
│   │   ├── processor.py        # Minimum curvature calculations
│   │   ├── kop_detector.py     # KOP detection algorithms
│   │   └── validator.py        # Survey validation
│   ├── clearance/
│   │   ├── calculator.py       # Distance calculations
│   │   └── boundary_segmenter.py
│   ├── coordinates/
│   │   ├── converter.py        # Coordinate transformations
│   │   └── magnetic_field.py   # Magnetic field calculations
│   ├── plat/
│   │   └── locator.py          # Spatial joins
│   ├── pdf/
│   │   └── parser.py           # PDF survey extraction
│   └── wcr/
│       └── generator.py        # Excel report generation
│
├── data/                       # Data access layer
│   ├── database.py             # Database manager
│   ├── repositories/
│   │   ├── well_repository.py
│   │   ├── survey_repository.py
│   │   ├── plat_repository.py
│   │   └── casing_repository.py
│   └── models/                 # Data Transfer Objects
│       ├── well.py
│       ├── survey.py
│       ├── plat.py
│       └── clearance.py
│
├── ui/                         # UI helpers
│   ├── table_models.py         # QAbstractTableModel implementations
│   ├── visualizations.py       # Matplotlib/Plotly wrappers
│   └── validators.py           # Input validation
│
├── utils/
│   └── errors.py               # Custom exceptions
│
└── tests/                      # Integration tests
    ├── conftest.py
    └── test_repositories.py
```

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Code Style
- PEP 8 compliant
- Type hints throughout
- Docstrings for all public methods

### Adding New Features

1. **Add Data Model** (if needed)
   ```python
   # data/models/new_feature.py
   from dataclasses import dataclass

   @dataclass
   class NewFeature:
       field1: str
       field2: float
   ```

2. **Add Repository** (if database access needed)
   ```python
   # data/repositories/new_feature_repository.py
   class NewFeatureRepository(BaseRepository):
       def get_data(self, param: str):
           query = "SELECT * FROM table WHERE col = :param"
           return self._execute_query(query, {'param': param})
   ```

3. **Add Business Logic**
   ```python
   # core/new_feature/processor.py
   class NewFeatureProcessor:
       def process(self, data):
           # Business logic here
           pass
   ```

4. **Add Service**
   ```python
   # services/new_feature_service.py
   class NewFeatureService:
       def __init__(self, repo, processor):
           self.repo = repo
           self.processor = processor

       def do_something(self, param):
           data = self.repo.get_data(param)
           return self.processor.process(data)
   ```

5. **Connect to UI**
   ```python
   # mainProject_new.py
   def on_new_feature_button(self):
       result = self.new_feature_service.do_something(param)
       self._display_results(result)
   ```

## Technical Details

### Survey Processing
- **Algorithm**: Minimum curvature method via welleng library
- **Coordinate Systems**: WGS84, UTM Zone 12N, State Plane
- **Magnetic Model**: World Magnetic Model (WMM)
- **Interpolation**: Optional interpolation to user-defined step size

### Clearance Calculations
- **Method**: Shapely geometric operations
- **Section Identification**: Point-in-polygon spatial joins
- **Boundary Segmentation**: Polygon edges classified as N/S/E/W
- **Distance Calculation**: Perpendicular distance to line segments

### Database
- **Primary**: SQL Server (production) with ODBC
- **Fallback**: Local SQL Server Express
- **Connection Pooling**: SQLAlchemy with pre-ping
- **Security**: Parameterized queries throughout
- **Reference Data**: SQLite databases for plats and casing specs

## Troubleshooting

### Database Connection Issues
- Verify ODBC drivers installed: SQL Server Native Client
- Check `logininfo.txt` has correct credentials
- Test connection: `python -m data.database`
- Check firewall settings for SQL Server port 1433

### Import Errors
- Ensure all dependencies installed: `pip install -r requirements_new.txt`
- Verify Python 3.12+ installed
- Check virtual environment activated

### PDF Parsing Issues
- Ensure pdfminer.six installed
- Check PDF is text-based (not scanned image)
- Verify survey data is in tabular format

## License

[Specify License]

## Contact

[Contact Information]

## Acknowledgments

- **welleng**: Wellbore trajectory calculations
- **PyGeoMag**: Magnetic field calculations
- **Shapely/GeoPandas**: Geospatial operations
- **PyQt5**: User interface framework
