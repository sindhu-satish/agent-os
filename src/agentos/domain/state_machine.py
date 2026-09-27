"""Legal execution status transitions."""

from enum import StrEnum

from agentos.domain.errors import AgentOSError


class Transition(StrEnum):
    COMMIT_OUTBOX = "commit_outbox"
    CLAIM_LEASE = "claim_lease"
    START = "start"
    SUCCEED = "succeed"
    FAIL = "fail"
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"
    CANCEL = "cancel"
    CONFIRM_CANCEL = "confirm_cancel"
    LEASE_EXPIRED = "lease_expired"
    RECLAIM = "reclaim"


class IllegalTransition(AgentOSError):
    """The execution is not in a state that accepts this event."""


_TRANSITIONS: dict[tuple[str, Transition], str] = {
    ("pending", Transition.COMMIT_OUTBOX): "queued",
    ("queued", Transition.CLAIM_LEASE): "leased",
    ("recovering", Transition.RECLAIM): "leased",
    ("leased", Transition.START): "running",
    ("running", Transition.SUCCEED): "succeeded",
    ("running", Transition.FAIL): "failed",
    ("failed", Transition.RETRY): "queued",
    ("failed", Transition.DEAD_LETTER): "dead_letter",
    ("queued", Transition.CANCEL): "cancelled",
    ("leased", Transition.CANCEL): "cancel_requested",
    ("running", Transition.CANCEL): "cancel_requested",
    ("cancel_requested", Transition.CONFIRM_CANCEL): "cancelled",
    ("leased", Transition.LEASE_EXPIRED): "recovering",
    ("running", Transition.LEASE_EXPIRED): "recovering",
    ("cancel_requested", Transition.LEASE_EXPIRED): "recovering",
}


def transition(current: str, event: Transition) -> str:
    try:
        return _TRANSITIONS[(current, event)]
    except KeyError as exc:
        raise IllegalTransition(f"{current} cannot accept {event}") from exc
