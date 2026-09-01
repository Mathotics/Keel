from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from keel.paths import database_path


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
    database_url: str | None = None
    default_user: str | None = None

    def resolved_database_url(self) -> str:
        """The configured URL, or a SQLite file in the user data directory."""
        if self.database_url:
            return self.database_url
        return f"sqlite+pysqlite:///{database_path().as_posix()}"


@lru_cache
def get_settings() -> KeelSettings:
    return KeelSettings()
