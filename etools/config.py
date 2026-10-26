"""Centralized configuration via pydantic-settings.

Reads .env if present. Environment variables override .env.

ETools has no server database: well data comes from the uploaded PDFs, and
reference data from the bundled SQLite files (``plats_db`` plus the casing
catalog and Grid Numbers under ``etools/data``). Old ``ETOOLS_DB__*`` settings
are ignored.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


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
    # Smaller model for bulk work (the per-entry ops translations). On CPU
    # a ~4b model decodes ~2.5-3x faster than the 9b at near-equal quality
    # for that mechanical task. Activates automatically once pulled:
    #   ollama pull qwen3:4b
    # Falls back silently to ``model`` while it isn't pulled.
    fast_model: str | None = "qwen3:4b"
    # Concurrent Ollama requests for the ops-translation chunks. Measured
    # on this box: with the server's default OLLAMA_NUM_PARALLEL=1 the
    # requests just queue (21.4 min parallel vs 19.4 min sequential for the
    # same job), so the default is 1. Only raise this after raising
    # OLLAMA_NUM_PARALLEL on the Ollama service itself.
    parallel_requests: int = 1
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

    llm: LLMConfig = Field(default_factory=LLMConfig)

    plats_db: Path = REPO_ROOT / "data" / "Board_DB_Plss_Sections.db"

    output_dir: Path = REPO_ROOT / "output"

    # Personal WCR-processing tracker (V2's TrackingWCR.xlsx). Copy your old
    # workbook here to keep its history; a new one is created if missing.
    tracking_workbook: Path = REPO_ROOT / "TrackingWCR.xlsx"

    port: int = 8080
    log_level: str = "DEBUG"


settings = Settings()
