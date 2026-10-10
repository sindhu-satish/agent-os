"""Validate, authorize, and execute allowlisted tools."""

import asyncio
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from agentos.domain.errors import ToolPermissionError, ToolTimeoutError, ToolValidationError
from agentos.tools.builtin import BUILTIN_HANDLERS, ToolHandler


@dataclass(frozen=True)
class ToolSpec:
    name: str
    handler_key: str
    json_schema: dict[str, Any]
    timeout_ms: int


class ToolGateway:
    def __init__(
        self,
        allowed: dict[str, ToolSpec],
        handlers: dict[str, ToolHandler] | None = None,
    ) -> None:
        self._allowed = allowed
        self._handlers = handlers or BUILTIN_HANDLERS

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        spec = self._allowed.get(name)
        if spec is None:
            raise ToolPermissionError(name)
        handler = self._handlers.get(spec.handler_key)
        if handler is None:
            raise ToolPermissionError(spec.handler_key)
        validator = Draft202012Validator(spec.json_schema)
        errors = sorted(validator.iter_errors(arguments), key=lambda item: list(item.path))
        if errors:
            raise ToolValidationError(errors[0].message)
        try:
            return await asyncio.wait_for(handler(arguments), timeout=spec.timeout_ms / 1000)
        except TimeoutError as exc:
            raise ToolTimeoutError(name) from exc
