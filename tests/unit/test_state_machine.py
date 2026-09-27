import pytest

from agentos.domain.errors import AgentOSError
from agentos.domain.state_machine import IllegalTransition, Transition, transition


@pytest.mark.parametrize(
    ("current", "event", "expected"),
    [
        ("pending", Transition.COMMIT_OUTBOX, "queued"),
        ("queued", Transition.CLAIM_LEASE, "leased"),
        ("recovering", Transition.RECLAIM, "leased"),
        ("leased", Transition.START, "running"),
        ("running", Transition.SUCCEED, "succeeded"),
        ("running", Transition.FAIL, "failed"),
        ("failed", Transition.RETRY, "queued"),
        ("failed", Transition.DEAD_LETTER, "dead_letter"),
        ("queued", Transition.CANCEL, "cancelled"),
        ("leased", Transition.CANCEL, "cancel_requested"),
        ("running", Transition.CANCEL, "cancel_requested"),
        ("cancel_requested", Transition.CONFIRM_CANCEL, "cancelled"),
        ("leased", Transition.LEASE_EXPIRED, "recovering"),
        ("running", Transition.LEASE_EXPIRED, "recovering"),
        ("cancel_requested", Transition.LEASE_EXPIRED, "recovering"),
    ],
)
def test_legal_transitions(current: str, event: Transition, expected: str) -> None:
    assert transition(current, event) == expected


@pytest.mark.parametrize(
    ("current", "event"),
    [
        ("succeeded", Transition.RETRY),
        ("pending", Transition.START),
        ("queued", Transition.SUCCEED),
        ("cancelled", Transition.CLAIM_LEASE),
        ("dead_letter", Transition.RETRY),
        ("running", Transition.RETRY),
        ("failed", Transition.CANCEL),
    ],
)
def test_illegal_transitions(current: str, event: Transition) -> None:
    with pytest.raises(IllegalTransition):
        transition(current, event)


def test_illegal_transition_is_a_domain_error() -> None:
    assert issubclass(IllegalTransition, AgentOSError)
