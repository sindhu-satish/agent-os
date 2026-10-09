"""Transactional outbox relay."""

import json
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentos.db.models import OutboxMessage


class MessagePublisher(Protocol):
    async def publish(
        self,
        subject: str,
        payload: bytes,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Publish one durable wake-up message."""


def task_subject(organization_id: str) -> str:
    return f"agentos.tasks.{organization_id}"


def encode_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


class OutboxRelay:
    def __init__(self, session: AsyncSession, publisher: MessagePublisher) -> None:
        self._session = session
        self._publisher = publisher

    async def publish_pending(self, limit: int = 50) -> int:
        rows = list(
            await self._session.scalars(
                select(OutboxMessage)
                .where(OutboxMessage.published_at.is_(None))
                .order_by(OutboxMessage.created_at, OutboxMessage.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        published = 0
        now = datetime.now(UTC)
        for row in rows:
            organization_id = str(row.payload["organization_id"])
            await self._publisher.publish(
                task_subject(organization_id),
                encode_payload(row.payload),
                headers={"Nats-Msg-Id": str(row.id)},
            )
            row.published_at = now
            published += 1
        await self._session.flush()
        return published
