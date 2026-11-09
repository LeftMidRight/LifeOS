from __future__ import annotations

import logging
import socket
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.capture import router as capture_router
from app.api.routes.entries import router as entries_router
from app.api.routes.health import router as health_router
from app.api.routes.insights import router as insights_router
from app.api.routes.stats import router as stats_router
from app.config import Settings, get_settings
from app.core.errors import format_validation_detail
from app.core.static import resolve_static_file
from app.db import engine

VERSION = "0.2.0"
REPO_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger("uvicorn.error")


def _web_root(settings: Settings) -> Path:
    return Path(settings.web_dist) if settings.web_dist else REPO_ROOT / "dist/web"


def _lan_urls(port: int) -> list[str]:
    urls: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                urls.add(f"http://{ip}:{port}")
    except socket.gaierror:
        pass
    return sorted(urls)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    logger.info("LifeOS v%s 已启动", VERSION)
    logger.info("本机访问   http://localhost:%s", settings.lifeos_port)
    for url in _lan_urls(settings.lifeos_port):
        logger.info("局域网访问 %s   ← 手机用这个（同一 WiFi）", url)
    logger.info("数据库     %s", settings.safe_database_url)
    if not (_web_root(settings) / "index.html").is_file():
        logger.info("未检测到 dist/web：开发模式请用 npm run dev（前端 5173，接口 8787）")
    yield
    await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="LifeOS API", version=VERSION, lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "参数不合法", "detail": format_validation_detail(exc)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("请求处理失败: %s", request.url.path)
        return JSONResponse(status_code=500, content={"error": "服务器内部错误"})

    app.include_router(health_router, prefix="/api")
    app.include_router(entries_router, prefix="/api")
    app.include_router(capture_router, prefix="/api")
    app.include_router(stats_router, prefix="/api")
    app.include_router(insights_router, prefix="/api")

    @app.api_route("/{full_path:path}", methods=["GET"])
    async def spa_fallback(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": "接口不存在"})

        web_root = _web_root(settings)
        index = web_root / "index.html"
        if not index.is_file():
            return PlainTextResponse(
                "前端尚未构建。开发模式请用 npm run dev 打开 http://localhost:5173 ，或先执行 npm run build。",
                status_code=404,
            )

        if full_path:
            file = resolve_static_file(web_root, full_path)
            if file is not None:
                return FileResponse(file)
            if Path(full_path).suffix:
                return PlainTextResponse("静态资源不存在", status_code=404)

        return FileResponse(index)

    return app


app = create_app()
