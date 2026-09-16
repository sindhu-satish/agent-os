"""Apply the schema to Postgres and compare it with the SQLAlchemy metadata."""

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = "postgresql://agentos:agentos@localhost:5432/postgres"
TEST_URL = "postgresql://agentos:agentos@localhost:5432/agentos_test"
EXPECTED_TABLES = {
    "organizations",
    "users",
    "api_keys",
    "agents",
    "agent_versions",
    "tasks",
    "executions",
    "execution_steps",
    "checkpoints",
    "tools",
    "tool_permissions",
    "worker_leases",
    "memory_entries",
    "audit_events",
    "outbox_messages",
    "alembic_version",
}


@pytest.fixture(scope="module")
def migrated_database() -> Iterator[None]:
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS agentos_test WITH (FORCE)")
        admin.execute("CREATE DATABASE agentos_test")
    env = os.environ.copy()
    env["AGENTOS_DATABASE_URL"] = "postgresql+asyncpg://agentos:agentos@localhost:5432/agentos_test"
    env["AGENTOS_NATS_URL"] = "nats://localhost:4222"
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)
    subprocess.run(["uv", "run", "alembic", "check"], cwd=ROOT, env=env, check=True)
    yield
    subprocess.run(["uv", "run", "alembic", "downgrade", "base"], cwd=ROOT, env=env, check=True)


@pytest.mark.integration
def test_migration_matches_models_and_seeds_builtin_tools(migrated_database: None) -> None:
    with psycopg.connect(TEST_URL) as connection:
        rows = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
        names = connection.execute("SELECT name FROM tools ORDER BY name").fetchall()
    assert {row[0] for row in rows} == EXPECTED_TABLES
    assert names == [("add",), ("echo",)]
