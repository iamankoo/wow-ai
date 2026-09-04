from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.routes import brain, calls, contacts, feedback, health, memories, users, verification
from app.db.base import Base
from app.db.session import engine


async def create_tables(engine: AsyncEngine) -> None:
    """Phase 1 schema bootstrap. A migrations tool (Alembic) should replace
    this once the schema needs versioned, production-safe changes."""
    async with engine.begin() as conn:
        # A managed Postgres instance (e.g. Render's) starts without the
        # pgvector extension enabled - the local dev docker-compose.yml uses
        # the pgvector/pgvector image, which does this for its default
        # database automatically. Idempotent, so safe on every boot.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables(engine)
    yield


app = FastAPI(title="WOW AI Backend", version="0.1.0", lifespan=lifespan)

# The Android app is the only real client and carries no browser cookies/
# session, so there's no CORS-relevant origin to restrict to - this exists
# so any HTTP client (the app, a browser hitting the API directly for
# debugging) can reach the deployed backend without being blocked.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(users.router)
app.include_router(contacts.router)
app.include_router(brain.router)
app.include_router(feedback.router)
app.include_router(memories.router)
app.include_router(verification.router)
app.include_router(calls.router)
