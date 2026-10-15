"""Demo recovery API against Postgres and the worker."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentos.api.app import create_app
from agentos.config import Settings
from agentos.db.models import ExecutionStep
from agentos.worker.runtime import drain_available

API_KEY = "local-dev-key"


def _settings(database_url: str, *, enable_demo_routes: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        nats_url="nats://localhost:4222",
        bootstrap_api_key=API_KEY,
        enable_demo_routes=enable_demo_routes,
    )


async def _ready(_database_url: str) -> bool:
    return True


@pytest.mark.integration
async def test_demo_recovery_endpoint_seeds_and_worker_recovers(
    session_factory: async_sessionmaker[AsyncSession],
    repo_database: str,
) -> None:
    app = create_app(
        _settings(repo_database),
        session_factory=session_factory,
        database_checker=_ready,
    )
    headers = {"Authorization": f"Bearer {API_KEY}"}
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/v1/agents",
                headers=headers,
                json={
                    "name": "Calculator",
                    "slug": f"calc-{uuid.uuid4().hex[:8]}",
                    "tool_names": ["add"],
                },
            )
            assert created.status_code == 201
            agent_id = created.json()["id"]

            seeded = await client.post(
                "/v1/demo/recoveries",
                headers=headers,
                json={"agent_id": agent_id},
            )
            assert seeded.status_code == 201
            execution_id = seeded.json()["execution_id"]

            missing = await client.post(
                "/v1/demo/recoveries",
                headers=headers,
                json={"agent_id": str(uuid.uuid4())},
            )
            assert missing.status_code == 404

    completed = await drain_available(session_factory, "worker-demo", 30, 5)
    assert completed == 1

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            execution = await client.get(f"/v1/executions/{execution_id}", headers=headers)
            assert execution.status_code == 200
            body = execution.json()
            assert body["status"] == "succeeded"
            assert body["result"] == {"text": "5"}
            tool_steps = [step for step in body["steps"] if step["kind"] == "tool"]
            assert len(tool_steps) == 1
            assert tool_steps[0]["output"] == {"result": 5}


@pytest.mark.integration
async def test_demo_routes_absent_when_disabled(
    session_factory: async_sessionmaker[AsyncSession],
    repo_database: str,
) -> None:
    app = create_app(
        _settings(repo_database, enable_demo_routes=False),
        session_factory=session_factory,
        database_checker=_ready,
    )
    headers = {"Authorization": f"Bearer {API_KEY}"}
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/demo/recoveries",
                headers=headers,
                json={"agent_id": str(uuid.uuid4())},
            )
    assert response.status_code == 404


@pytest.mark.integration
async def test_seed_helper_writes_one_tool_step(
    session_factory: async_sessionmaker[AsyncSession],
    repo_database: str,
) -> None:
    from agentos.db.models import Organization, User
    from agentos.db.seed import ensure_builtin_tools
    from agentos.demo.recovery import seed_expired_lease_recovery
    from agentos.repositories.agents import AgentRepository, NewAgent

    async with session_factory() as session, session.begin():
        await ensure_builtin_tools(session)
        organization = Organization(name="Demo", slug=f"demo-{uuid.uuid4().hex[:8]}")
        session.add(organization)
        await session.flush()
        session.add(
            User(organization_id=organization.id, email="demo@example.com", display_name="Demo")
        )
        agent = await AgentRepository(session).create(
            organization.id,
            NewAgent(
                name="Calculator",
                slug=f"calc-{uuid.uuid4().hex[:8]}",
                description="",
                model_provider="scripted",
                model_name="scripted-1",
                system_prompt="",
                tool_names=("add",),
            ),
            actor="test",
        )
        execution_id = await seed_expired_lease_recovery(session, organization.id, agent.id)
        tool_steps = list(
            await session.scalars(
                select(ExecutionStep).where(
                    ExecutionStep.execution_id == execution_id,
                    ExecutionStep.kind == "tool",
                )
            )
        )
    assert len(tool_steps) == 1
