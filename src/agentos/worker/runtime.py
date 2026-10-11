"""Single-worker loop."""

import asyncio
import contextlib
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentos.config import Settings, get_settings
from agentos.db.seed import ensure_builtin_tools
from agentos.db.session import create_engine, create_session_factory
from agentos.domain.errors import LostLease
from agentos.execution.engine import ExecutionEngine
from agentos.execution.sql_store import SqlExecutionStore
from agentos.logging import configure_logging
from agentos.messaging.nats_publisher import (
    JetStreamPublisher,
    connect_jetstream,
    ensure_task_stream,
)
from agentos.messaging.outbox import OutboxRelay
from agentos.repositories.leases import Claim, LeaseRepository
from agentos.worker.recovery import expire_leases

logger = logging.getLogger(__name__)


async def drain_available(
    session_factory: async_sessionmaker[AsyncSession],
    worker_id: str,
    lease_seconds: int,
    heartbeat_seconds: int,
) -> int:
    async with session_factory() as session, session.begin():
        await expire_leases(session)
    completed = 0
    while True:
        async with session_factory() as session, session.begin():
            claim = await LeaseRepository(session).claim_next(worker_id, lease_seconds)
        if claim is None:
            return completed
        await _run_claim(session_factory, claim, lease_seconds, heartbeat_seconds)
        completed += 1


async def run_once(
    session_factory: async_sessionmaker[AsyncSession],
    publisher: JetStreamPublisher,
    worker_id: str,
    lease_seconds: int,
    heartbeat_seconds: int,
) -> int:
    try:
        async with session_factory() as session, session.begin():
            await OutboxRelay(session, publisher).publish_pending()
    except Exception:
        logger.warning("outbox publish failed", exc_info=True)
    return await drain_available(session_factory, worker_id, lease_seconds, heartbeat_seconds)


async def _run_claim(
    session_factory: async_sessionmaker[AsyncSession],
    claim: Claim,
    lease_seconds: int,
    heartbeat_seconds: int,
) -> None:
    stop = asyncio.Event()

    async def pulse() -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=heartbeat_seconds)
            except TimeoutError:
                async with session_factory() as session, session.begin():
                    alive = await LeaseRepository(session).heartbeat(
                        claim.execution_id,
                        claim.fencing_token,
                        lease_seconds,
                    )
                if not alive:
                    return

    heartbeat = asyncio.create_task(pulse())
    try:
        async with session_factory() as session:
            await ExecutionEngine(SqlExecutionStore(session)).run(
                claim.execution_id,
                claim.fencing_token,
            )
    except LostLease:
        logger.info("worker lost the lease for %s", claim.execution_id)
    finally:
        stop.set()
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat


async def serve(settings: Settings) -> None:
    configure_logging(settings.log_level)
    client, jetstream = await connect_jetstream(settings.nats_url)
    await ensure_task_stream(jetstream)
    publisher = JetStreamPublisher(jetstream)
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    async with session_factory() as session, session.begin():
        await ensure_builtin_tools(session)
    logger.info("worker %s started", settings.worker_id)
    try:
        while True:
            completed = await run_once(
                session_factory,
                publisher,
                settings.worker_id,
                settings.lease_seconds,
                settings.heartbeat_seconds,
            )
            if completed == 0:
                await asyncio.sleep(0.2)
    finally:
        await client.drain()
        await engine.dispose()


def main() -> None:
    asyncio.run(serve(get_settings()))
