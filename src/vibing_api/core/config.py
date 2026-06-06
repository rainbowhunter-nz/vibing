from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="VIBING_",
        extra="ignore",
    )

    app_name: str = "vibing-api"
    api_v1_prefix: str = "/api/v1"

    database_url: str = f"sqlite:///{Path.cwd() / 'vibing.db'}"
    static_dir: str | None = None

    backend_host: str = "0.0.0.0"
    backend_port: int = 8080

    transcript_timeout_seconds: float = 10.0


settings = Settings()
