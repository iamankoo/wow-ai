from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.routes import brain, calls, contacts, feedback, health, memories, users, verification
from app.db.base import Base
from app.db.session import engine


async def create_tables(engine: AsyncEngine) -> None:
    """Phase 1 schema bootstrap. A migrations tool (Alembic) should replace
    this once the schema needs versioned, production-safe changes."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables(engine)
    yield


app = FastAPI(title="WOW AI Backend", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(users.router)
app.include_router(contacts.router)
app.include_router(brain.router)
app.include_router(feedback.router)
app.include_router(memories.router)
app.include_router(verification.router)
app.include_router(calls.router)
