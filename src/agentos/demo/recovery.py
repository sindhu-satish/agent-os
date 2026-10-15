"""Seed an expired-lease execution for local crash-recovery demos."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from agentos.db.models import Agent, Checkpoint, ExecutionStep, Task, WorkerLease
from agentos.domain.errors import NotFound
from agentos.providers.base import ModelResult, ToolCall
from agentos.repositories.tasks import TaskRepository


async def seed_expired_lease_recovery(
    session: AsyncSession,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    actor: str = "demo",
) -> uuid.UUID:
    """Insert a running execution with completed tool work and an expired lease.

    Returns the execution id. The live worker can reclaim it without repeating
    the succeeded tool step.
    """
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.organization_id != organization_id:
        raise NotFound("agent not found")
    task = await TaskRepository(session).insert(
        organization_id,
        agent.id,
        f"demo-crash-{uuid.uuid4().hex[:8]}",
        {"text": "add 2 and 3"},
        actor=actor,
    )
    execution = await TaskRepository(session).latest_execution(organization_id, task.id)
    if execution is None:
        raise NotFound("task has no execution")
    execution.status = "running"
    execution.fencing_token = 1
    stored_task = await session.get(Task, task.id)
    if stored_task is None:
        raise NotFound("task disappeared")
    stored_task.status = "running"
    add_crashed_history(session, execution.id)
    return execution.id


def add_crashed_history(session: AsyncSession, execution_id: uuid.UUID) -> None:
    """Attach succeeded model/tool steps, a checkpoint, and an expired lease."""
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
