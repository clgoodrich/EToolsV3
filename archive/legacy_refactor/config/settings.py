"""
Configuration management for EToolsV3.

This module provides centralized configuration using environment variables
and sensible defaults. Configuration is organized into logical groups using
dataclasses for type safety and clarity.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DatabaseConfig:
    """Database connection configuration."""

    # Production database settings
    host: str = os.getenv('DB_HOST', 'oilgas-sql-prod.ogm.utah.gov')
    database: str = os.getenv('DB_NAME', 'UTRBDMSNET')
    user: Optional[str] = os.getenv('DB_USER', None)
    password: Optional[str] = os.getenv('DB_PASSWORD', None)
    driver: str = os.getenv('DB_DRIVER', 'SQL Server')

    # Local fallback settings
    local_fallback: bool = True
    local_server: str = os.getenv('DB_LOCAL_SERVER', r'CGDESKTOP\SQLEXPRESS')
    local_database: str = os.getenv('DB_LOCAL_NAME', 'UTRBDMSNET')

    # Connection pooling settings
    pool_size: int = int(os.getenv('DB_POOL_SIZE', '5'))
    pool_recycle: int = int(os.getenv('DB_POOL_RECYCLE', '3600'))
    pool_pre_ping: bool = True

    # Timeout settings
    connect_timeout: int = int(os.getenv('DB_CONNECT_TIMEOUT', '30'))
    command_timeout: int = int(os.getenv('DB_COMMAND_TIMEOUT', '300'))

    @property
    def has_credentials(self) -> bool:
        """Check if database credentials are configured."""
        return bool(self.user and self.password)


@dataclass
class PathConfig:
    """File system paths configuration."""

    # Base directories
    root_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    data_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / 'data')

    # Database files
    plat_db: Optional[Path] = None
    casing_db: Optional[Path] = None
    location_db: Optional[Path] = None

    # Login credentials file
    login_file: str = 'logininfo.txt'

    # Output directories
    output_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / 'output')
    log_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / 'logs')
    temp_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / 'temp')

    def __post_init__(self):
        """Initialize derived paths and create directories."""
        # Set database file paths
        if self.plat_db is None:
            self.plat_db = self.data_dir / 'Board_DB_Plss_Sections.db'
        if self.casing_db is None:
            self.casing_db = self.data_dir / 'CasingStrength.db'
        if self.location_db is None:
            self.location_db = self.data_dir / 'location_data.db'

        # Create necessary directories
        for directory in [self.output_dir, self.log_dir, self.temp_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def login_file_path(self) -> Path:
        """Get full path to login credentials file."""
        return self.root_dir / self.login_file


@dataclass
class LoggingConfig:
    """Logging configuration."""

    # Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    level: str = os.getenv('LOG_LEVEL', 'INFO')

    # File logging settings
    file_enabled: bool = True
    file_max_bytes: int = 10 * 1024 * 1024  # 10 MB
    file_backup_count: int = 5

    # Console logging settings
    console_enabled: bool = True

    # Log format
    format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format: str = '%Y-%m-%d %H:%M:%S'


@dataclass
class CalculationConfig:
    """Configuration for calculation algorithms."""

    # Survey processing
    minimum_curvature_method: str = 'balanced_tangential'
    default_north_reference: str = 'true'  # 'true', 'magnetic', or 'grid'

    # KOP detection
    kop_inclination_threshold: float = 3.0  # degrees
    kop_detection_methods: list = field(default_factory=lambda: [
        'first_deviation',
        'rate_of_change',
        'moving_average',
        'curvature_based'
    ])

    # Clearance calculations
    clearance_scan_resolution: float = 10.0  # feet
    minimum_clearance_warning: float = 50.0  # feet

    # Coordinate transformations
    utm_zone: int = 12  # Utah is primarily in UTM Zone 12N
    utm_hemisphere: str = 'N'

    # Magnetic field calculations
    magnetic_field_model: str = 'WMM'  # World Magnetic Model
    magnetic_field_date: Optional[str] = None  # Use current date if None


@dataclass
class UIConfig:
    """User interface configuration."""

    # Application settings
    app_name: str = 'ETools V3'
    app_version: str = '3.0.0'

    # Window settings
    window_width: int = 1200
    window_height: int = 800

    # Visualization settings
    default_plot_dpi: int = 100
    plot_style: str = 'seaborn-v0_8-darkgrid'

    # Table display settings
    table_font_size: int = 9
    table_row_height: int = 25


@dataclass
class AppConfig:
    """Main application configuration."""

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    calculations: CalculationConfig = field(default_factory=CalculationConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    # Environment
    environment: str = os.getenv('ETOOLS_ENV', 'development')
    debug: bool = os.getenv('ETOOLS_DEBUG', 'false').lower() == 'true'

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == 'development'

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == 'production'


# Global settings instance
settings = AppConfig()


def load_credentials_from_file(login_file_path: Optional[Path] = None) -> tuple[Optional[str], Optional[str]]:
    """
    Load database credentials from login file.

    Args:
        login_file_path: Path to login credentials file. If None, uses default from settings.

    Returns:
        Tuple of (username, password) or (None, None) if file not found or invalid.
    """
    if login_file_path is None:
        login_file_path = settings.paths.login_file_path

    try:
        if not login_file_path.exists():
            return None, None

        with open(login_file_path, 'r') as file:
            lines = file.read().strip().split('\n')

        user = lines[0].split('=')[1].strip() if len(lines) > 0 else None
        password = lines[1].split('=')[1].strip() if len(lines) > 1 else None

        return user, password

    except (IndexError, ValueError, IOError):
        return None, None


def update_database_credentials():
    """
    Update database configuration with credentials from login file.

    This function should be called at application startup to load credentials
    from the logininfo.txt file if environment variables are not set.
    """
    if not settings.database.has_credentials:
        user, password = load_credentials_from_file()
        if user and password:
            settings.database.user = user
            settings.database.password = password


# Auto-load credentials on import
update_database_credentials()
