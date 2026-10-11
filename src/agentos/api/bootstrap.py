"""Development tenant bootstrap. The raw key is never written to the database."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentos.config import Settings
from agentos.db.models import ApiKey, Organization, User
from agentos.hashing import hash_api_key


async def bootstrap_api_key(session: AsyncSession, settings: Settings) -> None:
    if not settings.bootstrap_api_key:
        return
    digest = hash_api_key(settings.bootstrap_api_key)
    existing = await session.scalar(select(ApiKey).where(ApiKey.key_hash == digest))
    if existing is not None:
        return
    organization = await session.scalar(select(Organization).where(Organization.slug == "local"))
    if organization is None:
        organization = Organization(name="Local", slug="local")
        session.add(organization)
        await session.flush()
        session.add(
            User(
                organization_id=organization.id,
                email="local@agentos.dev",
                display_name="Local",
            )
        )
        await session.flush()
    user = await session.scalar(select(User).where(User.organization_id == organization.id))
    session.add(
        ApiKey(
            organization_id=organization.id,
            user_id=None if user is None else user.id,
            key_hash=digest,
            prefix=settings.bootstrap_api_key[:8],
        )
    )
    await session.flush()
