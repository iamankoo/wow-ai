"""API smoke test that avoids touching the database (health check only)."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import health


@pytest.fixture
def health_app():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(health.router)
    return app


async def test_health_endpoint(health_app):
    transport = ASGITransport(app=health_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
