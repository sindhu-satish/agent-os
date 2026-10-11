"""Agent registration routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from agentos.api.deps import require_organization
from agentos.api.schemas import AgentResponse, CreateAgentRequest
from agentos.domain.errors import NotFound
from agentos.repositories.agents import AgentRepository, NewAgent

router = APIRouter(prefix="/v1/agents", tags=["agents"])


def _response(agent: object) -> AgentResponse:
    return AgentResponse.model_validate(agent, from_attributes=True)


@router.post("", status_code=201)
async def create_agent(
    body: CreateAgentRequest,
    request: Request,
    organization_id: UUID = Depends(require_organization),
) -> AgentResponse:
    if body.model_provider != "scripted":
        raise HTTPException(status_code=422, detail="only the scripted provider is available")
    try:
        async with request.app.state.session_factory() as session, session.begin():
            agent = await AgentRepository(session).create(
                organization_id,
                NewAgent(
                    name=body.name,
                    slug=body.slug,
                    description=body.description,
                    model_provider=body.model_provider,
                    model_name=body.model_name,
                    system_prompt=body.system_prompt,
                    tool_names=tuple(body.tool_names),
                    max_iterations=body.max_iterations,
                    max_tokens=body.max_tokens,
                    max_cost_micros=body.max_cost_micros,
                    max_concurrency=body.max_concurrency,
                ),
                actor="api-key",
            )
            return _response(agent)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="agent slug already exists") from exc


@router.get("")
async def list_agents(
    request: Request,
    organization_id: UUID = Depends(require_organization),
) -> list[AgentResponse]:
    async with request.app.state.session_factory() as session:
        agents = await AgentRepository(session).list_for_organization(organization_id)
        return [_response(agent) for agent in agents]


@router.get("/{agent_id}")
async def get_agent(
    agent_id: UUID,
    request: Request,
    organization_id: UUID = Depends(require_organization),
) -> AgentResponse:
    async with request.app.state.session_factory() as session:
        agent = await AgentRepository(session).get(organization_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return _response(agent)
