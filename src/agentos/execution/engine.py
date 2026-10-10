"""Checkpointed execution of model and tool steps."""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from agentos.domain.errors import LostLease, ToolError
from agentos.providers.base import ModelResult
from agentos.providers.scripted import ScriptedProvider
from agentos.tools.gateway import ToolGateway, ToolSpec


class ModelProvider(Protocol):
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tool_names: list[str],
    ) -> ModelResult:
        """Return the next model result for the transcript."""


@dataclass
class StoredStep:
    sequence: int
    kind: str
    status: str
    name: str
    input: dict[str, Any]
    output: dict[str, Any] | None


@dataclass
class RunContext:
    execution_id: UUID
    fencing_token: int
    status: str
    messages: list[dict[str, Any]]
    next_sequence: int = 0
    pending_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_micros: int = 0
    max_iterations: int = 8
    max_tokens: int = 8000
    max_cost_micros: int = 0
    tool_specs: dict[str, ToolSpec] = field(default_factory=dict)
    result_text: str | None = None
    error: str | None = None


class ExecutionStore(Protocol):
    async def load(self, execution_id: UUID, fencing_token: int) -> RunContext:
        """Load the latest checkpoint or the initial transcript."""

    async def get_step(self, execution_id: UUID, sequence: int) -> StoredStep | None:
        """Return a persisted step, if this sequence already ran."""

    async def save_step(self, context: RunContext, step: StoredStep) -> bool:
        """Persist a step. Return false when the fence is stale."""

    async def save_checkpoint(self, context: RunContext) -> bool:
        """Persist the transcript. Return false when the fence is stale."""

    async def refresh_status(self, context: RunContext) -> str:
        """Return the current execution status for this fence."""

    async def mark_succeeded(self, context: RunContext, text: str) -> bool:
        """Record a terminal success."""

    async def mark_failed(self, context: RunContext, error: str) -> bool:
        """Record a terminal failure."""

    async def mark_cancelled(self, context: RunContext) -> bool:
        """Record a terminal cancellation."""


class ExecutionEngine:
    def __init__(
        self,
        store: ExecutionStore,
        provider: ModelProvider | None = None,
        gateway: ToolGateway | None = None,
    ) -> None:
        self._store = store
        self._provider = provider or ScriptedProvider()
        self._gateway = gateway

    async def run(self, execution_id: UUID, fencing_token: int) -> str:
        context = await self._store.load(execution_id, fencing_token)
        gateway = self._gateway or ToolGateway(context.tool_specs)
        while True:
            context.status = await self._store.refresh_status(context)
            if context.status == "cancel_requested":
                await self._require(await self._store.mark_cancelled(context), context)
                return "cancelled"
            if context.pending_tool_calls:
                try:
                    await self._run_tool(context, gateway)
                except ToolError:
                    return "failed"
                continue
            if self._over_budget(context):
                await self._require(
                    await self._store.mark_failed(context, self._budget_error(context)),
                    context,
                )
                return "failed"
            result, fresh = await self._model_result(context)
            if fresh:
                context.iterations += 1
                context.input_tokens += result.input_tokens
                context.output_tokens += result.output_tokens
                context.cost_micros += result.cost_micros
            self._append_assistant(context, result)
            if self._over_budget(context):
                await self._require(
                    await self._store.mark_failed(context, self._budget_error(context)),
                    context,
                )
                return "failed"
            context.pending_tool_calls = [call.model_dump() for call in result.tool_calls]
            await self._require(await self._store.save_checkpoint(context), context)
            if not result.tool_calls:
                await self._require(
                    await self._store.mark_succeeded(context, result.text or ""),
                    context,
                )
                return "succeeded"

    async def _model_result(self, context: RunContext) -> tuple[ModelResult, bool]:
        existing = await self._store.get_step(context.execution_id, context.next_sequence)
        if existing is not None and existing.status == "succeeded" and existing.output is not None:
            return ModelResult.model_validate(existing.output), False
        result = await self._provider.complete(context.messages, list(context.tool_specs))
        saved = await self._store.save_step(
            context,
            StoredStep(
                sequence=context.next_sequence,
                kind="model",
                status="succeeded",
                name=result.tool_calls[0].name if result.tool_calls else "final",
                input={"messages": context.messages},
                output=result.model_dump(),
            ),
        )
        await self._require(saved, context)
        return result, True

    async def _run_tool(self, context: RunContext, gateway: ToolGateway) -> None:
        call = context.pending_tool_calls[0]
        name = str(call["name"])
        arguments = dict(call["arguments"])
        existing = await self._store.get_step(context.execution_id, context.next_sequence)
        if existing is not None and existing.status == "succeeded":
            output = existing.output or {}
        else:
            try:
                output = await gateway.execute(name, arguments)
            except ToolError as exc:
                await self._store.save_step(
                    context,
                    StoredStep(
                        sequence=context.next_sequence,
                        kind="tool",
                        status="failed",
                        name=name,
                        input=arguments,
                        output={"error": str(exc)},
                    ),
                )
                await self._require(await self._store.mark_failed(context, str(exc)), context)
                raise
            await self._require(
                await self._store.save_step(
                    context,
                    StoredStep(
                        sequence=context.next_sequence,
                        kind="tool",
                        status="succeeded",
                        name=name,
                        input=arguments,
                        output=output,
                    ),
                ),
                context,
            )
        context.messages.append({"role": "tool", "name": name, "content": json.dumps(output)})
        context.pending_tool_calls = context.pending_tool_calls[1:]
        context.next_sequence += 1
        await self._require(await self._store.save_checkpoint(context), context)

    def _append_assistant(self, context: RunContext, result: ModelResult) -> None:
        context.messages.append(
            {
                "role": "assistant",
                "content": result.text or "",
                "tool_calls": [call.model_dump() for call in result.tool_calls],
            }
        )
        context.next_sequence += 1

    async def _require(self, saved: bool, context: RunContext) -> None:
        if not saved:
            raise LostLease(str(context.execution_id))

    def _over_budget(self, context: RunContext) -> bool:
        if context.iterations >= context.max_iterations:
            return True
        if context.input_tokens + context.output_tokens > context.max_tokens:
            return True
        return context.max_cost_micros > 0 and context.cost_micros > context.max_cost_micros

    def _budget_error(self, context: RunContext) -> str:
        if context.iterations >= context.max_iterations:
            return "iteration budget exceeded"
        if context.input_tokens + context.output_tokens > context.max_tokens:
            return "token budget exceeded"
        return "cost budget exceeded"
