"""API key authentication."""

from uuid import UUID

from fastapi import Header, HTTPException, Request
from sqlalchemy import select

from agentos.db.models import ApiKey
from agentos.hashing import hash_api_key


async def require_organization(
    request: Request,
    authorization: str | None = Header(default=None),
) -> UUID:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    raw_key = authorization.removeprefix("Bearer ").strip()
    if not raw_key:
        raise HTTPException(status_code=401, detail="missing bearer token")
    async with request.app.state.session_factory() as session:
        api_key = await session.scalar(
            select(ApiKey).where(
                ApiKey.key_hash == hash_api_key(raw_key),
                ApiKey.revoked_at.is_(None),
            )
        )
    if api_key is None:
        raise HTTPException(status_code=401, detail="invalid bearer token")
    return api_key.organization_id
