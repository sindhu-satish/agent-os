"""HTTP API against Postgres."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentos.api.app import create_app
from agentos.config import Settings

API_KEY = "local-dev-key"


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        nats_url="nats://localhost:4222",
        bootstrap_api_key=API_KEY,
    )


@pytest.mark.integration
async def test_register_submit_replay_and_cancel(
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
            unauthenticated = await client.get("/v1/agents")
            assert unauthenticated.status_code == 401

            created = await client.post(
                "/v1/agents",
                headers=headers,
                json={
                    "name": "Calculator",
                    "slug": f"calc-{uuid.uuid4().hex[:8]}",
                    "tool_names": ["add"],
                    "system_prompt": "Add numbers.",
                },
            )
            assert created.status_code == 201
            agent_id = created.json()["id"]

            listed = await client.get("/v1/agents", headers=headers)
            assert listed.status_code == 200
            assert any(agent["id"] == agent_id for agent in listed.json())

            unknown = await client.post(
                "/v1/agents",
                headers=headers,
                json={"name": "Bad", "slug": "bad-agent", "tool_names": ["shell"]},
            )
            assert unknown.status_code == 404

            submitted = await client.post(
                "/v1/tasks",
                headers=headers,
                json={
                    "agent_id": agent_id,
                    "input": {"text": "add 2 and 3"},
                    "idempotency_key": "task-1",
                },
            )
            assert submitted.status_code == 201
            body = submitted.json()
            assert body["status"] == "queued"
            execution_id = body["execution_id"]

            replay = await client.post(
                "/v1/tasks",
                headers=headers,
                json={
                    "agent_id": agent_id,
                    "input": {"text": "add 2 and 3"},
                    "idempotency_key": "task-1",
                },
            )
            assert replay.status_code == 200
            assert replay.json()["id"] == body["id"]

            conflict = await client.post(
                "/v1/tasks",
                headers=headers,
                json={
                    "agent_id": agent_id,
                    "input": {"text": "add 9 and 9"},
                    "idempotency_key": "task-1",
                },
            )
            assert conflict.status_code == 409

            fetched = await client.get(f"/v1/tasks/{body['id']}", headers=headers)
            assert fetched.status_code == 200
            execution = await client.get(f"/v1/executions/{execution_id}", headers=headers)
            assert execution.status_code == 200
            assert execution.json()["status"] == "queued"
            assert execution.json()["steps"] == []

            cancelled = await client.post(f"/v1/tasks/{body['id']}/cancel", headers=headers)
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"


async def _ready(_database_url: str) -> bool:
    return True
