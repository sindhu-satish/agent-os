"""Repository behavior against Postgres."""

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentos.db.models import Execution, Organization, Task, User
from agentos.db.seed import ensure_builtin_tools
from agentos.domain.errors import IdempotencyConflict, LostLease, NotFound
from agentos.repositories.agents import AgentRepository, NewAgent
from agentos.repositories.leases import LeaseRepository
from agentos.repositories.tasks import submit_task


@pytest.fixture
async def organization(
    session_factory: async_sessionmaker[AsyncSession],
) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        await ensure_builtin_tools(session)
        org = Organization(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
        session.add(org)
        await session.flush()
        session.add(
            User(
                organization_id=org.id,
                email="dev@example.com",
                display_name="Dev",
            )
        )
        return org.id


async def _agent(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    *,
    max_concurrency: int = 1,
) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        agent = await AgentRepository(session).create(
            organization_id,
            NewAgent(
                name="Calculator",
                slug=f"calc-{uuid.uuid4().hex[:8]}",
                description="",
                model_provider="scripted",
                model_name="scripted-1",
                system_prompt="Add numbers.",
                tool_names=("add",),
                max_concurrency=max_concurrency,
            ),
            actor="test",
        )
        return agent.id


@pytest.mark.integration
async def test_unknown_tool_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
    organization: uuid.UUID,
) -> None:
    async with session_factory() as session, session.begin():
        with pytest.raises(NotFound):
            await AgentRepository(session).create(
                organization,
                NewAgent(
                    name="Bad",
                    slug="bad",
                    description="",
                    model_provider="scripted",
                    model_name="scripted-1",
                    system_prompt="",
                    tool_names=("shell",),
                ),
                actor="test",
            )


@pytest.mark.integration
async def test_idempotent_submit_replays_and_rejects_payload_changes(
    session_factory: async_sessionmaker[AsyncSession],
    organization: uuid.UUID,
) -> None:
    agent_id = await _agent(session_factory, organization)
    first = await submit_task(
        session_factory,
        organization,
        agent_id,
        "key-1",
        {"text": "add 2 and 3"},
        "test",
    )
    second = await submit_task(
        session_factory,
        organization,
        agent_id,
        "key-1",
        {"text": "add 2 and 3"},
        "test",
    )
    assert second.id == first.id
    with pytest.raises(IdempotencyConflict):
        await submit_task(
            session_factory,
            organization,
            agent_id,
            "key-1",
            {"text": "add 4 and 5"},
            "test",
        )


@pytest.mark.integration
async def test_concurrent_claims_produce_one_lease(
    session_factory: async_sessionmaker[AsyncSession],
    organization: uuid.UUID,
) -> None:
    agent_id = await _agent(session_factory, organization)
    await submit_task(
        session_factory,
        organization,
        agent_id,
        "race",
        {"text": "add 2 and 3"},
        "test",
    )

    async def claim() -> object:
        async with session_factory() as session, session.begin():
            return await LeaseRepository(session).claim_next("worker", 30)

    results = await asyncio.gather(claim(), claim())
    claims = [result for result in results if result is not None]
    assert len(claims) == 1


@pytest.mark.integration
async def test_claim_respects_priority_and_concurrency(
    session_factory: async_sessionmaker[AsyncSession],
    organization: uuid.UUID,
) -> None:
    agent_id = await _agent(session_factory, organization, max_concurrency=1)
    low = await submit_task(
        session_factory, organization, agent_id, "low", {"text": "low"}, "test", priority=1
    )
    high = await submit_task(
        session_factory, organization, agent_id, "high", {"text": "high"}, "test", priority=10
    )
    async with session_factory() as session, session.begin():
        first = await LeaseRepository(session).claim_next("worker", 30)
        assert first is not None
        assert first.task_id == high.id
        second = await LeaseRepository(session).claim_next("worker", 30)
        assert second is None
    async with session_factory() as session:
        low_task = await session.get(Task, low.id)
        assert low_task is not None
        assert low_task.status == "queued"


@pytest.mark.integration
async def test_stale_fence_cannot_heartbeat_or_write(
    session_factory: async_sessionmaker[AsyncSession],
    organization: uuid.UUID,
) -> None:
    agent_id = await _agent(session_factory, organization)
    task = await submit_task(
        session_factory, organization, agent_id, "fence", {"text": "add 1 and 1"}, "test"
    )
    async with session_factory() as session, session.begin():
        claim = await LeaseRepository(session).claim_next("worker", 30)
        assert claim is not None
        execution = await session.scalar(select(Execution).where(Execution.task_id == task.id))
        assert execution is not None
        execution.status = "running"
        assert await LeaseRepository(session).heartbeat(claim.execution_id, claim.fencing_token, 30)
        assert not await LeaseRepository(session).heartbeat(claim.execution_id, 999, 30)
        await LeaseRepository(session).require_running(claim.execution_id, claim.fencing_token)
        with pytest.raises(LostLease):
            await LeaseRepository(session).require_running(claim.execution_id, 999)
