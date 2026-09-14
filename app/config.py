"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Missing required values fail at startup."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # An empty key would let a request with an empty X-API-Key header through.
    api_key: SecretStr = Field(min_length=1)
    database_url: str = Field(min_length=1)


@lru_cache
def get_settings() -> Settings:
    """Return the settings instance, built once per process."""
    return Settings()
