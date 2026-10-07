from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_timezone: str = "America/Mexico_City"
    database_url: str = "sqlite:///data/database/app.db"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    source_check_interval_minutes: int = Field(default=15, gt=0)

    source_monitor_enabled: bool = True
    source_storage_dir: str = "data/sources"
    source_http_timeout_seconds: float = Field(default=20, gt=0)
    source_http_retries: int = Field(default=2, ge=0, le=5)
    source_max_age_hours: dict[str, float] = Field(default_factory=lambda: {
        "smn_pronostico_general": 24, "smn_potencial_tormentas": 24,
        "nhc_atlantic_twd": 24, "nhc_eastern_pacific_twd": 24,
    })

    @field_validator("source_max_age_hours")
    @classmethod
    def positive_ages(cls, value):
        if any(hours <= 0 for hours in value.values()):
            raise ValueError("La reutilización requiere un umbral positivo")
        return value

    @field_validator("app_timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
