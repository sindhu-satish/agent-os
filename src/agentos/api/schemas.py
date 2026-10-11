"""Request and response schemas."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100)
    description: str = ""
    system_prompt: str = ""
    model_provider: str = "scripted"
    model_name: str = "scripted-1"
    tool_names: list[str] = Field(default_factory=list)
    max_iterations: int = 8
    max_tokens: int = 8000
    max_cost_micros: int = 0
    max_concurrency: int = 1


class AgentResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str
    status: str
    current_version_id: UUID | None
    max_concurrency: int


class CreateTaskRequest(BaseModel):
    agent_id: UUID
    input: dict[str, Any]
    idempotency_key: str = Field(min_length=1, max_length=200)
    priority: int = 0


class TaskResponse(BaseModel):
    id: UUID
    agent_id: UUID
    status: str
    idempotency_key: str
    priority: int
    input: dict[str, Any]
    execution_id: UUID | None = None


class StepResponse(BaseModel):
    sequence: int
    kind: str
    status: str
    name: str
    input: dict[str, Any]
    output: dict[str, Any] | None


class ExecutionResponse(BaseModel):
    id: UUID
    task_id: UUID
    status: str
    attempt: int
    fencing_token: int
    result: dict[str, Any] | None
    error: str | None
    steps: list[StepResponse]
