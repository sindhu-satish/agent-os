"""Idempotent seed data for builtin tools."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentos.db.models import Tool

ECHO_TOOL_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
ADD_TOOL_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
MULTIPLY_TOOL_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
CONCAT_TOOL_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
LOOKUP_TOOL_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")

ECHO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
}
ADD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
    "required": ["a", "b"],
}
MULTIPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
    "required": ["a", "b"],
}
CONCAT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"left": {"type": "string"}, "right": {"type": "string"}},
    "required": ["left", "right"],
}
LOOKUP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"topic": {"type": "string"}},
    "required": ["topic"],
}

_BUILTIN_TOOLS: tuple[tuple[uuid.UUID, str, str, dict[str, Any]], ...] = (
    (ECHO_TOOL_ID, "echo", "Return the provided message.", ECHO_SCHEMA),
    (ADD_TOOL_ID, "add", "Add two numbers.", ADD_SCHEMA),
    (MULTIPLY_TOOL_ID, "multiply", "Multiply two numbers.", MULTIPLY_SCHEMA),
    (CONCAT_TOOL_ID, "concat", "Concatenate two strings.", CONCAT_SCHEMA),
    (LOOKUP_TOOL_ID, "lookup", "Look up a canned fact by topic.", LOOKUP_SCHEMA),
)


async def ensure_builtin_tools(session: AsyncSession) -> None:
    existing = set(
        await session.scalars(select(Tool.handler_key).where(Tool.organization_id.is_(None)))
    )
    created_at = datetime.now(UTC)
    for tool_id, name, description, schema in _BUILTIN_TOOLS:
        if name in existing:
            continue
        session.add(
            Tool(
                id=tool_id,
                organization_id=None,
                name=name,
                description=description,
                json_schema=schema,
                timeout_ms=2000,
                idempotent=True,
                handler_key=name,
                created_at=created_at,
            )
        )
    await session.flush()
