"""Allowlisted in-process tools."""

from collections.abc import Awaitable, Callable
from typing import Any

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def echo(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"message": arguments["message"]}


async def add(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"result": arguments["a"] + arguments["b"]}


BUILTIN_HANDLERS: dict[str, ToolHandler] = {
    "echo": echo,
    "add": add,
}
