"""Idempotent seed data for builtin tools."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentos.db.models import Tool

ECHO_TOOL_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
ADD_TOOL_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")

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


async def ensure_builtin_tools(session: AsyncSession) -> None:
    existing = set(
        await session.scalars(select(Tool.handler_key).where(Tool.organization_id.is_(None)))
    )
    created_at = datetime.now(UTC)
    if "echo" not in existing:
        session.add(
            Tool(
                id=ECHO_TOOL_ID,
                organization_id=None,
                name="echo",
                description="Return the provided message.",
                json_schema=ECHO_SCHEMA,
                timeout_ms=2000,
                idempotent=True,
                handler_key="echo",
                created_at=created_at,
            )
        )
    if "add" not in existing:
        session.add(
            Tool(
                id=ADD_TOOL_ID,
                organization_id=None,
                name="add",
                description="Add two numbers.",
                json_schema=ADD_SCHEMA,
                timeout_ms=2000,
                idempotent=True,
                handler_key="add",
                created_at=created_at,
            )
        )
    await session.flush()
