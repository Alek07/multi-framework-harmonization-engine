from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.registry import Base

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_async_engine(settings.DATABASE_URL, connect_args=connect_args)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create the schema from the models, idempotently.

    The POC ships no Alembic revision on purpose: the audit log (UCM-11) is the
    only mutable state, and `docker compose up` has to produce a working SQLite
    database on a foreign machine without a migration step. The model registry is
    what puts every table in the metadata — and, with the log's table, the
    append-only triggers it carries.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
