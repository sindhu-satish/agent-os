"""Postgres-backed execution store."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentos.db.models import (
    AgentVersion,
    Checkpoint,
    Execution,
    ExecutionStep,
    Task,
    Tool,
    ToolPermission,
    WorkerLease,
)
from agentos.domain.errors import LostLease
from agentos.domain.state_machine import Transition, transition
from agentos.execution.engine import RunContext, StoredStep
from agentos.tools.gateway import ToolSpec


class SqlExecutionStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, execution_id: UUID, fencing_token: int) -> RunContext:
        execution = await self._require(execution_id, fencing_token)
        if execution.status == "leased":
            execution.status = transition(execution.status, Transition.START)
            execution.started_at = datetime.now(UTC)
            task = await self._session.get(Task, execution.task_id)
            if task is None:
                raise LostLease(str(execution_id))
            task.status = execution.status
            await self._session.commit()
        elif execution.status not in {"running", "cancel_requested"}:
            raise LostLease(str(execution_id))
        task = await self._session.get(Task, execution.task_id)
        if task is None:
            raise LostLease(str(execution_id))
        version = await self._session.get(AgentVersion, task.agent_version_id)
        if version is None:
            raise LostLease(str(execution_id))
        checkpoint = await self._session.scalar(
            select(Checkpoint)
            .where(Checkpoint.execution_id == execution.id)
            .order_by(Checkpoint.step_sequence.desc())
            .limit(1)
        )
        specs = await self._tool_specs(version.id)
        if checkpoint is None:
            messages: list[dict[str, Any]] = []
            if version.system_prompt:
                messages.append({"role": "system", "content": version.system_prompt})
            messages.append({"role": "user", "content": _user_text(task.input)})
            return RunContext(
                execution_id=execution.id,
                fencing_token=fencing_token,
                status=execution.status,
                messages=messages,
                max_iterations=version.max_iterations,
                max_tokens=version.max_tokens,
                max_cost_micros=version.max_cost_micros,
                tool_specs=specs,
            )
        state = checkpoint.state
        return RunContext(
            execution_id=execution.id,
            fencing_token=fencing_token,
            status=execution.status,
            messages=list(state["messages"]),
            next_sequence=int(state["next_sequence"]),
            pending_tool_calls=list(state["pending_tool_calls"]),
            iterations=int(state["iterations"]),
            input_tokens=int(state["input_tokens"]),
            output_tokens=int(state["output_tokens"]),
            cost_micros=int(state["cost_micros"]),
            max_iterations=version.max_iterations,
            max_tokens=version.max_tokens,
            max_cost_micros=version.max_cost_micros,
            tool_specs=specs,
        )

    async def get_step(self, execution_id: UUID, sequence: int) -> StoredStep | None:
        step = await self._session.scalar(
            select(ExecutionStep).where(
                ExecutionStep.execution_id == execution_id,
                ExecutionStep.sequence == sequence,
            )
        )
        if step is None:
            return None
        return StoredStep(
            sequence=step.sequence,
            kind=step.kind,
            status=step.status,
            name=step.name,
            input=step.input,
            output=step.output,
        )

    async def save_step(self, context: RunContext, step: StoredStep) -> bool:
        await self._require(context.execution_id, context.fencing_token)
        self._session.add(
            ExecutionStep(
                execution_id=context.execution_id,
                sequence=step.sequence,
                kind=step.kind,
                status=step.status,
                name=step.name,
                input=step.input,
                output=step.output,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        )
        await self._session.commit()
        return True

    async def save_checkpoint(self, context: RunContext) -> bool:
        await self._require(context.execution_id, context.fencing_token)
        self._session.add(
            Checkpoint(
                execution_id=context.execution_id,
                step_sequence=context.next_sequence,
                state=_checkpoint_state(context),
            )
        )
        await self._session.commit()
        return True

    async def refresh_status(self, context: RunContext) -> str:
        execution = await self._require(context.execution_id, context.fencing_token)
        return execution.status

    async def mark_succeeded(self, context: RunContext, text: str) -> bool:
        return await self._finish(context, "succeeded", result={"text": text}, error=None)

    async def mark_failed(self, context: RunContext, error: str) -> bool:
        return await self._finish(context, "failed", result=None, error=error)

    async def mark_cancelled(self, context: RunContext) -> bool:
        execution = await self._require(context.execution_id, context.fencing_token)
        if execution.status != "cancel_requested":
            return False
        execution.status = transition(execution.status, Transition.CONFIRM_CANCEL)
        task = await self._session.get(Task, execution.task_id)
        if task is not None:
            task.status = execution.status
        execution.finished_at = datetime.now(UTC)
        await self._delete_lease(execution.id)
        await self._session.commit()
        return True

    async def _finish(
        self,
        context: RunContext,
        status: str,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> bool:
        execution = await self._require(context.execution_id, context.fencing_token)
        execution.status = status
        execution.result = result
        execution.error = error
        execution.token_usage = context.input_tokens + context.output_tokens
        execution.estimated_cost_micros = context.cost_micros
        execution.finished_at = datetime.now(UTC)
        task = await self._session.get(Task, execution.task_id)
        if task is not None:
            task.status = status
        await self._delete_lease(execution.id)
        await self._session.commit()
        return True

    async def _require(self, execution_id: UUID, fencing_token: int) -> Execution:
        execution = await self._session.scalar(
            select(Execution)
            .where(Execution.id == execution_id, Execution.fencing_token == fencing_token)
            .execution_options(populate_existing=True)
        )
        if execution is None:
            raise LostLease(str(execution_id))
        return execution

    async def _tool_specs(self, agent_version_id: UUID) -> dict[str, ToolSpec]:
        tools = await self._session.scalars(
            select(Tool)
            .join(ToolPermission, ToolPermission.tool_id == Tool.id)
            .where(ToolPermission.agent_version_id == agent_version_id)
        )
        return {
            tool.name: ToolSpec(
                name=tool.name,
                handler_key=tool.handler_key,
                json_schema=tool.json_schema,
                timeout_ms=tool.timeout_ms,
            )
            for tool in tools
        }

    async def _delete_lease(self, execution_id: UUID) -> None:
        lease = await self._session.get(WorkerLease, execution_id)
        if lease is not None:
            await self._session.delete(lease)


def _user_text(payload: dict[str, Any]) -> str:
    text = payload.get("text")
    if isinstance(text, str):
        return text
    return json.dumps(payload, sort_keys=True)


def _checkpoint_state(context: RunContext) -> dict[str, Any]:
    return {
        "messages": context.messages,
        "next_sequence": context.next_sequence,
        "pending_tool_calls": context.pending_tool_calls,
        "iterations": context.iterations,
        "input_tokens": context.input_tokens,
        "output_tokens": context.output_tokens,
        "cost_micros": context.cost_micros,
    }
