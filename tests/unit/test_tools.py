import asyncio

import pytest

from agentos.db.seed import (
    ADD_SCHEMA,
    CONCAT_SCHEMA,
    ECHO_SCHEMA,
    LOOKUP_SCHEMA,
    MULTIPLY_SCHEMA,
)
from agentos.domain.errors import ToolPermissionError, ToolTimeoutError, ToolValidationError
from agentos.tools.gateway import ToolGateway, ToolSpec


def _specs() -> dict[str, ToolSpec]:
    return {
        "echo": ToolSpec("echo", "echo", ECHO_SCHEMA, 2000),
        "add": ToolSpec("add", "add", ADD_SCHEMA, 2000),
        "multiply": ToolSpec("multiply", "multiply", MULTIPLY_SCHEMA, 2000),
        "concat": ToolSpec("concat", "concat", CONCAT_SCHEMA, 2000),
        "lookup": ToolSpec("lookup", "lookup", LOOKUP_SCHEMA, 2000),
    }


@pytest.mark.asyncio
async def test_builtin_tools_succeed() -> None:
    gateway = ToolGateway(_specs())
    echo = await gateway.execute("echo", {"message": "hello"})
    added = await gateway.execute("add", {"a": 2, "b": 3})
    multiplied = await gateway.execute("multiply", {"a": 4, "b": 5})
    joined = await gateway.execute("concat", {"left": "Hello, ", "right": "Ada"})
    fact = await gateway.execute("lookup", {"topic": "capital of france"})
    assert echo == {"message": "hello"}
    assert added == {"result": 5}
    assert multiplied == {"result": 20}
    assert joined == {"message": "Hello, Ada"}
    assert fact["found"] is True
    assert fact["fact"] == "Paris"


@pytest.mark.asyncio
async def test_unknown_tool_is_denied() -> None:
    gateway = ToolGateway(_specs())
    with pytest.raises(ToolPermissionError):
        await gateway.execute("shell", {"command": "ls"})


@pytest.mark.asyncio
async def test_unknown_handler_is_denied_even_if_named() -> None:
    gateway = ToolGateway({"shell": ToolSpec("shell", "shell", {"type": "object"}, 1000)})
    with pytest.raises(ToolPermissionError):
        await gateway.execute("shell", {})


@pytest.mark.asyncio
async def test_invalid_arguments_are_rejected() -> None:
    gateway = ToolGateway(_specs())
    with pytest.raises(ToolValidationError):
        await gateway.execute("add", {"a": 1})
    with pytest.raises(ToolValidationError):
        await gateway.execute("echo", {"message": "x", "extra": True})


@pytest.mark.asyncio
async def test_tool_timeout() -> None:
    async def slow(_arguments: dict[str, object]) -> dict[str, object]:
        await asyncio.sleep(1)
        return {}

    gateway = ToolGateway(
        {"echo": ToolSpec("echo", "echo", ECHO_SCHEMA, 10)},
        handlers={"echo": slow},
    )
    with pytest.raises(ToolTimeoutError):
        await gateway.execute("echo", {"message": "hello"})
