"""Task submission, cancellation, and execution reads."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from agentos.api.deps import require_organization
from agentos.api.schemas import (
    CreateTaskRequest,
    ExecutionResponse,
    StepResponse,
    TaskResponse,
)
from agentos.db.models import Execution, ExecutionStep, Task
from agentos.domain.errors import IdempotencyConflict, NotFound
from agentos.domain.state_machine import IllegalTransition, Transition, transition
from agentos.hashing import hash_payload
from agentos.repositories.executions import get_execution
from agentos.repositories.tasks import TaskRepository, submit_task

router = APIRouter(prefix="/v1", tags=["tasks"])


def _task_response(task: Task, execution_id: UUID | None) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        agent_id=task.agent_id,
        status=task.status,
        idempotency_key=task.idempotency_key,
        priority=task.priority,
        input=task.input,
        execution_id=execution_id,
    )


@router.post("/tasks", status_code=201)
async def create_task(
    body: CreateTaskRequest,
    request: Request,
    response: Response,
    organization_id: UUID = Depends(require_organization),
) -> TaskResponse:
    digest = hash_payload(body.input)
    async with request.app.state.session_factory() as session:
        existing = await TaskRepository(session).get_by_key(organization_id, body.idempotency_key)
        if existing is not None:
            if existing.payload_hash != digest:
                raise HTTPException(
                    status_code=409,
                    detail="idempotency key reused with a different payload",
                )
            execution = await TaskRepository(session).latest_execution(organization_id, existing.id)
            response.status_code = 200
            return _task_response(existing, None if execution is None else execution.id)
    try:
        task = await submit_task(
            request.app.state.session_factory,
            organization_id,
            body.agent_id,
            body.idempotency_key,
            body.input,
            actor="api-key",
            priority=body.priority,
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    async with request.app.state.session_factory() as session:
        execution = await TaskRepository(session).latest_execution(organization_id, task.id)
    return _task_response(task, None if execution is None else execution.id)


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: UUID,
    request: Request,
    organization_id: UUID = Depends(require_organization),
) -> TaskResponse:
    async with request.app.state.session_factory() as session:
        task = await TaskRepository(session).get(organization_id, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        execution = await TaskRepository(session).latest_execution(organization_id, task.id)
    return _task_response(task, None if execution is None else execution.id)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: UUID,
    request: Request,
    organization_id: UUID = Depends(require_organization),
) -> TaskResponse:
    async with request.app.state.session_factory() as session, session.begin():
        repository = TaskRepository(session)
        task = await repository.get(organization_id, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        execution = await repository.latest_execution(organization_id, task.id)
        if execution is None:
            raise HTTPException(status_code=404, detail="execution not found")
        try:
            new_status = transition(execution.status, Transition.CANCEL)
        except IllegalTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        execution.status = new_status
        task.status = new_status
        await session.flush()
        return _task_response(task, execution.id)


@router.get("/executions/{execution_id}")
async def read_execution(
    execution_id: UUID,
    request: Request,
    organization_id: UUID = Depends(require_organization),
) -> ExecutionResponse:
    async with request.app.state.session_factory() as session:
        found = await get_execution(session, organization_id, execution_id)
    if found is None:
        raise HTTPException(status_code=404, detail="execution not found")
    execution, steps = found
    return _execution_response(execution, steps)


def _execution_response(execution: Execution, steps: list[ExecutionStep]) -> ExecutionResponse:
    return ExecutionResponse(
        id=execution.id,
        task_id=execution.task_id,
        status=execution.status,
        attempt=execution.attempt,
        fencing_token=execution.fencing_token,
        result=execution.result,
        error=execution.error,
        steps=[
            StepResponse(
                sequence=step.sequence,
                kind=step.kind,
                status=step.status,
                name=step.name,
                input=step.input,
                output=step.output,
            )
            for step in steps
        ],
    )
