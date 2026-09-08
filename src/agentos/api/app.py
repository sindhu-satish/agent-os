"""FastAPI application factory."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException

from agentos.config import Settings, get_settings
from agentos.db.session import database_ready
from agentos.logging import configure_logging

DatabaseChecker = Callable[[str], Awaitable[bool]]


def create_app(
    settings: Settings | None = None,
    database_checker: DatabaseChecker | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    checker = database_checker or database_ready
    configure_logging(resolved.log_level)
    app = FastAPI(title="AgentOS", version="0.1.0")
    app.state.settings = resolved

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        if not await checker(resolved.database_url):
            raise HTTPException(status_code=503, detail="database unavailable")
        return {"status": "ready"}

    return app
