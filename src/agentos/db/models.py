"""Relational schema for AgentOS durable state."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from agentos.domain.status import (
    AGENT_STATUSES,
    EXECUTION_STATUSES,
    MEMORY_KINDS,
    STEP_KINDS,
    STEP_STATUSES,
    sql_in,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = created_at_column()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at_column()


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = created_at_column()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug"),
        CheckConstraint(sql_in("status", AGENT_STATUSES), name="status"),
        CheckConstraint("max_concurrency > 0", name="max_concurrency_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "agent_versions.id",
            use_alter=True,
            name="fk_agents_current_version_id_agent_versions",
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="active")
    max_concurrency: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (
        UniqueConstraint("agent_id", "version"),
        CheckConstraint("max_iterations > 0", name="max_iterations_positive"),
        CheckConstraint("max_tokens > 0", name="max_tokens_positive"),
        CheckConstraint("max_cost_micros >= 0", name="max_cost_non_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"))
    version: Mapped[int] = mapped_column(Integer)
    model_provider: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(200))
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    max_iterations: Mapped[int] = mapped_column(Integer, default=8)
    max_tokens: Mapped[int] = mapped_column(Integer, default=8000)
    max_cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = created_at_column()


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key"),
        CheckConstraint(sql_in("status", EXECUTION_STATUSES), name="status"),
        Index("ix_tasks_organization_id_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"))
    agent_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_versions.id"))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = created_at_column()


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt"),
        CheckConstraint(sql_in("status", EXECUTION_STATUSES), name="status"),
        CheckConstraint("attempt > 0", name="attempt_positive"),
        Index("ix_executions_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    fencing_token: Mapped[int] = mapped_column(BigInteger, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_column()


class ExecutionStep(Base):
    __tablename__ = "execution_steps"
    __table_args__ = (
        UniqueConstraint("execution_id", "sequence"),
        CheckConstraint(sql_in("kind", STEP_KINDS), name="kind"),
        CheckConstraint(sql_in("status", STEP_STATUSES), name="status"),
        CheckConstraint("sequence >= 0", name="sequence_non_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Checkpoint(Base):
    __tablename__ = "checkpoints"
    __table_args__ = (UniqueConstraint("execution_id", "step_sequence"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"))
    step_sequence: Mapped[int] = mapped_column(Integer)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()


class Tool(Base):
    __tablename__ = "tools"
    __table_args__ = (
        Index(
            "uq_tools_scope_name",
            text("COALESCE(organization_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "name",
            unique=True,
        ),
        CheckConstraint("timeout_ms > 0", name="timeout_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    json_schema: Mapped[dict[str, Any]] = mapped_column(JSONB)
    timeout_ms: Mapped[int] = mapped_column(Integer)
    idempotent: Mapped[bool] = mapped_column(Boolean, default=False)
    handler_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at_column()


class ToolPermission(Base):
    __tablename__ = "tool_permissions"

    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_versions.id"),
        primary_key=True,
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tools.id"), primary_key=True)


class WorkerLease(Base):
    __tablename__ = "worker_leases"
    __table_args__ = (Index("ix_worker_leases_expires_at", "expires_at"),)

    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"), primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(200))
    fencing_token: Mapped[int] = mapped_column(BigInteger)
    leased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MemoryEntry(Base):
    __tablename__ = "memory_entries"
    __table_args__ = (CheckConstraint(sql_in("kind", MEMORY_KINDS), name="kind"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"))
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("executions.id"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_column()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_organization_id_created_at", "organization_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = created_at_column()


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (
        Index(
            "ix_outbox_messages_unpublished",
            "id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    aggregate_type: Mapped[str] = mapped_column(String(100))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
