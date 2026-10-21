"""Application configuration loaded from environment variables."""
from typing import Optional

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API."""

    app_name: str = "premedia-api"
    
    google_cloud_project: Optional[str] = None
    firestore_collection: str = "artwork_tasks"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""

    return Settings()


settings = get_settings()
