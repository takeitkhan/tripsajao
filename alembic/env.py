import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import Base

target_metadata = Base.metadata
# Migrations run as the table OWNER (not the RLS-enforced app role).
from app.core.config import settings  # noqa: E402  (reads .env itself)

URL = os.environ.get("DATABASE_URL_MIGRATIONS") or settings.database_url_migrations
if not URL:
    raise SystemExit("DATABASE_URL_MIGRATIONS is not set (check your .env)")


def run_migrations_offline() -> None:
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(URL)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
