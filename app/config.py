"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Missing required values fail at startup."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # An empty key would let a request with an empty X-API-Key header through.
    api_key: SecretStr = Field(min_length=1)
    database_url: str = Field(min_length=1)

    # Where ingestion reads podcasts from. "fixtures" replays the stored iTunes
    # responses so the service can be exercised while the upstream API is down.
    ingest_source: Literal["itunes", "fixtures"] = "itunes"
    itunes_base_url: str = "https://itunes.apple.com"
    itunes_timeout_seconds: float = Field(default=10.0, gt=0)
    fixtures_dir: Path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "itunes"

    # Artwork downloads run in a thread pool; each download has its own short timeout.
    artwork_workers: int = Field(default=8, ge=1, le=64)
    artwork_timeout_seconds: float = Field(default=5.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    """Return the settings instance, built once per process."""
    return Settings()
