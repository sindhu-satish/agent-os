"""Deterministic model adapter used for local execution and tests."""

import json
import re
from typing import Any

from agentos.providers.base import ModelResult, ToolCall

_ADD = re.compile(r"add\s+(-?\d+(?:\.\d+)?)\s+and\s+(-?\d+(?:\.\d+)?)", re.IGNORECASE)


def _number(raw: str) -> int | float:
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return float(raw)


class ScriptedProvider:
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tool_names: list[str],
    ) -> ModelResult:
        if messages and messages[-1]["role"] == "tool":
            text = _final_text(str(messages[-1]["content"]))
            return ModelResult(text=text, input_tokens=8, output_tokens=4)
        user_text = ""
        for message in reversed(messages):
            if message["role"] == "user":
                user_text = str(message["content"])
                break
        match = _ADD.search(user_text)
        if match and "add" in tool_names:
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


def _final_text(content: str) -> str:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return content
    if isinstance(parsed, dict) and "result" in parsed:
        return str(parsed["result"])
    return content
