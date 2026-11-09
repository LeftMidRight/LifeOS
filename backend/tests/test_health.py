from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def test_health_shape():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert set(body) == {"ok", "version", "db", "llm", "now"}
    assert set(body["llm"]) == {"configured", "model", "baseUrl"}
    assert body["now"].endswith("Z")
