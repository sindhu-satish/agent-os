import json
import logging

import pytest
from httpx import ASGITransport, AsyncClient

from agentos.api.app import create_app
from agentos.config import Settings
from agentos.logging import JsonFormatter, redact_text


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://agentos:agentos@localhost:5432/agentos",
        nats_url="nats://localhost:4222",
    )


def test_redact_text_hides_bearer_tokens() -> None:
    raw = "Authorization: Bearer local-dev-key"
    assert redact_text(raw) == "Authorization: Bearer [redacted]"
    assert "local-dev-key" not in redact_text(raw)


def test_json_formatter_redacts_message() -> None:
    record = logging.LogRecord(
        name="agentos",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="header Authorization: Bearer secret-token",
        args=(),
        exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "header Authorization: Bearer [redacted]"
    assert "secret-token" not in payload["message"]


@pytest.mark.asyncio
async def test_health_is_ok() -> None:
    app = create_app(_settings(), database_checker=_ready(True))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_reports_database_failure() -> None:
    app = create_app(_settings(), database_checker=_ready(False))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_ready_succeeds_when_database_check_passes() -> None:
    app = create_app(_settings(), database_checker=_ready(True))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def _ready(value: bool):
    async def checker(_database_url: str) -> bool:
        return value

    return checker
