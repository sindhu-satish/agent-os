"""FastAPI application factory."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentos.api.bootstrap import bootstrap_api_key
from agentos.api.routes.agents import router as agents_router
from agentos.api.routes.tasks import router as tasks_router
from agentos.config import Settings, get_settings
from agentos.db.seed import ensure_builtin_tools
from agentos.db.session import create_engine, create_session_factory, database_ready
from agentos.logging import configure_logging

DatabaseChecker = Callable[[str], Awaitable[bool]]


def create_app(
    settings: Settings | None = None,
    database_checker: DatabaseChecker | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    connect_database: bool = True,
) -> FastAPI:
    resolved = settings or get_settings()
    checker = database_checker or database_ready
    configure_logging(resolved.log_level)
    engine = None
    factory = session_factory
    if connect_database and factory is None:
        engine = create_engine(resolved.database_url)
        factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if connect_database and factory is not None:
            async with factory() as session, session.begin():
                await ensure_builtin_tools(session)
                await bootstrap_api_key(session, resolved)
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="AgentOS", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved
    app.state.session_factory = factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        if not await checker(resolved.database_url):
            raise HTTPException(status_code=503, detail="database unavailable")
        return {"status": "ready"}

    if connect_database:
        app.include_router(agents_router)
        app.include_router(tasks_router)
    return app
