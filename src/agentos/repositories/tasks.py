"""Idempotent task submission."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentos.db.models import Agent, AuditEvent, Execution, Task
from agentos.domain.errors import IdempotencyConflict, NotFound
from agentos.hashing import hash_payload


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(
        self,
        organization_id: uuid.UUID,
        agent_id: uuid.UUID,
        idempotency_key: str,
        task_input: dict[str, Any],
        actor: str,
        priority: int = 0,
    ) -> Task:
        digest = hash_payload(task_input)
        existing = await self.get_by_key(organization_id, idempotency_key)
        if existing is not None:
            if existing.payload_hash != digest:
                raise IdempotencyConflict(idempotency_key)
            return existing
        agent = await self._session.scalar(
            select(Agent).where(Agent.id == agent_id, Agent.organization_id == organization_id)
        )
        if agent is None or agent.current_version_id is None or agent.status != "active":
            raise NotFound("agent")
        task = Task(
            organization_id=organization_id,
            agent_id=agent.id,
            agent_version_id=agent.current_version_id,
            idempotency_key=idempotency_key,
            payload_hash=digest,
            priority=priority,
            input=task_input,
            status="queued",
        )
        self._session.add(task)
        await self._session.flush()
        self._session.add(
            Execution(
                task_id=task.id,
                attempt=1,
                status="queued",
                fencing_token=0,
            )
        )
        self._session.add(
            AuditEvent(
                organization_id=organization_id,
                actor=actor,
                action="task.submitted",
                resource_type="task",
                resource_id=task.id,
                payload={"agent_id": str(agent.id), "idempotency_key": idempotency_key},
            )
        )
        await self._session.flush()
        return task

    async def get(self, organization_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        return await self._session.scalar(
            select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
        )

    async def get_by_key(self, organization_id: uuid.UUID, idempotency_key: str) -> Task | None:
        return await self._session.scalar(
            select(Task).where(
                Task.organization_id == organization_id,
                Task.idempotency_key == idempotency_key,
            )
        )

    async def latest_execution(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> Execution | None:
        return await self._session.scalar(
            select(Execution)
            .join(Task, Task.id == Execution.task_id)
            .where(Task.id == task_id, Task.organization_id == organization_id)
            .order_by(Execution.attempt.desc())
        )


async def submit_task(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    idempotency_key: str,
    task_input: dict[str, Any],
    actor: str,
    priority: int = 0,
) -> Task:
    """Insert a task, or return the original when the idempotency key is reused."""
    digest = hash_payload(task_input)
    try:
        async with session_factory() as session, session.begin():
            return await TaskRepository(session).insert(
                organization_id,
                agent_id,
                idempotency_key,
                task_input,
                actor,
                priority,
            )
    except IntegrityError:
        async with session_factory() as session:
            existing = await TaskRepository(session).get_by_key(organization_id, idempotency_key)
        if existing is None or existing.payload_hash != digest:
            raise IdempotencyConflict(idempotency_key) from None
        return existing
