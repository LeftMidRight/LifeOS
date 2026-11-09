from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.core.static import resolve_static_file
from app.main import create_app


def make_settings(web_dist: Path) -> Settings:
    return Settings(
        _env_file=None,
        lifeos_database_url="mysql+aiomysql://lifeos:test@127.0.0.1:3306/lifeos",
        web_dist=str(web_dist),
    )


def test_resolve_static_file_blocks_traversal(tmp_path: Path):
    web_dist = tmp_path / "web"
    web_dist.mkdir()
    (web_dist / "index.html").write_text("ok", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")

    assert resolve_static_file(web_dist, "index.html") == (web_dist / "index.html").resolve()
    assert resolve_static_file(web_dist, "../secret.txt") is None


async def test_spa_fallback_and_missing_asset(tmp_path: Path):
    web_dist = tmp_path / "web"
    web_dist.mkdir()
    (web_dist / "index.html").write_text("<html>LifeOS</html>", encoding="utf-8")

    app = create_app(make_settings(web_dist))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        root = await client.get("/")
        assert root.status_code == 200
        assert "LifeOS" in root.text

        deep = await client.get("/timeline/detail")
        assert deep.status_code == 200
        assert "LifeOS" in deep.text

        missing = await client.get("/assets/missing.js")
        assert missing.status_code == 404
        assert missing.text == "静态资源不存在"

        api = await client.get("/api/unknown")
        assert api.status_code == 404
        assert api.json() == {"error": "接口不存在"}

        traversal = await client.get("/..%2Fsecret.txt")
        assert traversal.status_code == 404


async def test_unbuilt_frontend_message(tmp_path: Path):
    app = create_app(make_settings(tmp_path / "missing"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 404
    assert "前端尚未构建" in response.text
