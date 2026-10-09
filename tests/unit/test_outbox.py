import json

from agentos.messaging.outbox import encode_payload, task_subject


def test_task_subject_is_tenant_scoped() -> None:
    assert task_subject("org-1") == "agentos.tasks.org-1"


def test_encode_payload_is_stable() -> None:
    encoded = encode_payload({"b": 1, "a": "x"})
    assert json.loads(encoded) == {"a": "x", "b": 1}
    assert encoded == encode_payload({"a": "x", "b": 1})
