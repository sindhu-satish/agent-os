"""Local-only demo routes for crash recovery."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from agentos.api.deps import require_organization
from agentos.api.schemas import CreateDemoRecoveryRequest, DemoRecoveryResponse
from agentos.demo.recovery import seed_expired_lease_recovery
from agentos.domain.errors import NotFound

router = APIRouter(prefix="/v1/demo", tags=["demo"])


@router.post("/recoveries", status_code=201)
async def create_recovery(
    body: CreateDemoRecoveryRequest,
    request: Request,
    organization_id: UUID = Depends(require_organization),
) -> DemoRecoveryResponse:
    settings = request.app.state.settings
    if not settings.enable_demo_routes:
        raise HTTPException(status_code=404, detail="demo routes are disabled")
    try:
        async with request.app.state.session_factory() as session, session.begin():
            execution_id = await seed_expired_lease_recovery(
                session,
                organization_id,
                body.agent_id,
                actor="api-key",
            )
            return DemoRecoveryResponse(execution_id=execution_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
