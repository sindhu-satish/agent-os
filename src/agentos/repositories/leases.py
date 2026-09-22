"""Execution leases with fencing tokens."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from agentos.db.models import Agent, Execution, Task, WorkerLease
from agentos.domain.errors import LostLease

CLAIMABLE = ("queued", "recovering")
ACTIVE = ("leased", "running", "cancel_requested")


@dataclass(frozen=True)
class Claim:
    execution_id: uuid.UUID
    task_id: uuid.UUID
    fencing_token: int


class LeaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim_next(
        self,
        worker_id: str,
        lease_seconds: int,
        execution_id: uuid.UUID | None = None,
    ) -> Claim | None:
        active_execution = aliased(Execution)
        active_task = aliased(Task)
        active_count = (
            select(func.count(active_execution.id))
            .select_from(active_execution)
            .join(active_task, active_task.id == active_execution.task_id)
            .where(active_task.agent_id == Agent.id)
            .where(active_execution.status.in_(ACTIVE))
            .correlate(Agent)
            .scalar_subquery()
        )
        statement = (
            select(Execution)
            .join(Task, Task.id == Execution.task_id)
            .join(Agent, Agent.id == Task.agent_id)
            .where(Execution.status.in_(CLAIMABLE))
            .where(active_count < Agent.max_concurrency)
            .order_by(Task.priority.desc(), Execution.created_at.asc(), Execution.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True, of=(Execution, Agent))
        )
        if execution_id is not None:
            statement = statement.where(Execution.id == execution_id)
        execution = await self._session.scalar(statement)
        if execution is None:
            return None
        now = datetime.now(UTC)
        token = execution.fencing_token + 1
        execution.fencing_token = token
        execution.status = "leased"
        execution.worker_id = worker_id
        task = await self._session.get(Task, execution.task_id)
        if task is None:
            raise LostLease(str(execution.id))
        task.status = "leased"
        expires_at = now + timedelta(seconds=lease_seconds)
        lease = await self._session.get(WorkerLease, execution.id)
        if lease is None:
            self._session.add(
                WorkerLease(
                    execution_id=execution.id,
                    worker_id=worker_id,
                    fencing_token=token,
                    leased_at=now,
                    heartbeat_at=now,
                    expires_at=expires_at,
                )
            )
        else:
            lease.worker_id = worker_id
            lease.fencing_token = token
            lease.leased_at = now
            lease.heartbeat_at = now
            lease.expires_at = expires_at
        await self._session.flush()
        return Claim(execution_id=execution.id, task_id=execution.task_id, fencing_token=token)

    async def heartbeat(
        self,
        execution_id: uuid.UUID,
        fencing_token: int,
        lease_seconds: int,
    ) -> bool:
        now = datetime.now(UTC)
        result = await self._session.execute(
            update(WorkerLease)
            .where(
                WorkerLease.execution_id == execution_id,
                WorkerLease.fencing_token == fencing_token,
            )
            .values(heartbeat_at=now, expires_at=now + timedelta(seconds=lease_seconds))
            .returning(WorkerLease.execution_id)
        )
        return result.first() is not None

    async def require_running(self, execution_id: uuid.UUID, fencing_token: int) -> Execution:
        execution = await self._session.scalar(
            select(Execution)
            .where(
                Execution.id == execution_id,
                Execution.fencing_token == fencing_token,
                Execution.status == "running",
            )
            .with_for_update()
        )
        if execution is None:
            raise LostLease(str(execution_id))
        return execution
