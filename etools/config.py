"""Centralized configuration via pydantic-settings.

Reads .env if present. Environment variables override .env. The default
configuration assumes a local SQL Server Express with trusted connection,
matching the dev setup.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class DatabaseConfig(BaseModel):
    server: str = r"CGDESKTOP\SQLEXPRESS"
    database: str = "UTRBDMSNET"
    trusted: bool = True
    user: str | None = None
    password: str | None = None
    driver: str = "SQL Server"
    pool_recycle: int = 3600

    def odbc_connection_string(self) -> str:
        parts = [
            f"Driver={{{self.driver}}}",
            f"Server={self.server}",
            f"Database={self.database}",
        ]
        if self.trusted:
            parts.append("Trusted_Connection=yes")
        else:
            if not self.user or not self.password:
                raise ValueError("DB credentials required when trusted=false")
            parts.append(f"UID={self.user}")
            parts.append(f"PWD={self.password}")
        return ";".join(parts) + ";"


class LLMConfig(BaseModel):
    """Local LLM (Ollama) for PDF metadata extraction."""

    enabled: bool = True
    base_url: str = "http://localhost:11434"
    model: str = "qwen3.5:9b"
    # qwen3.5 is text-only — Ollama silently accepts images and the model
    # hallucinates. For real vision, pull a VL model and set this:
    #   ollama pull qwen2.5vl:7b   (then ETOOLS_LLM__VISION_MODEL=qwen2.5vl:7b)
    # When this points at a non-VL model we skip the vision layer entirely.
    vision_model: str = "qwen2.5vl:7b"
    timeout_s: int = 600  # 10 min — qwen3.5:9b on CPU can take 5+ min on long PDFs
    request_temperature: float = 0.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ETOOLS_",
        env_nested_delimiter="__",
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    plats_db: Path = REPO_ROOT / "data" / "Board_DB_Plss_Sections.db"
    location_db: Path = REPO_ROOT / "data" / "location_data.db"
    casing_db: Path = REPO_ROOT / "data" / "CasingStrength.db"

    wcr_template: Path = REPO_ROOT / "WCR_Empty.xlsm"
    output_dir: Path = REPO_ROOT / "output"

    port: int = 8080
    log_level: str = "DEBUG"


settings = Settings()
