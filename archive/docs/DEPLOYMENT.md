# ETools V3 Deployment Checklist

## Pre-Deployment Setup

### 1. Environment Setup
- [ ] Python 3.12+ installed
- [ ] Virtual environment created: `python -m venv .venv`
- [ ] Virtual environment activated: `.venv\Scripts\activate`
- [ ] Dependencies installed: `pip install -r requirements_new.txt`

### 2. Database Configuration
- [ ] SQL Server accessible
- [ ] ODBC Driver for SQL Server installed
- [ ] Database credentials obtained
- [ ] `.env` file created from `.env.example`
- [ ] Database connection tested

### 3. Required Data Files
- [ ] `data/Board_DB_Plss_Sections.db` exists
- [ ] `data/CasingStrength.db` exists
- [ ] `data/location_data.db` exists
- [ ] `WCR_Empty.xlsm` template exists in root

### 4. Directory Structure
- [ ] `output/` directory created (or will be auto-created)
- [ ] `logs/` directory created (or will be auto-created)
- [ ] `temp/` directory for temporary files

## Migration from Old Version

### 1. Backup Old System
```bash
# Create backup of old installation
cp -r etoolsv3 etoolsv3_backup_$(date +%Y%m%d)
```

### 2. Preserve Data Files
- [ ] Copy plat databases to `data/` directory
- [ ] Copy casing database to `data/` directory
- [ ] Copy WCR template
- [ ] Copy logininfo.txt (if using)

### 3. Configuration Migration
- [ ] Transfer database credentials
- [ ] Transfer any custom configuration
- [ ] Update paths in settings if needed

## Testing Checklist

### Unit Tests
```bash
pytest tests/ -v
```

### Integration Testing

#### 1. Database Connectivity
- [ ] Test SQL Server connection
- [ ] Test local fallback connection
- [ ] Verify query execution
- [ ] Check connection pooling

#### 2. Repository Tests
- [ ] WellRepository: Load well data
- [ ] SurveyRepository: Fetch survey
- [ ] PlatRepository: Query sections
- [ ] CasingRepository: Get casing specs

#### 3. Core Business Logic
- [ ] CoordinateConverter: Lat/lon ↔ UTM conversion
- [ ] MagneticFieldCalculator: Calculate declination
- [ ] SurveyProcessor: Process survey with minimum curvature
- [ ] KOPDetector: Detect kick-off point
- [ ] ClearanceCalculator: Calculate distances

#### 4. Services
- [ ] WellService: Load complete well data
- [ ] SurveyService: End-to-end survey processing
- [ ] ClearanceService: Full clearance workflow
- [ ] WCRService: Generate Excel report
- [ ] VisualizationService: Create plots

### UI Testing

#### 1. Basic Workflows
- [ ] Launch application: `python main.py`
- [ ] Load well by API and lateral
- [ ] Process survey
- [ ] Calculate clearances
- [ ] Generate WCR
- [ ] Create 2D visualization
- [ ] Create 3D visualization

#### 2. Error Handling
- [ ] Invalid API number shows friendly error
- [ ] Missing survey shows appropriate message
- [ ] Database connection failure handled gracefully
- [ ] No crashes on invalid input

#### 3. Data Validation
- [ ] API number validation works
- [ ] Survey data validation catches issues
- [ ] Clearance warnings displayed
- [ ] Results displayed correctly in tables

## Performance Testing

### 1. Survey Processing
Test with different survey sizes:
- [ ] Small survey (< 50 points): < 1 second
- [ ] Medium survey (50-500 points): < 5 seconds
- [ ] Large survey (> 500 points): < 15 seconds

### 2. Clearance Calculations
- [ ] Single section: < 1 second
- [ ] Multiple sections: < 5 seconds
- [ ] Full wellbore: < 10 seconds

### 3. Memory Usage
- [ ] No memory leaks on repeated operations
- [ ] Memory usage reasonable for typical workflow

## Production Deployment

### 1. Configuration
- [ ] Set `ETOOLS_ENV=production` in .env
- [ ] Set `ETOOLS_DEBUG=false`
- [ ] Set `LOG_LEVEL=INFO` or `WARNING`
- [ ] Configure production database credentials

### 2. Security
- [ ] logininfo.txt excluded from version control (.gitignore)
- [ ] .env file excluded from version control
- [ ] Database credentials stored securely
- [ ] No hardcoded passwords in code

### 3. Documentation
- [ ] README.md updated with deployment info
- [ ] Architecture documentation complete
- [ ] User guide created (if needed)
- [ ] Known issues documented

### 4. Backup Strategy
- [ ] Database backup procedure documented
- [ ] Data file backup procedure
- [ ] Log rotation configured
- [ ] Output file retention policy

## Post-Deployment Verification

### 1. First Run
- [ ] Application launches without errors
- [ ] Database connection succeeds
- [ ] Plat databases load correctly
- [ ] UI displays properly

### 2. Known Well Test
Use a known well to verify:
- [ ] Well loads correctly
- [ ] Survey processes correctly
- [ ] Clearances match expected values
- [ ] WCR generates successfully
- [ ] Plots display correctly

### 3. Logging
- [ ] Log files created in logs/ directory
- [ ] Log level appropriate for environment
- [ ] Errors logged with full context
- [ ] No sensitive data in logs

## Rollback Plan

If issues occur:

1. **Stop Application**
   - Close all instances
   - Note any error messages

2. **Restore Old Version**
   ```bash
   mv etoolsv3 etoolsv3_failed
   mv etoolsv3_backup_YYYYMMDD etoolsv3
   ```

3. **Verify Old Version Works**
   - Test basic functionality
   - Ensure data intact

4. **Report Issues**
   - Collect error logs
   - Document failure scenario
   - Report for fixes

## Common Issues and Solutions

### Database Connection Fails
- Check ODBC driver installed
- Verify server name and credentials
- Test network connectivity
- Check firewall settings

### Import Errors
- Verify virtual environment activated
- Reinstall dependencies
- Check Python version (3.12+)

### PDF Parsing Fails
- Ensure PDF is text-based
- Check pdfminer.six installed
- Verify PDF format compatible

### Visualization Doesn't Display
- Check matplotlib/plotly installed
- Verify PyQt5 WebEngine installed
- Check display settings

## Success Criteria

Deployment is successful when:
- [x] Application launches without errors
- [x] Database connection works
- [x] Known well processes correctly
- [x] All core features functional
- [x] Error handling works properly
- [x] Performance is acceptable
- [x] Logging is operational
- [x] No data loss or corruption

## Support and Maintenance

### Regular Maintenance
- Review logs weekly
- Update dependencies monthly
- Backup databases weekly
- Clean temp/output directories as needed

### Monitoring
- Track error rates in logs
- Monitor database performance
- Check disk space for logs/output
- Review user feedback

## Contact for Issues

[Add contact information for support]
