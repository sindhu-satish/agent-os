import pytest
from pydantic import ValidationError

from agentos.config import Settings, get_settings


def test_missing_required_settings_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTOS_DATABASE_URL", raising=False)
    monkeypatch.delenv("AGENTOS_NATS_URL", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults_and_sync_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AGENTOS_DATABASE_URL",
        "postgresql+asyncpg://agentos:agentos@localhost:5432/agentos",
    )
    monkeypatch.setenv("AGENTOS_NATS_URL", "nats://localhost:4222")
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    assert settings.log_level == "INFO"
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8000
    assert settings.worker_id == "worker-1"
    assert settings.lease_seconds == 30
    assert settings.heartbeat_seconds == 5
    assert settings.bootstrap_api_key is None
    assert settings.cors_origins == "http://127.0.0.1:5173,http://localhost:5173"
    assert settings.cors_origin_list == [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    assert settings.enable_demo_routes is True
    assert (
        settings.sync_database_url == "postgresql+psycopg://agentos:agentos@localhost:5432/agentos"
    )


def test_rejects_non_postgres_and_non_nats_urls() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="mysql://localhost/agentos",
            nats_url="nats://localhost:4222",
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://localhost/agentos",
            nats_url="http://localhost:4222",
        )
