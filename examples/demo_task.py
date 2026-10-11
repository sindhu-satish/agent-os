"""Register an agent, run a task, and recover an expired lease.

Requires the Compose stack:

    docker compose up --build

The bootstrap key is AGENTOS_BOOTSTRAP_API_KEY, defaulting to local-dev-key.
"""

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from agentos.db.models import Agent, Checkpoint, ExecutionStep, Task, WorkerLease
from agentos.db.session import create_engine, create_session_factory
from agentos.providers.base import ModelResult, ToolCall
from agentos.repositories.tasks import TaskRepository

API_URL = os.environ.get("AGENTOS_API_URL", "http://127.0.0.1:8000")
DATABASE_URL = os.environ.get(
    "AGENTOS_DATABASE_URL",
    "postgresql+asyncpg://agentos:agentos@localhost:5432/agentos",
)
API_KEY = os.environ.get("AGENTOS_BOOTSTRAP_API_KEY", "local-dev-key")


async def main() -> None:
    headers = {"Authorization": f"Bearer {API_KEY}"}
    async with httpx.AsyncClient(base_url=API_URL, timeout=10) as client:
        await _wait_ready(client)
        agent_id = await _register(client, headers)
        execution = await _submit_and_wait(client, headers, agent_id, "demo-happy")
        if execution["result"]["text"] != "5":
            raise SystemExit(f"unexpected happy-path result: {execution['result']}")
        print(f"completed execution {execution['id']} with result 5")
        crashed_id = await _seed_expired_lease(agent_id)
        recovered = await _wait_execution(client, headers, crashed_id)
        tool_steps = [step for step in recovered["steps"] if step["kind"] == "tool"]
        if recovered["result"]["text"] != "5" or len(tool_steps) != 1:
            raise SystemExit(f"recovery repeated or lost work: {recovered}")
        print(f"recovered execution {crashed_id} without repeating the tool step")


async def _wait_ready(client: httpx.AsyncClient) -> None:
    for _ in range(30):
        try:
            response = await client.get("/ready")
        except httpx.HTTPError:
            await asyncio.sleep(1)
            continue
        if response.status_code == 200:
            return
        await asyncio.sleep(1)
    raise SystemExit(f"API at {API_URL} did not become ready")


async def _register(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/v1/agents",
        headers=headers,
        json={
            "name": "Calculator",
            "slug": f"calc-{uuid.uuid4().hex[:8]}",
            "tool_names": ["add"],
            "system_prompt": "Add numbers.",
        },
    )
    response.raise_for_status()
    return str(response.json()["id"])


async def _submit_and_wait(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    agent_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    response = await client.post(
        "/v1/tasks",
        headers=headers,
        json={
            "agent_id": agent_id,
            "input": {"text": "add 2 and 3"},
            "idempotency_key": idempotency_key,
        },
    )
    response.raise_for_status()
    return await _wait_execution(client, headers, str(response.json()["execution_id"]))


async def _wait_execution(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    execution_id: str,
) -> dict[str, Any]:
    for _ in range(40):
        response = await client.get(f"/v1/executions/{execution_id}", headers=headers)
        response.raise_for_status()
        body = response.json()
        if body["status"] in {"succeeded", "failed", "cancelled", "dead_letter"}:
            return body
        await asyncio.sleep(0.25)
    raise SystemExit(f"execution {execution_id} did not finish")


async def _seed_expired_lease(agent_id: str) -> str:
    engine = create_engine(DATABASE_URL)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            agent = await session.get(Agent, uuid.UUID(agent_id))
            if agent is None:
                raise SystemExit("agent not found in the database")
            task = await TaskRepository(session).insert(
                agent.organization_id,
                agent.id,
                f"demo-crash-{uuid.uuid4().hex[:8]}",
                {"text": "add 2 and 3"},
                actor="demo",
            )
            execution = await TaskRepository(session).latest_execution(
                agent.organization_id,
                task.id,
            )
            if execution is None:
                raise SystemExit("task has no execution")
            execution.status = "running"
            execution.fencing_token = 1
            stored_task = await session.get(Task, task.id)
            if stored_task is None:
                raise SystemExit("task disappeared")
            stored_task.status = "running"
            _add_crashed_history(session, execution.id)
            return str(execution.id)
    finally:
        await engine.dispose()


def _add_crashed_history(session: AsyncSession, execution_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    model_output = ModelResult(
        tool_calls=[ToolCall(name="add", arguments={"a": 2, "b": 3})],
        input_tokens=12,
        output_tokens=8,
    ).model_dump()
    session.add(
        ExecutionStep(
            execution_id=execution_id,
            sequence=0,
            kind="model",
            status="succeeded",
            name="add",
            input={},
            output=model_output,
            started_at=now,
            finished_at=now,
        )
    )
    session.add(
        ExecutionStep(
            execution_id=execution_id,
            sequence=1,
            kind="tool",
            status="succeeded",
            name="add",
            input={"a": 2, "b": 3},
            output={"result": 5},
            started_at=now,
            finished_at=now,
        )
    )
    session.add(
        Checkpoint(
            execution_id=execution_id,
            step_sequence=2,
            state={
                "messages": [
                    {"role": "user", "content": "add 2 and 3"},
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"name": "add", "arguments": {"a": 2, "b": 3}}],
                    },
                    {"role": "tool", "name": "add", "content": json.dumps({"result": 5})},
                ],
                "next_sequence": 2,
                "pending_tool_calls": [],
                "iterations": 1,
                "input_tokens": 12,
                "output_tokens": 8,
                "cost_micros": 0,
            },
        )
    )
    session.add(
        WorkerLease(
            execution_id=execution_id,
            worker_id="demo-crashed-worker",
            fencing_token=1,
            leased_at=now - timedelta(seconds=60),
            heartbeat_at=now - timedelta(seconds=60),
            expires_at=now - timedelta(seconds=30),
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
