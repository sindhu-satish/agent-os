"""Postgres fixtures for repository and migration tests."""

import os
import subprocess
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentos.db.seed import ensure_builtin_tools

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = "postgresql://agentos:agentos@localhost:5432/postgres"
REPO_DATABASE_URL = "postgresql+asyncpg://agentos:agentos@localhost:5432/agentos_repo"

_TRUNCATE = """
TRUNCATE TABLE
    tool_permissions,
    worker_leases,
    checkpoints,
    execution_steps,
    memory_entries,
    executions,
    tasks,
    api_keys,
    audit_events,
    outbox_messages,
    agent_versions,
    agents,
    users,
    organizations,
    tools
RESTART IDENTITY CASCADE
"""


@pytest.fixture(scope="session")
def repo_database() -> Iterator[str]:
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS agentos_repo WITH (FORCE)")
        admin.execute("CREATE DATABASE agentos_repo")
    env = os.environ.copy()
    env["AGENTOS_DATABASE_URL"] = REPO_DATABASE_URL
    env["AGENTOS_NATS_URL"] = "nats://localhost:4222"
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)
    yield REPO_DATABASE_URL


@pytest.fixture
async def engine(repo_database: str) -> AsyncIterator[AsyncEngine]:
    database = create_async_engine(repo_database)
    yield database
    await database.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    async with engine.begin() as connection:
        await connection.execute(text(_TRUNCATE))
    async with factory() as session, session.begin():
        await ensure_builtin_tools(session)
