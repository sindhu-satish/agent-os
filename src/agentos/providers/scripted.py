"""Deterministic model adapter used for local execution and tests."""

import json
import re
from typing import Any

from agentos.providers.base import ModelResult, ToolCall

_ADD = re.compile(r"add\s+(-?\d+(?:\.\d+)?)\s+and\s+(-?\d+(?:\.\d+)?)", re.IGNORECASE)
_MULTIPLY = re.compile(
    r"multiply\s+(-?\d+(?:\.\d+)?)\s+by\s+(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_ADD_THEN_MULTIPLY = re.compile(
    r"add\s+(-?\d+(?:\.\d+)?)\s+and\s+(-?\d+(?:\.\d+)?)\s+then\s+multiply\s+by\s+"
    r"(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_SAY = re.compile(r"^(?:say|echo)\s+(.+)$", re.IGNORECASE | re.DOTALL)
_GREET = re.compile(r"^greet\s+(.+)$", re.IGNORECASE | re.DOTALL)
_LOOKUP = re.compile(r"^lookup\s+(.+)$", re.IGNORECASE | re.DOTALL)
_RESEARCH = re.compile(r"^research\s+(.+?)\s+and\s+note\s+it$", re.IGNORECASE | re.DOTALL)


def _number(raw: str) -> int | float:
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return float(raw)


def _user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message["role"] == "user":
            return str(message["content"]).strip()
    return ""


def _tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [message for message in messages if message["role"] == "tool"]


def _parse_tool_payload(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _final_text(content: str) -> str:
    parsed = _parse_tool_payload(content)
    if "result" in parsed:
        return str(parsed["result"])
    if "message" in parsed:
        return str(parsed["message"])
    if parsed.get("found") and "fact" in parsed:
        return str(parsed["fact"])
    if "fact" in parsed:
        return str(parsed["fact"])
    return content


class ScriptedProvider:
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tool_names: list[str],
    ) -> ModelResult:
        user_text = _user_text(messages)
        tools = _tool_messages(messages)
        allowed = set(tool_names)

        chain = _ADD_THEN_MULTIPLY.search(user_text)
        if chain and {"add", "multiply"} <= allowed:
            if not tools:
                return ModelResult(
                    tool_calls=[
                        ToolCall(
                            name="add",
                            arguments={
                                "a": _number(chain.group(1)),
                                "b": _number(chain.group(2)),
                            },
                        )
                    ],
                    input_tokens=14,
                    output_tokens=10,
                )
            if len(tools) == 1:
                summed = _parse_tool_payload(str(tools[0]["content"])).get("result")
                if summed is None:
                    return ModelResult(text=user_text, input_tokens=6, output_tokens=4)
                return ModelResult(
                    tool_calls=[
                        ToolCall(
                            name="multiply",
                            arguments={
                                "a": summed,
                                "b": _number(chain.group(3)),
                            },
                        )
                    ],
                    input_tokens=14,
                    output_tokens=10,
                )
            return ModelResult(
                text=_final_text(str(tools[-1]["content"])),
                input_tokens=8,
                output_tokens=4,
            )

        research = _RESEARCH.match(user_text)
        if research and {"lookup", "echo"} <= allowed:
            topic = research.group(1).strip()
            if not tools:
                return ModelResult(
                    tool_calls=[ToolCall(name="lookup", arguments={"topic": topic})],
                    input_tokens=12,
                    output_tokens=8,
                )
            if len(tools) == 1:
                fact = _parse_tool_payload(str(tools[0]["content"])).get("fact")
                note = f"Note: {fact}" if fact is not None else f"Note: unknown topic {topic}"
                return ModelResult(
                    tool_calls=[ToolCall(name="echo", arguments={"message": note})],
                    input_tokens=12,
                    output_tokens=8,
                )
            return ModelResult(
                text=_final_text(str(tools[-1]["content"])),
                input_tokens=8,
                output_tokens=4,
            )

        if tools:
            return ModelResult(
                text=_final_text(str(tools[-1]["content"])),
                input_tokens=8,
                output_tokens=4,
            )

        greet = _GREET.match(user_text)
        if greet and "concat" in allowed:
            return ModelResult(
                tool_calls=[
                    ToolCall(
                        name="concat",
                        arguments={"left": "Hello, ", "right": greet.group(1).strip()},
                    )
                ],
                input_tokens=10,
                output_tokens=6,
            )

        say = _SAY.match(user_text)
        if say and "echo" in allowed:
            return ModelResult(
                tool_calls=[ToolCall(name="echo", arguments={"message": say.group(1).strip()})],
                input_tokens=10,
                output_tokens=6,
            )

        lookup = _LOOKUP.match(user_text)
        if lookup and "lookup" in allowed:
            return ModelResult(
                tool_calls=[ToolCall(name="lookup", arguments={"topic": lookup.group(1).strip()})],
                input_tokens=10,
                output_tokens=6,
            )

        multiply = _MULTIPLY.search(user_text)
        if multiply and "multiply" in allowed:
            return ModelResult(
                tool_calls=[
                    ToolCall(
                        name="multiply",
                        arguments={
                            "a": _number(multiply.group(1)),
                            "b": _number(multiply.group(2)),
                        },
                    )
                ],
                input_tokens=12,
                output_tokens=8,
            )

        match = _ADD.search(user_text)
        if match and "add" in allowed:
            return ModelResult(
                tool_calls=[
                    ToolCall(
                        name="add",
                        arguments={
                            "a": _number(match.group(1)),
                            "b": _number(match.group(2)),
                        },
                    )
                ],
                input_tokens=12,
                output_tokens=8,
            )

        return ModelResult(text=user_text, input_tokens=6, output_tokens=4)
