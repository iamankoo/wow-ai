from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.routes import (
    brain,
    calls,
    contacts,
    feedback,
    health,
    memories,
    telephony_plivo,
    users,
    verification,
)
from app.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.security import require_api_key, validate_security_config


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
    # Refuses to start when the backend is configured to be publicly
    # reachable (PUBLIC_BASE_URL) without API_ACCESS_KEY/PLIVO_AUTH_TOKEN.
    validate_security_config(get_settings())
    await create_tables(engine)
    yield


_settings = get_settings()
# The interactive docs/OpenAPI schema enumerate every route - not served when
# the API is key-protected or publicly tunnelled.
_expose_docs = not (_settings.api_access_key or _settings.public_base_url)
app = FastAPI(
    title="WOW AI Backend",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _expose_docs else None,
    redoc_url="/redoc" if _expose_docs else None,
    openapi_url="/openapi.json" if _expose_docs else None,
)

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

# Every REST route except /health sits behind the shared API key
# (app/security.py) - a no-op while API_ACCESS_KEY is unset, enforced once
# set (mandatory whenever PUBLIC_BASE_URL is set). The Plivo router is NOT
# behind it: it is called by Plivo, not the app, and authenticates itself
# (X-Plivo-Signature-V3 on the webhook, a single-use token on the stream).
_protected = [Depends(require_api_key)]

app.include_router(health.router)
app.include_router(users.router, dependencies=_protected)
app.include_router(contacts.router, dependencies=_protected)
app.include_router(brain.router, dependencies=_protected)
app.include_router(feedback.router, dependencies=_protected)
app.include_router(memories.router, dependencies=_protected)
app.include_router(verification.router, dependencies=_protected)
app.include_router(calls.router, dependencies=_protected)
app.include_router(telephony_plivo.router)
