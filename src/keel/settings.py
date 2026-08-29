from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class KeelSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KEEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = False
    log_level: str = "info"


@lru_cache
def get_settings() -> KeelSettings:
    return KeelSettings()
