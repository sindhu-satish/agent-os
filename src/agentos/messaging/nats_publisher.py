"""JetStream adapter for the outbox relay."""

from nats.aio.client import Client as NatsClient
from nats.js import JetStreamContext
from nats.js.errors import NotFoundError

STREAM_NAME = "AGENTOS"
STREAM_SUBJECTS = ["agentos.tasks.>"]


async def connect_jetstream(nats_url: str) -> tuple[NatsClient, JetStreamContext]:
    client = NatsClient()
    await client.connect(nats_url)
    return client, client.jetstream()


async def ensure_task_stream(jetstream: JetStreamContext) -> None:
    try:
        await jetstream.stream_info(STREAM_NAME)
    except NotFoundError:
        await jetstream.add_stream(name=STREAM_NAME, subjects=STREAM_SUBJECTS)


class JetStreamPublisher:
    def __init__(self, jetstream: JetStreamContext) -> None:
        self._jetstream = jetstream

    async def publish(
        self,
        subject: str,
        payload: bytes,
        headers: dict[str, str] | None = None,
    ) -> None:
        await self._jetstream.publish(subject, payload, headers=headers)
