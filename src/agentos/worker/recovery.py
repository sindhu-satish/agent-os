"""Lease expiry."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentos.db.models import Execution, Task, WorkerLease
from agentos.domain.state_machine import Transition, transition

_EXPIRABLE = {"leased", "running", "cancel_requested"}


async def expire_leases(session: AsyncSession, now: datetime | None = None) -> list[UUID]:
    current = now or datetime.now(UTC)
    leases = list(
        await session.scalars(
            select(WorkerLease).where(WorkerLease.expires_at < current).with_for_update()
        )
    )
    expired: list[UUID] = []
    for lease in leases:
        execution = await session.get(Execution, lease.execution_id)
        if (
            execution is not None
            and execution.fencing_token == lease.fencing_token
            and execution.status in _EXPIRABLE
        ):
            execution.status = transition(execution.status, Transition.LEASE_EXPIRED)
            task = await session.get(Task, execution.task_id)
            if task is not None:
                task.status = execution.status
            expired.append(execution.id)
        await session.delete(lease)
    await session.flush()
    return expired
