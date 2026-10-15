"""Process configuration loaded from the environment."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by the API and the worker."""

    model_config = SettingsConfigDict(
        env_prefix="AGENTOS_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = Field(min_length=1)
    nats_url: str = Field(min_length=1)
    log_level: str = "INFO"
    bootstrap_api_key: str | None = None
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    worker_id: str = "worker-1"
    lease_seconds: int = 30
    heartbeat_seconds: int = 5
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    enable_demo_routes: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed CORS origins from the comma-separated setting."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @field_validator("database_url")
    @classmethod
    def database_url_must_be_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError("database_url must be a postgresql URL")
        return value

    @field_validator("nats_url")
    @classmethod
    def nats_url_must_be_nats(cls, value: str) -> str:
        if not value.startswith("nats://"):
            raise ValueError("nats_url must start with nats://")
        return value

    @field_validator("lease_seconds", "heartbeat_seconds", "api_port")
    @classmethod
    def must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be positive")
        return value

    @property
    def sync_database_url(self) -> str:
        """SQLAlchemy URL for Alembic's synchronous psycopg driver."""
        if "+asyncpg" in self.database_url:
            return self.database_url.replace("+asyncpg", "+psycopg")
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    # Required fields are supplied by the environment, which mypy cannot see.
    return Settings()  # type: ignore[call-arg]
