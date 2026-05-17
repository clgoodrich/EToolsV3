# EToolsV3 Ground-Up Rebuild - Implementation Plan

## Executive Summary

**Goal**: Rebuild EToolsV3 from scratch with clean, maintainable architecture while preserving all functionality and the existing PyQt5 UI (EToolsLimited.py).

**Approach**: Simple & Pragmatic architecture with clear separation of concerns, comprehensive error handling, and integration tests.

**Timeline Estimate**: 2-3 weeks for core rebuild + 1 week for testing/refinement

---

## Current State Analysis

### What Works Well (Keep/Preserve)
- ✅ **PyQt5 UI Definition** (EToolsLimited.py, WCR.py) - Auto-generated, comprehensive
- ✅ **PDF Import Algorithm** (main_project_import_surveys.py) - Complex but functional
- ✅ **Core Algorithms**: Minimum curvature, magnetic field calculations, clearance math
- ✅ **Visualization Logic**: 2D/3D plotting with matplotlib/plotly

### Critical Problems (Must Fix)
- ❌ **No separation of concerns** - Business logic mixed with UI code
- ❌ **SQL injection vulnerabilities** - String interpolation in queries
- ❌ **Massive code duplication** - 4,000+ lines duplicated across files
- ❌ **No error handling** - Application crashes expose users to stack traces
- ❌ **Import spaghetti** - Circular dependencies, duplicate imports
- ❌ **No validation** - Invalid data crashes the app
- ❌ **Hard-coded paths** - Database locations, file paths embedded everywhere
- ❌ **No tests** - Can't verify changes don't break functionality

---

## New Architecture Design

### Design Principles
1. **Separation of Concerns**: UI → Services → Data Access → Database
2. **Single Responsibility**: Each class/module does ONE thing well
3. **Dependency Injection**: Pass dependencies explicitly, no global state
4. **Fail Fast**: Validate inputs early, handle errors gracefully
5. **Testability**: Design for testing from day one

### Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│                  UI Layer (PyQt5)                   │
│            mainProject.py + EToolsLimited.py        │
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
│  - SurveyProcessor (min curvature, KOP detection)   │
│  - ClearanceCalculator (point-to-boundary distances) │
│  - CoordinateConverter (lat/lon, UTM, grid)         │
│  - PlatLocator (spatial joins, section assignment)   │
│  - PDFParser (survey extraction)                     │
│  - WCRGenerator (Excel report building)              │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│              Data Access Layer                       │
│  - WellRepository                                    │
│  - SurveyRepository                                  │
│  - PlatRepository                                    │
│  - CasingRepository                                  │
│  - DatabaseManager (connection handling)             │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│                  Data Layer                          │
│  SQL Server (wells, surveys, construction)           │
│  SQLite (plats, casing specs, reference data)        │
└──────────────────────────────────────────────────────┘
```

---

## Module Structure

### New Directory Layout

```
etoolsv3/
├── README.md
├── requirements.txt
├── config.example.txt
├── .gitignore
│
├── main.py                          # Application entry point
├── mainProject.py                   # UI controller (cleaned up)
├── EToolsLimited.py                 # PyQt5 UI (unchanged)
├── WCR.py                           # WCR UI (unchanged)
│
├── config/
│   ├── __init__.py
│   ├── settings.py                  # Centralized configuration
│   └── logging_config.py            # Logging setup
│
├── services/                        # Application services
│   ├── __init__.py
│   ├── well_service.py
│   ├── survey_service.py
│   ├── clearance_service.py
│   ├── wcr_service.py
│   └── visualization_service.py
│
├── core/                            # Business logic
│   ├── __init__.py
│   ├── survey/
│   │   ├── __init__.py
│   │   ├── processor.py             # Survey trajectory calculations
│   │   ├── kop_detector.py          # Kick-off point detection
│   │   └── validator.py             # Survey data validation
│   ├── clearance/
│   │   ├── __init__.py
│   │   ├── calculator.py            # Distance calculations
│   │   └── boundary_segmenter.py    # Plat boundary segmentation
│   ├── coordinates/
│   │   ├── __init__.py
│   │   ├── converter.py             # Coordinate transformations
│   │   └── magnetic_field.py        # Declination calculations
│   ├── plat/
│   │   ├── __init__.py
│   │   └── locator.py               # Spatial joins, section assignment
│   ├── pdf/
│   │   ├── __init__.py
│   │   └── parser.py                # PDF survey extraction
│   └── wcr/
│       ├── __init__.py
│       └── generator.py             # Excel report generation
│
├── data/                            # Data access layer
│   ├── __init__.py
│   ├── database.py                  # Database manager
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── well_repository.py
│   │   ├── survey_repository.py
│   │   ├── plat_repository.py
│   │   └── casing_repository.py
│   └── models/
│       ├── __init__.py
│       ├── well.py                  # Data models/DTOs
│       ├── survey.py
│       ├── plat.py
│       └── clearance.py
│
├── ui/                              # UI-specific helpers
│   ├── __init__.py
│   ├── table_models.py              # QAbstractTableModel implementations
│   ├── visualizations.py           # Matplotlib/Plotly wrappers
│   └── validators.py               # UI input validation
│
├── utils/                           # Shared utilities
│   ├── __init__.py
│   ├── errors.py                    # Custom exceptions
│   ├── logging.py                   # Logging helpers
│   └── validators.py                # Data validation utilities
│
└── tests/                           # Integration tests
    ├── __init__.py
    ├── conftest.py                  # Pytest fixtures
    ├── test_survey_service.py
    ├── test_clearance_service.py
    ├── test_wcr_service.py
    ├── fixtures/
    │   └── sample_data.py           # Test data
    └── integration/
        ├── test_database.py
        └── test_end_to_end.py
```

---

## Implementation Phases

### Phase 1: Foundation (Days 1-3)
**Goal**: Set up clean foundation with configuration, logging, database layer

**Tasks**:
1. Create new directory structure
2. Implement `config/settings.py` with environment-based configuration
3. Implement `config/logging_config.py` with structured logging
4. Implement `utils/errors.py` with custom exception hierarchy
5. Implement `data/database.py` with connection pooling and error handling
6. Implement base repository pattern in `data/repositories/`
7. Write integration tests for database connectivity

**Deliverables**:
- Clean configuration system (no hard-coded values)
- Centralized logging (file + console output)
- Database connection manager with pooling
- Repository base classes
- Tests verifying database connectivity

**Critical Files**:
- `config/settings.py`
- `data/database.py`
- `data/repositories/base_repository.py`
- `tests/integration/test_database.py`

---

### Phase 2: Data Access Layer (Days 4-6)
**Goal**: Implement all database queries as safe, tested repositories

**Tasks**:
1. Implement `data/models/` - Data Transfer Objects (DTOs)
2. Implement `data/repositories/well_repository.py`
   - `get_well_by_api()`, `get_well_location()`, `get_casing_data()`
3. Implement `data/repositories/survey_repository.py`
   - `get_survey_data()`, `get_survey_header()`, `save_survey()`
4. Implement `data/repositories/plat_repository.py`
   - `get_plats_in_bounds()`, `get_plat_by_section()`, `get_adjacent_plats()`
5. Implement `data/repositories/casing_repository.py`
   - `get_casing_strengths()`, `get_casing_by_well()`
6. **Replace ALL string interpolation with parameterized queries**
7. Write integration tests for each repository

**Deliverables**:
- Complete data access layer (no SQL in business logic)
- All queries parameterized (SQL injection protection)
- DTOs for type safety
- Integration tests covering all queries

**Critical Files**:
- `data/models/well.py`
- `data/models/survey.py`
- `data/repositories/well_repository.py`
- `data/repositories/survey_repository.py`
- `data/repositories/plat_repository.py`
- `tests/test_well_repository.py`

---

### Phase 3: Core Business Logic (Days 7-10)
**Goal**: Implement all calculation/processing logic with clean interfaces

**Tasks**:
1. Implement `core/coordinates/converter.py`
   - Lat/Lon ↔ UTM conversion
   - Grid convergence calculation
   - Coordinate validation
2. Implement `core/coordinates/magnetic_field.py`
   - Magnetic declination using PyGeoMag
   - Dip and total field calculations
3. Implement `core/survey/processor.py`
   - Minimum curvature algorithm
   - TVD/Northing/Easting calculations
   - North reference transformations
4. Implement `core/survey/kop_detector.py`
   - Multi-method KOP detection (preserve existing algorithms)
   - Consensus-based result
5. Implement `core/plat/locator.py`
   - Spatial join (points to plats)
   - Section/township/range parsing
6. Implement `core/clearance/boundary_segmenter.py`
   - Polygon segmentation into N/S/E/W sides
7. Implement `core/clearance/calculator.py`
   - Vectorized point-to-line distance calculations
   - FNL/FSL/FEL/FWL calculations
8. Implement `core/pdf/parser.py`
   - **Preserve existing PDF parsing logic** (works well)
   - Wrap in clean interface with error handling
9. Write unit tests for all algorithms

**Deliverables**:
- Clean business logic with no database dependencies
- All algorithms tested independently
- Clear input/output contracts (type hints)
- Docstrings explaining algorithms

**Critical Files**:
- `core/survey/processor.py`
- `core/clearance/calculator.py`
- `core/coordinates/converter.py`
- `core/pdf/parser.py`
- `tests/test_survey_processor.py`

---

### Phase 4: Application Services (Days 11-13)
**Goal**: Orchestration layer connecting UI to business logic

**Tasks**:
1. Implement `services/well_service.py`
   - `load_well(api, lateral)` - Loads well data from database
   - `validate_well_exists(api)` - Checks well exists before processing
2. Implement `services/survey_service.py`
   - `process_survey(api, lateral, north_ref)` - End-to-end survey processing
   - `import_from_pdf(pdf_path)` - PDF extraction + processing
   - `calculate_kop(survey_data)` - KOP detection
   - Returns processed survey with all coordinates calculated
3. Implement `services/clearance_service.py`
   - `calculate_clearances(survey_data, plat_data)` - Full clearance workflow
   - Returns clearance results (FNL/FSL/FEL/FWL at each point)
4. Implement `services/wcr_service.py`
   - `generate_wcr(well, survey, clearances)` - Excel generation
   - `get_wcr_data(api, lateral)` - Fetch all WCR-related data
5. Implement `services/visualization_service.py`
   - `create_2d_plot(survey, plats, clearances)` - 2D matplotlib figure
   - `create_3d_plot(survey, plats)` - 3D plotly figure
6. Add comprehensive error handling in all services
7. Add logging at service boundaries
8. Write integration tests for each service

**Deliverables**:
- Service layer orchestrating all business logic
- Comprehensive error handling with user-friendly messages
- Structured logging throughout
- Integration tests verifying end-to-end flows

**Critical Files**:
- `services/survey_service.py`
- `services/clearance_service.py`
- `services/wcr_service.py`
- `tests/test_survey_service.py`

---

### Phase 5: UI Integration (Days 14-17)
**Goal**: Rebuild mainProject.py to use new architecture

**Tasks**:
1. Implement `ui/table_models.py`
   - QAbstractTableModel for survey data display
   - QAbstractTableModel for clearance/footage display
2. Implement `ui/visualizations.py`
   - Matplotlib canvas wrapper
   - Plotly integration helper
3. Implement `ui/validators.py`
   - Input validation for text fields
   - Coordinate format validation
4. Rebuild `mainProject.py` (NEW file, start from scratch)
   - Initialize services via dependency injection
   - Connect UI signals to service method calls
   - Handle service errors gracefully (show MessageBox, don't crash)
   - Update UI with results from services
   - **Keep ALL signal/slot connections from original**
5. Create `main.py` entry point
   - Set up logging
   - Load configuration
   - Initialize services
   - Launch QApplication
6. Test each UI workflow end-to-end

**Deliverables**:
- Clean UI controller using services
- No business logic in UI layer
- Graceful error handling (no crashes)
- All original UI functionality preserved

**Critical Files**:
- `mainProject.py` (completely rebuilt)
- `main.py`
- `ui/table_models.py`
- `ui/visualizations.py`

---

### Phase 6: Testing & Refinement (Days 18-21)
**Goal**: Comprehensive testing and bug fixes

**Tasks**:
1. Write integration tests for full workflows:
   - Survey import → Processing → Clearance → Visualization
   - WCR generation end-to-end
   - PDF import → Survey processing
2. Manual testing of all UI features:
   - DX Survey tab
   - Well Visualization tab
   - WCR tab
   - Check Point functionality
3. Performance testing:
   - Profile clearance calculations (optimize if needed)
   - Test with large surveys (1000+ points)
4. Error scenario testing:
   - Invalid API numbers
   - Missing survey data
   - Database connection failures
   - Invalid PDF formats
5. Bug fixing and refinement
6. Documentation updates

**Deliverables**:
- Full integration test suite
- Bug-free application
- Performance benchmarks
- Updated README with new architecture

---

## Key Design Decisions

### 1. Error Handling Strategy

**Exception Hierarchy**:
```python
class EToolsError(Exception):
    """Base exception for all application errors"""
    pass

class DatabaseError(EToolsError):
    """Database connection or query errors"""
    pass

class ValidationError(EToolsError):
    """Input validation errors"""
    pass

class CalculationError(EToolsError):
    """Errors in calculations/algorithms"""
    pass

class PDFParseError(EToolsError):
    """Errors parsing PDF files"""
    pass
```

**UI Error Display**:
- All service methods return `Result[T, Error]` type
- UI checks result and shows QMessageBox on error
- Detailed errors logged to file
- User-friendly messages shown in UI

**Example**:
```python
# In service
def process_survey(api: str, lateral: str) -> Result[SurveyData, EToolsError]:
    try:
        # ... processing ...
        return Ok(survey_data)
    except Exception as e:
        logger.error(f"Survey processing failed: {e}", exc_info=True)
        return Err(CalculationError("Unable to process survey data. Check logs for details."))

# In UI
result = survey_service.process_survey(api, lateral)
if result.is_err():
    QMessageBox.critical(self, "Error", str(result.error))
    return
survey_data = result.unwrap()
```

---

### 2. Configuration Management

**settings.py**:
```python
@dataclass
class DatabaseConfig:
    host: str = os.getenv('DB_HOST', 'oilgas-sql-prod.ogm.utah.gov')
    database: str = os.getenv('DB_NAME', 'UTRBDMSNET')
    user: str = os.getenv('DB_USER', '')
    password: str = os.getenv('DB_PASSWORD', '')
    local_fallback: bool = True
    local_server: str = r'CGDESKTOP\SQLEXPRESS'

@dataclass
class PathConfig:
    data_dir: Path = Path(__file__).parent.parent / 'data'
    plat_db: Path = data_dir / 'Board_DB_Plss_Sections.db'
    casing_db: Path = data_dir / 'CasingStrength.db'
    location_db: Path = data_dir / 'location_data.db'

@dataclass
class AppConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    log_level: str = os.getenv('LOG_LEVEL', 'INFO')

settings = AppConfig()
```

**Usage**:
```python
from config.settings import settings

db_manager = DatabaseManager(settings.database)
plat_repo = PlatRepository(settings.paths.plat_db)
```

---

### 3. Repository Pattern

**Base Repository**:
```python
class BaseRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def _execute_query(self, query: str, params: dict) -> pd.DataFrame:
        """Execute parameterized query, return DataFrame"""
        try:
            return self.db.query_to_dataframe(query, params)
        except Exception as e:
            logger.error(f"Query failed: {query[:100]}...", exc_info=True)
            raise DatabaseError(f"Database query failed: {str(e)}")
```

**Example Repository**:
```python
class SurveyRepository(BaseRepository):
    def get_survey_data(self, api: str, lateral: str) -> pd.DataFrame:
        query = """
            SELECT MeasuredDepth, Inclination, Azimuth, CitingType
            FROM DirectionalSurveyHeader dsh
            JOIN DirectionalSurveyData dsd ON dsd.DirectionalSurveyHeaderKey = dsh.Pkey
            WHERE dsh.APINumber = :api AND dsh.LateralName = :lateral
            ORDER BY MeasuredDepth
        """
        return self._execute_query(query, {'api': api, 'lateral': lateral})
```

---

### 4. Service Layer Pattern

**Example Service**:
```python
class SurveyService:
    def __init__(
        self,
        survey_repo: SurveyRepository,
        well_repo: WellRepository,
        processor: SurveyProcessor,
        kop_detector: KOPDetector,
        coordinate_converter: CoordinateConverter
    ):
        self.survey_repo = survey_repo
        self.well_repo = well_repo
        self.processor = processor
        self.kop_detector = kop_detector
        self.converter = coordinate_converter

    def process_survey(self, api: str, lateral: str, north_ref: str) -> Result[SurveyData, EToolsError]:
        """
        Complete survey processing workflow:
        1. Fetch raw survey data from database
        2. Get well location for surface coordinates
        3. Calculate trajectory using minimum curvature
        4. Convert coordinates (lat/lon, UTM, grid)
        5. Detect KOP
        6. Return processed survey with all fields populated
        """
        try:
            # Validate inputs
            if not api or len(api) != 10:
                return Err(ValidationError("Invalid API number format"))

            # Fetch data
            logger.info(f"Processing survey for API={api}, Lateral={lateral}")
            raw_survey = self.survey_repo.get_survey_data(api, lateral)

            if raw_survey.empty:
                return Err(ValidationError(f"No survey data found for {api}/{lateral}"))

            well_location = self.well_repo.get_well_location(api)

            # Process trajectory
            survey = self.processor.calculate_trajectory(
                raw_survey,
                well_location.surface_lat,
                well_location.surface_lon,
                well_location.elevation,
                north_ref
            )

            # Detect KOP
            kop_result = self.kop_detector.detect(survey)
            survey.kop_md = kop_result.measured_depth
            survey.kop_confidence = kop_result.confidence

            logger.info(f"Survey processing complete. KOP={survey.kop_md:.1f}ft")
            return Ok(survey)

        except ValidationError as e:
            return Err(e)
        except DatabaseError as e:
            return Err(e)
        except Exception as e:
            logger.error(f"Unexpected error in survey processing: {e}", exc_info=True)
            return Err(CalculationError(f"Survey processing failed: {str(e)}"))
```

---

## What Gets Preserved vs. Rebuilt

### ✅ Preserve (Copy/Adapt)

1. **UI Definitions** (No changes)
   - `EToolsLimited.py`
   - `WCR.py`

2. **PDF Parser** (Wrap in clean interface)
   - `core/pdf/parser.py` ← adapted from `main_project_import_surveys.py`
   - Complex but works well
   - Add error handling and type hints

3. **Core Algorithms** (Extract and clean)
   - Minimum curvature → `core/survey/processor.py`
   - KOP detection → `core/survey/kop_detector.py`
   - Clearance calculations → `core/clearance/calculator.py`
   - Magnetic field → `core/coordinates/magnetic_field.py`

4. **Visualization Logic** (Extract to service)
   - 2D plotting → `ui/visualizations.py`
   - 3D plotting → `ui/visualizations.py`
   - Preserve matplotlib/plotly code

### 🔨 Rebuild from Scratch

1. **Main Application Controller**
   - `mainProject.py` - Complete rewrite with clean architecture

2. **Database Layer**
   - `data/database.py` - New connection manager
   - All repositories - New implementations with parameterized queries

3. **Service Layer**
   - All service classes - New orchestration logic

4. **Configuration**
   - `config/settings.py` - Centralized configuration

5. **Error Handling**
   - `utils/errors.py` - Custom exception hierarchy
   - Error handling throughout application

6. **Logging**
   - `config/logging_config.py` - Structured logging

### 🗑️ Delete Entirely

1. **Duplicate Files** (Already removed)
   - `DXClearance.py`
   - `DXSurveys2.py`
   - `main_project_relative_calc.py`

2. **Old Implementation Files** (Replace with new structure)
   - `main_project_*.py` (logic extracted to new modules)
   - `ModuleAgnostic.py` (utilities moved to appropriate modules)
   - `SQLQueries.py` (replaced by repositories)

---

## Testing Strategy

### Integration Tests

**Test Database**:
- Use production database (read-only queries)
- Or: Create test SQLite database with sample data

**Test Structure**:
```python
# tests/conftest.py
@pytest.fixture
def db_manager():
    return DatabaseManager(settings.database)

@pytest.fixture
def survey_repository(db_manager):
    return SurveyRepository(db_manager)

# tests/test_survey_repository.py
def test_get_survey_data_valid_api(survey_repository):
    """Test retrieving survey data for known well"""
    result = survey_repository.get_survey_data('4301354722', 'Reay_16-29-30-B4-2H')

    assert not result.empty
    assert 'measured_depth' in result.columns
    assert 'inclination' in result.columns
    assert 'azimuth' in result.columns
    assert len(result) > 0

def test_get_survey_data_invalid_api(survey_repository):
    """Test handling of invalid API number"""
    result = survey_repository.get_survey_data('0000000000', 'NonExistent')

    assert result.empty

# tests/test_survey_service.py
def test_process_survey_end_to_end(survey_service):
    """Test complete survey processing workflow"""
    result = survey_service.process_survey('4301354722', 'Reay_16-29-30-B4-2H', 'True')

    assert result.is_ok()
    survey = result.unwrap()
    assert survey.kop_md > 0
    assert len(survey.data) > 0
    assert 'tvd' in survey.data.columns
    assert 'northing' in survey.data.columns
    assert 'easting' in survey.data.columns
```

**Coverage Goals**:
- Repositories: 90%+ coverage (all queries tested)
- Services: 80%+ coverage (main workflows tested)
- Core business logic: 95%+ coverage (algorithms fully tested)

---

## Migration Strategy

### Phase-by-Phase Migration

**No "big bang" deployment** - Migrate functionality incrementally:

1. **Phase 1-2**: Build foundation, can develop alongside old code
2. **Phase 3**: Core logic ready, can be tested independently
3. **Phase 4**: Services ready, can be tested with mock UI
4. **Phase 5**: New UI controller ready
5. **Phase 6**: Switch `main.py` to use new architecture

### Rollback Plan

- Keep old code in `legacy/` directory until new version stable
- Can switch back by changing `main.py` import

### Data Migration

- No database schema changes needed
- All queries remain compatible

---

## Success Criteria

### Functionality
- ✅ All UI features work identically to original
- ✅ Survey processing produces same results as original
- ✅ Clearance calculations match original output
- ✅ WCR generation creates valid Excel files
- ✅ Visualizations display correctly

### Code Quality
- ✅ No SQL injection vulnerabilities
- ✅ No duplicate code (DRY principle)
- ✅ Clear separation of concerns (layered architecture)
- ✅ Comprehensive error handling (no crashes on invalid input)
- ✅ Structured logging throughout

### Testing
- ✅ 80%+ code coverage for business logic
- ✅ Integration tests for all repositories
- ✅ Integration tests for all services
- ✅ Manual testing of all UI workflows passed

### Documentation
- ✅ README updated with new architecture
- ✅ API documentation for all services
- ✅ Architecture diagram
- ✅ Setup/installation guide

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| PDF parsing breaks on edge cases | High | Extensive testing with various PDF formats, preserve original logic |
| Algorithm results don't match original | High | Unit tests comparing outputs, validate against known wells |
| Database queries return different results | High | Integration tests, side-by-side comparison with old code |
| UI integration issues | Medium | Incremental testing, keep UI definitions unchanged |
| Performance degradation | Medium | Profile code, optimize hot paths, benchmark against original |
| Missing dependencies in new structure | Low | Careful dependency analysis, comprehensive testing |

---

## Open Questions

1. **Database Access During Development**: Do we have read-only access to production database for testing?
2. **Test Data**: Do we have sample survey data we can use for automated tests?
3. **Deployment**: How is the application currently deployed to users?
4. **Python Version**: Confirm Python 3.12 is target (original code uses 3.12)
5. **External Dependencies**: Are all current dependencies acceptable (welleng, PyGeoMag, etc.)?

---

## Next Steps After Approval

1. Create new branch: `git checkout -b rebuild-clean-architecture`
2. Set up directory structure
3. Begin Phase 1 implementation
4. Daily progress updates with working code
5. Incremental commits for each completed module

---

## Appendix: Key Technologies

### Keep
- **PyQt5 5.15.11**: UI framework
- **pandas 2.2.2**: Data manipulation
- **NumPy 1.26.4**: Numerical computing
- **Shapely 2.0.5**: Geometric operations
- **geopandas 1.0.1**: Geospatial data
- **pyproj 3.6.1**: Coordinate transformations
- **welleng**: Well engineering calculations
- **matplotlib 3.9.2**: 2D plotting
- **plotly 5.23.0**: 3D visualization
- **pdfminer.six**: PDF parsing
- **SQLAlchemy 2.0.31**: Database ORM

### Add
- **pytest**: Testing framework
- **python-dotenv**: Environment variable management
- **returns**: Result/Maybe types for error handling

### Remove
- None (all current dependencies needed)
