from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.capture import router as capture_router
from app.api.routes.entries import router as entries_router
from app.api.routes.health import router as health_router
from app.api.routes.stats import router as stats_router
from app.config import Settings, get_settings
from app.core.errors import format_validation_detail
from app.db import engine

logger = logging.getLogger("lifeos")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="LifeOS API", version="0.2.0", lifespan=lifespan)
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
    return app


app = create_app()
