"""Outbox publication and duplicate wake-up handling."""

import json
import uuid

import pytest
from nats.aio.client import Client as NatsClient
from nats.js.errors import NotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentos.db.models import Organization, OutboxMessage, User
from agentos.db.seed import ensure_builtin_tools
from agentos.messaging.nats_publisher import STREAM_NAME, JetStreamPublisher, ensure_task_stream
from agentos.messaging.outbox import OutboxRelay
from agentos.repositories.agents import AgentRepository, NewAgent
from agentos.repositories.leases import LeaseRepository
from agentos.repositories.tasks import submit_task

NATS_URL = "nats://localhost:4222"


@pytest.fixture
async def organization_id(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        await ensure_builtin_tools(session)
        org = Organization(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
        session.add(org)
        await session.flush()
        session.add(User(organization_id=org.id, email="dev@example.com", display_name="Dev"))
        return org.id


@pytest.mark.integration
async def test_outbox_publish_and_duplicate_claim(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> None:
    async with session_factory() as session, session.begin():
        agent = await AgentRepository(session).create(
            organization_id,
            NewAgent(
                name="Calculator",
                slug=f"calc-{uuid.uuid4().hex[:8]}",
                description="",
                model_provider="scripted",
                model_name="scripted-1",
                system_prompt="",
                tool_names=("add",),
            ),
            actor="test",
        )
        agent_id = agent.id
    task = await submit_task(
        session_factory,
        organization_id,
        agent_id,
        "outbox-1",
        {"text": "add 2 and 3"},
        "test",
    )
    client = NatsClient()
    await client.connect(NATS_URL)
    jetstream = client.jetstream()
    try:
        await jetstream.delete_stream(STREAM_NAME)
    except NotFoundError:
        pass
    await ensure_task_stream(jetstream)
    async with session_factory() as session, session.begin():
        published = await OutboxRelay(session, JetStreamPublisher(jetstream)).publish_pending()
        assert published == 1
    async with session_factory() as session, session.begin():
        again = await OutboxRelay(session, JetStreamPublisher(jetstream)).publish_pending()
        assert again == 0
        row = await session.scalar(
            select(OutboxMessage).where(OutboxMessage.aggregate_id.is_not(None))
        )
        assert row is not None
        assert row.published_at is not None
    subscription = await jetstream.pull_subscribe(
        "agentos.tasks.>",
        durable="workers",
        stream=STREAM_NAME,
    )
    first = (await subscription.fetch(1, timeout=2))[0]
    payload = json.loads(first.data)
    await first.ack()
    await jetstream.publish(first.subject, first.data)
    second = (await subscription.fetch(1, timeout=2))[0]
    await second.ack()
    async with session_factory() as session, session.begin():
        claim = await LeaseRepository(session).claim_next(
            "worker",
            30,
            execution_id=uuid.UUID(payload["execution_id"]),
        )
        assert claim is not None
        assert claim.task_id == task.id
    async with session_factory() as session, session.begin():
        duplicate = await LeaseRepository(session).claim_next(
            "worker-2",
            30,
            execution_id=uuid.UUID(payload["execution_id"]),
        )
        assert duplicate is None
    await client.drain()
