"""Read models for executions."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentos.db.models import Execution, ExecutionStep, Task


async def get_execution(
    session: AsyncSession,
    organization_id: UUID,
    execution_id: UUID,
) -> tuple[Execution, list[ExecutionStep]] | None:
    execution = await session.scalar(
        select(Execution)
        .join(Task, Task.id == Execution.task_id)
        .where(Execution.id == execution_id, Task.organization_id == organization_id)
    )
    if execution is None:
        return None
    steps = list(
        await session.scalars(
            select(ExecutionStep)
            .where(ExecutionStep.execution_id == execution.id)
            .order_by(ExecutionStep.sequence)
        )
    )
    return execution, steps
