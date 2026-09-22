"""Agent registration and lookup, scoped by organization."""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentos.db.models import Agent, AgentVersion, AuditEvent, Tool, ToolPermission, utcnow
from agentos.domain.errors import NotFound

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class NewAgent:
    name: str
    slug: str
    description: str
    model_provider: str
    model_name: str
    system_prompt: str
    tool_names: tuple[str, ...]
    max_iterations: int = 8
    max_tokens: int = 8000
    max_cost_micros: int = 0
    max_concurrency: int = 1


class AgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, organization_id: uuid.UUID, spec: NewAgent, actor: str) -> Agent:
        if not _SLUG.fullmatch(spec.slug):
            raise ValueError("slug must be lowercase letters, numbers, and hyphens")
        if spec.max_concurrency <= 0 or spec.max_iterations <= 0 or spec.max_tokens <= 0:
            raise ValueError("budgets and concurrency must be positive")
        if spec.max_cost_micros < 0:
            raise ValueError("max cost cannot be negative")
        tools = await self._builtin_tools(spec.tool_names)
        agent = Agent(
            organization_id=organization_id,
            name=spec.name,
            slug=spec.slug,
            description=spec.description,
            status="active",
            max_concurrency=spec.max_concurrency,
            updated_at=utcnow(),
        )
        self._session.add(agent)
        await self._session.flush()
        version = AgentVersion(
            agent_id=agent.id,
            version=1,
            model_provider=spec.model_provider,
            model_name=spec.model_name,
            system_prompt=spec.system_prompt,
            max_iterations=spec.max_iterations,
            max_tokens=spec.max_tokens,
            max_cost_micros=spec.max_cost_micros,
        )
        self._session.add(version)
        await self._session.flush()
        agent.current_version_id = version.id
        for tool in tools:
            self._session.add(ToolPermission(agent_version_id=version.id, tool_id=tool.id))
        self._session.add(
            AuditEvent(
                organization_id=organization_id,
                actor=actor,
                action="agent.registered",
                resource_type="agent",
                resource_id=agent.id,
                payload={"slug": spec.slug, "version": 1},
            )
        )
        await self._session.flush()
        return agent

    async def get(self, organization_id: uuid.UUID, agent_id: uuid.UUID) -> Agent | None:
        return await self._session.scalar(
            select(Agent).where(Agent.id == agent_id, Agent.organization_id == organization_id)
        )

    async def list_for_organization(self, organization_id: uuid.UUID) -> list[Agent]:
        rows = await self._session.scalars(
            select(Agent)
            .where(Agent.organization_id == organization_id)
            .order_by(Agent.created_at, Agent.slug)
        )
        return list(rows)

    async def _builtin_tools(self, names: tuple[str, ...]) -> list[Tool]:
        if not names:
            return []
        rows = list(
            await self._session.scalars(
                select(Tool).where(Tool.organization_id.is_(None), Tool.name.in_(names))
            )
        )
        found = {tool.name for tool in rows}
        missing = [name for name in names if name not in found]
        if missing:
            raise NotFound(f"unknown tools: {', '.join(missing)}")
        return rows
