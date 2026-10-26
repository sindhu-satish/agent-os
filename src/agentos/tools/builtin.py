"""Allowlisted in-process tools."""

from collections.abc import Awaitable, Callable
from typing import Any

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def echo(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"message": arguments["message"]}


async def add(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"result": arguments["a"] + arguments["b"]}


async def multiply(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"result": arguments["a"] * arguments["b"]}


async def concat(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"message": f"{arguments['left']}{arguments['right']}"}


async def lookup(arguments: dict[str, Any]) -> dict[str, Any]:
    topic = str(arguments["topic"]).strip().lower()
    facts = {
        "capital of france": {"fact": "Paris", "confidence": 1.0},
        "population of tokyo": {"fact": "14000000", "confidence": 0.9},
        "boiling point of water": {"fact": "100", "unit": "celsius", "confidence": 1.0},
        "speed of light": {"fact": "299792458", "unit": "m/s", "confidence": 1.0},
    }
    hit = facts.get(topic)
    if hit is None:
        return {"found": False, "topic": topic, "fact": None}
    return {"found": True, "topic": topic, **hit}


BUILTIN_HANDLERS: dict[str, ToolHandler] = {
    "echo": echo,
    "add": add,
    "multiply": multiply,
    "concat": concat,
    "lookup": lookup,
}
