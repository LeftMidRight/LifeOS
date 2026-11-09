from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

API_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def make_settings(web_dist: Path) -> Settings:
    return Settings(
        _env_file=None,
        lifeos_database_url="mysql+aiomysql://lifeos:test@127.0.0.1:3306/lifeos_test",
        web_dist=str(web_dist),
    )


@pytest.fixture
async def fallback_client(tmp_path: Path):
    web_dist = tmp_path / "web"
    web_dist.mkdir()
    (web_dist / "index.html").write_text("<html>LifeOS</html>", encoding="utf-8")
    app = create_app(make_settings(web_dist))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_head_root_and_health_return_200(fallback_client: AsyncClient):
    root = await fallback_client.head("/")
    assert root.status_code == 200
    assert root.content == b""

    health = await fallback_client.head("/api/health")
    assert health.status_code == 200
    assert health.content == b""
    assert health.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("method", API_METHODS)
async def test_unknown_api_path_returns_404_json(fallback_client: AsyncClient, method: str):
    response = await fallback_client.request(method, "/api/unknown")
    assert response.status_code == 404
    assert response.json() == {"error": "接口不存在"}


@pytest.mark.parametrize("method", API_METHODS)
async def test_api_root_returns_404_json(fallback_client: AsyncClient, method: str):
    response = await fallback_client.request(method, "/api")
    assert response.status_code == 404
    assert response.json() == {"error": "接口不存在"}


async def test_head_unknown_api_path_returns_404_without_body(fallback_client: AsyncClient):
    response = await fallback_client.head("/api/unknown")
    assert response.status_code == 404
    assert response.content == b""
