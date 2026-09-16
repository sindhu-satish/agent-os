from agentos.db.models import Base

EXPECTED_TABLES = {
    "organizations",
    "users",
    "api_keys",
    "agents",
    "agent_versions",
    "tasks",
    "executions",
    "execution_steps",
    "checkpoints",
    "tools",
    "tool_permissions",
    "worker_leases",
    "memory_entries",
    "audit_events",
    "outbox_messages",
}


def test_metadata_contains_the_domain_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES
