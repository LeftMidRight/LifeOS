from __future__ import annotations

import os
from pathlib import Path

# Bootstrap the environment before importing any app.* module: app.config builds
# Settings at import time, so LIFEOS_DATABASE_URL must already be available.
_env_file = Path(__file__).resolve().parents[2] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _value = _line.split("=", 1)
        os.environ.setdefault(_key.strip(), _value.strip())

test_url = os.environ.get("LIFEOS_TEST_DATABASE_URL")
if not test_url:
    raise RuntimeError("LIFEOS_TEST_DATABASE_URL 未设置；测试必须使用独立测试库")
os.environ.setdefault("LIFEOS_DATABASE_URL", test_url)

from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import create_app  # noqa: E402

_settings = get_settings()
TEST_URL = _settings.lifeos_test_database_url
if not TEST_URL:
    raise RuntimeError("LIFEOS_TEST_DATABASE_URL 未设置；测试必须使用独立测试库")

SYNC_TEST_URL = TEST_URL.replace("+aiomysql", "+pymysql")

# NullPool avoids reusing aiomysql connections across pytest-asyncio's per-test
# event loops (Windows ProactorEventLoop raises on stale transports otherwise).
test_engine = create_async_engine(TEST_URL, pool_pre_ping=True, poolclass=NullPool)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)
sync_engine = create_engine(SYNC_TEST_URL, pool_pre_ping=True)


@pytest.fixture(scope="session", autouse=True)
def migrate_test_db():
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", SYNC_TEST_URL)
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
def clean_tables():
    with sync_engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE ai_insights"))
        conn.execute(text("TRUNCATE TABLE entries"))
    yield


@pytest.fixture
def db_engine() -> AsyncEngine:
    return test_engine


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with TestSession() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with TestSession() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
