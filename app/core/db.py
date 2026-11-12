from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

# API engine: connects as the RLS-enforced role.
engine = create_async_engine(settings.database_url, pool_size=10, max_overflow=20, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def bind_tenant(session: AsyncSession, tenant_id: UUID | str) -> None:
    """Set the RLS tenant for the CURRENT TRANSACTION only (is_local=true).

    Because it is transaction-scoped it can never leak across pooled connections.
    """
    await session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)})


@asynccontextmanager
async def system_session():
    """Cross-tenant session for Celery/ops. Uses the BYPASSRLS role and a NullPool engine
    (each Celery task runs in its own event loop, so pooled connections can't be reused)."""
    eng = create_async_engine(settings.database_url_system, poolclass=NullPool)
    try:
        async with async_sessionmaker(eng, expire_on_commit=False)() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise
    finally:
        await eng.dispose()


# Platform engine: the super admin portal and public registration need to look across tenants, so they use the
# BYPASSRLS role. Only app/api/v1/platform*.py, registration.py and the login-status check use it.
platform_engine = create_async_engine(settings.database_url_system, pool_size=5, max_overflow=10, pool_pre_ping=True)
PlatformSession = async_sessionmaker(platform_engine, expire_on_commit=False)
