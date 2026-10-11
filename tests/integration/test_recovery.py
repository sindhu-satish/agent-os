"""Worker execution and recovery against Postgres."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentos.db.models import (
    Checkpoint,
    Execution,
    ExecutionStep,
    Organization,
    Task,
    User,
    WorkerLease,
)
from agentos.db.seed import ensure_builtin_tools
from agentos.messaging.nats_publisher import (
    JetStreamPublisher,
    connect_jetstream,
    ensure_task_stream,
)
from agentos.providers.base import ModelResult, ToolCall
from agentos.repositories.agents import AgentRepository, NewAgent
from agentos.repositories.tasks import TaskRepository, submit_task
from agentos.worker.runtime import drain_available, run_once

NATS_URL = "nats://localhost:4222"


@pytest.fixture
async def organization_id(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        await ensure_builtin_tools(session)
        organization = Organization(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
        session.add(organization)
        await session.flush()
        session.add(
            User(organization_id=organization.id, email="dev@example.com", display_name="Dev")
        )
        return organization.id


async def _agent(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        agent = await AgentRepository(session).create(
            organization_id,
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
        return agent.id


@pytest.mark.integration
async def test_worker_completes_a_queued_task(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> None:
    agent_id = await _agent(session_factory, organization_id)
    task = await submit_task(
        session_factory,
        organization_id,
        agent_id,
        "happy",
        {"text": "add 2 and 3"},
        "test",
    )
    client, jetstream = await connect_jetstream(NATS_URL)
    await ensure_task_stream(jetstream)
    try:
        completed = await run_once(
            session_factory,
            JetStreamPublisher(jetstream),
            "worker-test",
            30,
            5,
        )
    finally:
        await client.drain()
    assert completed == 1
    async with session_factory() as session:
        execution = await TaskRepository(session).latest_execution(organization_id, task.id)
        assert execution is not None
        assert execution.status == "succeeded"
        assert execution.result == {"text": "5"}
        tool_steps = await session.scalar(
            select(func.count())
            .select_from(ExecutionStep)
            .where(ExecutionStep.execution_id == execution.id, ExecutionStep.kind == "tool")
        )
    assert tool_steps == 1


@pytest.mark.integration
async def test_expired_lease_resumes_without_repeating_the_tool(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> None:
    agent_id = await _agent(session_factory, organization_id)
    task = await submit_task(
        session_factory,
        organization_id,
        agent_id,
        "crash",
        {"text": "add 2 and 3"},
        "test",
    )
    async with session_factory() as session, session.begin():
        execution = await TaskRepository(session).latest_execution(organization_id, task.id)
        assert execution is not None
        execution.status = "running"
        execution.fencing_token = 1
        stored_task = await session.get(Task, task.id)
        assert stored_task is not None
        stored_task.status = "running"
        model_output = ModelResult(
            tool_calls=[ToolCall(name="add", arguments={"a": 2, "b": 3})],
            input_tokens=12,
            output_tokens=8,
        ).model_dump()
        session.add(
            ExecutionStep(
                execution_id=execution.id,
                sequence=0,
                kind="model",
                status="succeeded",
                name="add",
                input={},
                output=model_output,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        )
        session.add(
            ExecutionStep(
                execution_id=execution.id,
                sequence=1,
                kind="tool",
                status="succeeded",
                name="add",
                input={"a": 2, "b": 3},
                output={"result": 5},
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        )
        session.add(
            Checkpoint(
                execution_id=execution.id,
                step_sequence=2,
                state={
                    "messages": [
                        {"role": "user", "content": "add 2 and 3"},
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [{"name": "add", "arguments": {"a": 2, "b": 3}}],
                        },
                        {
                            "role": "tool",
                            "name": "add",
                            "content": json.dumps({"result": 5}),
                        },
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
                execution_id=execution.id,
                worker_id="dead-worker",
                fencing_token=1,
                leased_at=datetime.now(UTC) - timedelta(seconds=60),
                heartbeat_at=datetime.now(UTC) - timedelta(seconds=60),
                expires_at=datetime.now(UTC) - timedelta(seconds=30),
            )
        )
        execution_id = execution.id
    completed = await drain_available(session_factory, "worker-test", 30, 5)
    assert completed == 1
    async with session_factory() as session:
        execution = await session.get(Execution, execution_id)
        assert execution is not None
        assert execution.status == "succeeded"
        assert execution.result == {"text": "5"}
        assert execution.fencing_token == 2
        tool_steps = list(
            await session.scalars(
                select(ExecutionStep).where(
                    ExecutionStep.execution_id == execution_id,
                    ExecutionStep.kind == "tool",
                )
            )
        )
    assert len(tool_steps) == 1
    assert tool_steps[0].output == {"result": 5}
