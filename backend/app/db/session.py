from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    # A free-tier serverless Postgres (Neon, used in production - see
    # docs/DEPLOYMENT.md) closes idle connections from under a long-lived
    # pool; without this, the first query after a quiet period fails with
    # asyncpg.exceptions.InterfaceError: connection is closed instead of
    # transparently reconnecting.
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, expire_on_commit=False, class_=AsyncSession
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
