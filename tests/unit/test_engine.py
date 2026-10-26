import json
from uuid import uuid4

import pytest

from agentos.db.seed import ADD_SCHEMA
from agentos.domain.errors import LostLease
from agentos.execution.engine import ExecutionEngine, RunContext, StoredStep
from agentos.providers.base import ModelResult
from agentos.providers.scripted import ScriptedProvider
from agentos.tools.builtin import add
from agentos.tools.gateway import ToolGateway, ToolSpec


def _specs() -> dict[str, ToolSpec]:
    return {"add": ToolSpec("add", "add", ADD_SCHEMA, 2000)}


def _context(**overrides: object) -> RunContext:
    context = RunContext(
        execution_id=uuid4(),
        fencing_token=1,
        status="running",
        messages=[{"role": "user", "content": "add 2 and 3"}],
        max_iterations=4,
        tool_specs=_specs(),
    )
    for key, value in overrides.items():
        setattr(context, key, value)
    return context


class MemoryStore:
    def __init__(self, context: RunContext) -> None:
        self.context = context
        self.steps: dict[int, StoredStep] = {}
        self.cancel_after_checkpoints: int | None = None
        self.fail_writes = False
        self.checkpoints = 0

    async def load(self, execution_id: object, fencing_token: int) -> RunContext:
        return self.context

    async def get_step(self, execution_id: object, sequence: int) -> StoredStep | None:
        return self.steps.get(sequence)

    async def save_step(self, context: RunContext, step: StoredStep) -> bool:
        if self.fail_writes:
            return False
        self.steps[step.sequence] = step
        return True

    async def save_checkpoint(self, context: RunContext) -> bool:
        if self.fail_writes:
            return False
        self.checkpoints += 1
        if (
            self.cancel_after_checkpoints is not None
            and self.checkpoints >= self.cancel_after_checkpoints
        ):
            context.status = "cancel_requested"
        return True

    async def refresh_status(self, context: RunContext) -> str:
        return context.status

    async def mark_succeeded(self, context: RunContext, text: str) -> bool:
        if self.fail_writes:
            return False
        context.status = "succeeded"
        context.result_text = text
        return True

    async def mark_failed(self, context: RunContext, error: str) -> bool:
        if self.fail_writes:
            return False
        context.status = "failed"
        context.error = error
        return True

    async def mark_cancelled(self, context: RunContext) -> bool:
        if self.fail_writes:
            return False
        context.status = "cancelled"
        return True


@pytest.mark.asyncio
async def test_scripted_provider_requests_add_then_answers() -> None:
    provider = ScriptedProvider()
    first = await provider.complete(
        [{"role": "user", "content": "please add 2 and 3"}],
        ["add"],
    )
    assert first.tool_calls[0].arguments == {"a": 2, "b": 3}
    second = await provider.complete(
        [
            {"role": "user", "content": "please add 2 and 3"},
            {"role": "tool", "content": json.dumps({"result": 5})},
        ],
        ["add"],
    )
    assert second.text == "5"


@pytest.mark.asyncio
async def test_scripted_provider_chains_add_then_multiply() -> None:
    provider = ScriptedProvider()
    first = await provider.complete(
        [{"role": "user", "content": "add 2 and 3 then multiply by 4"}],
        ["add", "multiply"],
    )
    assert first.tool_calls[0].name == "add"
    second = await provider.complete(
        [
            {"role": "user", "content": "add 2 and 3 then multiply by 4"},
            {"role": "tool", "name": "add", "content": json.dumps({"result": 5})},
        ],
        ["add", "multiply"],
    )
    assert second.tool_calls[0].name == "multiply"
    assert second.tool_calls[0].arguments == {"a": 5, "b": 4}
    third = await provider.complete(
        [
            {"role": "user", "content": "add 2 and 3 then multiply by 4"},
            {"role": "tool", "name": "add", "content": json.dumps({"result": 5})},
            {"role": "tool", "name": "multiply", "content": json.dumps({"result": 20})},
        ],
        ["add", "multiply"],
    )
    assert third.text == "20"


@pytest.mark.asyncio
async def test_scripted_provider_research_then_notes() -> None:
    provider = ScriptedProvider()
    first = await provider.complete(
        [{"role": "user", "content": "research capital of france and note it"}],
        ["lookup", "echo"],
    )
    assert first.tool_calls[0].name == "lookup"
    second = await provider.complete(
        [
            {"role": "user", "content": "research capital of france and note it"},
            {
                "role": "tool",
                "name": "lookup",
                "content": json.dumps(
                    {"found": True, "topic": "capital of france", "fact": "Paris"}
                ),
            },
        ],
        ["lookup", "echo"],
    )
    assert second.tool_calls[0].name == "echo"
    assert second.tool_calls[0].arguments == {"message": "Note: Paris"}


@pytest.mark.asyncio
async def test_engine_runs_add_and_records_steps() -> None:
    store = MemoryStore(_context())
    status = await ExecutionEngine(store).run(store.context.execution_id, 1)
    assert status == "succeeded"
    assert store.context.result_text == "5"
    kinds = [step.kind for step in store.steps.values()]
    assert kinds == ["model", "tool", "model"]
    assert store.steps[1].output == {"result": 5}


@pytest.mark.asyncio
async def test_engine_cancels_between_steps() -> None:
    store = MemoryStore(_context())
    store.cancel_after_checkpoints = 1
    calls = {"add": 0}

    async def counting(arguments: dict[str, object]) -> dict[str, object]:
        calls["add"] += 1
        return await add(arguments)  # type: ignore[arg-type]

    gateway = ToolGateway(_specs(), handlers={"add": counting})
    status = await ExecutionEngine(store, gateway=gateway).run(store.context.execution_id, 1)
    assert status == "cancelled"
    assert calls["add"] == 0


@pytest.mark.asyncio
async def test_engine_resumes_without_repeating_a_succeeded_tool() -> None:
    context = _context(
        messages=[
            {"role": "user", "content": "add 2 and 3"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"name": "add", "arguments": {"a": 2, "b": 3}}],
            },
            {"role": "tool", "name": "add", "content": json.dumps({"result": 5})},
        ],
        next_sequence=2,
        iterations=1,
    )
    store = MemoryStore(context)
    store.steps[0] = StoredStep(0, "model", "succeeded", "add", {}, {})
    store.steps[1] = StoredStep(1, "tool", "succeeded", "add", {"a": 2, "b": 3}, {"result": 5})
    calls = {"add": 0}

    async def counting(arguments: dict[str, object]) -> dict[str, object]:
        calls["add"] += 1
        return {"result": 0}

    gateway = ToolGateway(_specs(), handlers={"add": counting})
    status = await ExecutionEngine(store, gateway=gateway).run(context.execution_id, 1)
    assert status == "succeeded"
    assert context.result_text == "5"
    assert calls["add"] == 0
    assert [step.kind for step in store.steps.values() if step.kind == "tool"] == ["tool"]


@pytest.mark.asyncio
async def test_iteration_budget_stops_before_a_second_model_call() -> None:
    store = MemoryStore(_context(max_iterations=1))
    status = await ExecutionEngine(store).run(store.context.execution_id, 1)
    assert status == "failed"
    assert store.context.error == "iteration budget exceeded"


class _CostlyProvider:
    async def complete(
        self,
        messages: list[dict[str, object]],
        tool_names: list[str],
    ) -> ModelResult:
        return ModelResult(text="done", input_tokens=1, output_tokens=1, cost_micros=50)


@pytest.mark.asyncio
async def test_cost_budget_fails_the_execution() -> None:
    store = MemoryStore(_context(max_cost_micros=10))
    status = await ExecutionEngine(store, provider=_CostlyProvider()).run(
        store.context.execution_id,
        1,
    )
    assert status == "failed"
    assert store.context.error == "cost budget exceeded"


@pytest.mark.asyncio
async def test_lost_lease_stops_the_engine() -> None:
    store = MemoryStore(_context())
    store.fail_writes = True
    with pytest.raises(LostLease):
        await ExecutionEngine(store).run(store.context.execution_id, 1)
