# LifeOS 后端 Python/FastAPI + MySQL 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Python/FastAPI + MySQL 8.0 完整替换 Node/Fastify + SQLite 后端，前端零改动、API 契约不变、现有数据全量迁移。

**Architecture:** FastAPI + Pydantic v2 + SQLAlchemy 2.0 async + aiomysql + Alembic 分层架构：`routes → services → repositories → models`。共享 TS 层保留给前端；Python 独立实现 capture 解析器，并以同一组测试锁定行为。

**Tech Stack:** Python 3.12、uv、FastAPI、Pydantic v2、SQLAlchemy 2.0（async）、aiomysql、pymysql、Alembic、httpx、pytest、pytest-asyncio、respx、ruff、MySQL 8.0.40。

**Spec:** `docs/superpowers/specs/2026-11-09-python-backend-refactor-design.md`

## Global Constraints

- Python 固定 3.12（`backend/.python-version`），依赖由 `uv` 管理。
- MySQL 8.0，库 `lifeos` / `lifeos_test`，字符集 `utf8mb4`，排序规则 `utf8mb4_0900_ai_ci`。
- 所有时间以 UTC naive 写入 `DATETIME(3)`；API 输出必须是 `YYYY-MM-DDTHH:mm:ss.sssZ`。
- API 路径、方法、JSON camelCase 字段、状态码、错误格式必须与 Node 版一致。
- 前端零改动；`shared/*.ts` 保留，不修改。
- 测试只允许连 `LIFEOS_TEST_DATABASE_URL`；缺失时测试必须失败并提示。
- 每个任务结束前运行该任务对应测试与 `ruff check`，然后提交。
- 提交信息结尾统一加：`Co-Authored-By: Claude Code <noreply@anthropic.com>`。

## Review Focus

以下五类输入/失败模式最容易在用户实际使用时出问题，规格没有逐条展开，但每个都必须在对应任务里有测试：

1. **源 SQLite 中混合时区字符串**（`+08:00` 与 `Z` 并存）迁移后必须全部归一化为 UTC，且时间排序正确 —— Task 3。
2. **PATCH 未传字段 vs 显式传 null**：未传必须保持原值，显式 null 必须写 NULL —— Task 4、Task 6。
3. **时间序列化精度**：必须固定毫秒 3 位并以 `Z` 结尾，否则前端字符串排序会错 —— Task 1、Task 5。
4. **中文标签过滤**：MySQL `JSON_CONTAINS` 必须能正确匹配 `#产品` 这类标签 —— Task 4。
5. **静态资源路径穿越**：`/../.env` 等路径不得读出 `dist/web` 之外的文件 —— Task 9。

## File Structure

```
backend/
├── pyproject.toml
├── uv.lock
├── .python-version
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/0001_initial.py
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── schemas.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py
│   │       ├── entries.py
│   │       ├── capture.py
│   │       ├── stats.py
│   │       └── insights.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── time.py
│   │   ├── errors.py
│   │   └── static.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── entries.py
│   │   └── insights.py
│   └── services/
│       ├── __init__.py
│       ├── capture.py
│       ├── insight.py
│       └── stats.py
├── scripts/
│   ├── __init__.py
│   ├── init_mysql.sql.example
│   ├── migrate_sqlite_to_mysql.py
│   └── seed.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_time.py
    ├── test_health.py
    ├── test_schema.py
    ├── test_migration.py
    ├── test_repositories_entries.py
    ├── test_api_entries_read.py
    ├── test_api_entries_write.py
    ├── test_api_stats.py
    ├── test_capture.py
    ├── test_api_capture.py
    ├── test_api_insights.py
    └── test_static.py
```

---

## Task 1: 环境基线、MySQL 初始化与健康检查

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.python-version`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/db.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/time.py`
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/insight.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/routes/__init__.py`
- Create: `backend/app/api/routes/health.py`
- Create: `backend/app/main.py`
- Create: `backend/scripts/init_mysql.sql.example`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_time.py`
- Create: `backend/tests/test_health.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `Settings`, `get_settings()`, `create_app(settings: Settings | None = None) -> FastAPI`, `to_iso_z(datetime) -> str`, `to_utc_naive(datetime) -> datetime`, `utcnow() -> datetime`, `llm_status(settings) -> dict`.

- [ ] **Step 1: 生成 MySQL 初始化脚本和本地密码**

运行：

```bash
cd E:/Code/LifeOS
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

把输出记为 `DB_PASSWORD`（只在本机使用，不提交）。创建 `backend/scripts/init_mysql.sql.example`：

```sql
CREATE DATABASE IF NOT EXISTS lifeos CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS lifeos_test CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'lifeos'@'localhost' IDENTIFIED BY 'CHANGE_ME';
CREATE USER IF NOT EXISTS 'lifeos'@'127.0.0.1' IDENTIFIED BY 'CHANGE_ME';

GRANT ALL PRIVILEGES ON lifeos.* TO 'lifeos'@'localhost';
GRANT ALL PRIVILEGES ON lifeos.* TO 'lifeos'@'127.0.0.1';
GRANT ALL PRIVILEGES ON lifeos_test.* TO 'lifeos'@'localhost';
GRANT ALL PRIVILEGES ON lifeos_test.* TO 'lifeos'@'127.0.0.1';
FLUSH PRIVILEGES;
```

生成实际执行文件（不提交）：

```bash
cd E:/Code/LifeOS
DB_PASSWORD="把上一步的输出放在这里"
sed "s/CHANGE_ME/$DB_PASSWORD/g" backend/scripts/init_mysql.sql.example > backend/scripts/init_mysql.local.sql
```

在 `.gitignore` 末尾追加：

```gitignore
backend/scripts/init_mysql.local.sql
```

- [ ] **Step 2: 人工执行 MySQL 初始化（需要用户操作）**

这一步需要用户在自己的终端执行并输入 MySQL root 密码（代理无法替用户输入密码）：

```bash
mysql -u root -p < E:/Code/LifeOS/backend/scripts/init_mysql.local.sql
```

验证：

```bash
mysql -u lifeos -p"$DB_PASSWORD" -h 127.0.0.1 -e "SHOW DATABASES LIKE 'lifeos%';"
```

预期输出包含 `lifeos` 和 `lifeos_test`。

- [ ] **Step 3: 创建根目录 `.env`（不提交）**

```bash
cat > E:/Code/LifeOS/.env <<EOF
LIFEOS_PORT=8787
LIFEOS_DATABASE_URL=mysql+aiomysql://lifeos:${DB_PASSWORD}@127.0.0.1:3306/lifeos?charset=utf8mb4
LIFEOS_TEST_DATABASE_URL=mysql+aiomysql://lifeos:${DB_PASSWORD}@127.0.0.1:3306/lifeos_test?charset=utf8mb4
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
EOF
```

- [ ] **Step 4: 写失败的测试**

创建 `backend/tests/test_time.py`：

```python
from datetime import datetime, timedelta, timezone

from app.core.time import day_range, to_iso_z, to_utc_naive


def test_to_iso_z_has_milliseconds_and_z():
    value = datetime(2026, 11, 9, 9, 34, 11, 695000, tzinfo=timezone.utc)
    assert to_iso_z(value) == "2026-11-09T09:34:11.695Z"


def test_to_iso_z_treats_naive_as_utc():
    assert to_iso_z(datetime(2026, 11, 9, 9, 34, 11, 1000)) == "2026-11-09T09:34:11.001Z"


def test_to_utc_naive_converts_offset():
    value = datetime(2026, 11, 9, 21, 15, 0, tzinfo=timezone(timedelta(hours=8)))
    assert to_utc_naive(value) == datetime(2026, 11, 9, 13, 15, 0)


def test_day_range_returns_utc_bounds():
    start, end = day_range("2026-11-09")
    assert start.tzinfo is not None
    assert end.tzinfo is not None
    assert (end - start).total_seconds() == 86400
```

创建 `backend/tests/test_health.py`：

```python
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
```

- [ ] **Step 5: 创建项目骨架并运行测试确认失败**

先创建 `backend/pyproject.toml`、`backend/.python-version` 和所有 `__init__.py`（完整内容见 Step 6），然后运行：

```bash
cd E:/Code/LifeOS/backend
uv sync
uv run pytest tests/test_time.py tests/test_health.py -v
```

预期：失败，原因是 `app.config` / `app.core.time` / `app.main` 等模块尚不存在。此时只完成了依赖与包骨架，业务实现留到 Step 6。

- [ ] **Step 6: 实现脚手架**

`backend/.python-version`：

```text
3.12
```

`backend/pyproject.toml`：

```toml
[project]
name = "lifeos-backend"
version = "0.2.0"
description = "LifeOS Python backend"
requires-python = ">=3.12,<3.13"
dependencies = [
    "fastapi>=0.115,<1.0",
    "uvicorn[standard]>=0.34,<1.0",
    "sqlalchemy[asyncio]>=2.0.36,<3.0",
    "aiomysql>=0.2.0,<1.0",
    "pymysql>=1.1.1,<2.0",
    "cryptography>=44.0.0",
    "alembic>=1.14,<2.0",
    "pydantic>=2.10,<3.0",
    "pydantic-settings>=2.7,<3.0",
    "httpx>=0.28,<1.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3,<9.0",
    "pytest-asyncio>=0.25,<1.0",
    "respx>=0.22,<1.0",
    "ruff>=0.9,<1.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 110
target-version = "py312"
```

`backend/app/__init__.py`、`backend/app/core/__init__.py`、`backend/app/services/__init__.py`、`backend/app/api/__init__.py`、`backend/app/api/routes/__init__.py`、`backend/tests/__init__.py`：空文件。

`backend/app/config.py`：

```python
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    lifeos_port: int = 8787
    lifeos_database_url: str
    lifeos_test_database_url: str | None = None
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    web_dist: str | None = None

    @property
    def safe_database_url(self) -> str:
        return make_url(self.lifeos_database_url).render_as_string(hide_password=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`backend/app/db.py`：

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_settings = get_settings()
engine = create_async_engine(
    _settings.lifeos_database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

`backend/app/core/time.py`：

```python
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("时间必须带时区")
    return value.astimezone(UTC).replace(tzinfo=None)


def to_iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def _local_tz():
    return datetime.now().astimezone().tzinfo


def to_day_key(value: datetime) -> str:
    local = value.astimezone(_local_tz())
    return f"{local.year:04d}-{local.month:02d}-{local.day:02d}"


def day_range(day_key: str) -> tuple[datetime, datetime]:
    year, month, day = (int(part) for part in day_key.split("-"))
    start = datetime(year, month, day, tzinfo=_local_tz())
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def month_range(month_key: str) -> tuple[datetime, datetime]:
    year, month = (int(part) for part in month_key.split("-"))
    start = datetime(year, month, 1, tzinfo=_local_tz())
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=_local_tz())
    else:
        end = datetime(year, month + 1, 1, tzinfo=_local_tz())
    return start.astimezone(UTC), end.astimezone(UTC)


def week_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(_local_tz())
    local = now.astimezone(_local_tz())
    monday_offset = local.weekday()  # Monday=0
    start_local = datetime(
        local.year, local.month, local.day, tzinfo=_local_tz()
    ) - timedelta(days=monday_offset)
    end_local = datetime(local.year, local.month, local.day, tzinfo=_local_tz()) + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def add_days(value: datetime, days: int) -> datetime:
    return value + timedelta(days=days)


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=1)


def to_date(value: datetime) -> date:
    return value.astimezone(_local_tz()).date()
```

`backend/app/services/insight.py`（本任务只放 `llm_status`）：

```python
from app.config import Settings


def llm_status(settings: Settings) -> dict[str, object]:
    return {
        "configured": bool(settings.llm_api_key),
        "model": settings.llm_model,
        "baseUrl": settings.llm_base_url,
    }
```

`backend/app/api/routes/health.py`：

```python
from fastapi import APIRouter, Request

from app.core.time import to_iso_z, utcnow
from app.services.insight import llm_status

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    return {
        "ok": True,
        "version": "0.2.0",
        "db": settings.safe_database_url,
        "llm": llm_status(settings),
        "now": to_iso_z(utcnow()),
    }
```

`backend/app/main.py`：

```python
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.config import Settings, get_settings
from app.db import engine


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
    app.include_router(health_router, prefix="/api")
    return app


app = create_app()
```

- [ ] **Step 7: 运行测试确认通过**

```bash
cd E:/Code/LifeOS/backend
uv sync
uv run pytest tests/test_time.py tests/test_health.py -v
uv run ruff check app tests
```

预期：全部 PASS，ruff 无错误。

- [ ] **Step 8: 提交**

```bash
cd E:/Code/LifeOS
git add backend .gitignore
git commit -m "feat(backend): 初始化 FastAPI 脚手架与健康检查

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 2: ORM 模型、Alembic 与测试数据库

**Files:**
- Create: `backend/app/models.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/0001_initial.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_schema.py`

**Interfaces:**
- Produces: `Base`, `Entry`, `AiInsight`；测试 fixture `db_engine`、`session`、`client`。
- Consumes: `app.config.Settings`（Task 1）。

- [ ] **Step 1: 写失败的 schema 测试**

创建 `backend/tests/test_schema.py`：

```python
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_tables_exist(db_engine: AsyncEngine):
    async with db_engine.connect() as conn:
        names = await conn.run_sync(lambda sync: inspect(sync).get_table_names())
    assert {"entries", "ai_insights"} <= set(names)


async def test_entries_columns_and_indexes(db_engine: AsyncEngine):
    async with db_engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync: {column["name"] for column in inspect(sync).get_columns("entries")}
        )
        indexes = await conn.run_sync(
            lambda sync: {index["name"] for index in inspect(sync).get_indexes("entries")}
        )

    assert {"id", "kind", "content", "occurred_at", "amount", "tags", "meta", "deleted_at"} <= columns
    assert {"idx_entries_occurred", "idx_entries_kind", "idx_entries_status"} <= indexes
```

运行确认失败：

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_schema.py -v
```

预期：失败，`db_engine` fixture 尚未定义。

- [ ] **Step 2: 创建 Alembic 骨架**

```bash
cd E:/Code/LifeOS/backend
uv run alembic init alembic
```

这会生成 `alembic.ini`、`alembic/env.py`、`alembic/script.py.mako` 和 `alembic/versions/`。保留生成的文件，下一步替换 `env.py` 并新增初始版本。

- [ ] **Step 3: 实现 ORM 模型**

`backend/app/models.py`：

```python
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CHAR, JSON, DECIMAL, Index, Integer, String, text
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(MEDIUMTEXT(), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(DECIMAL(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)
    mood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    energy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("(JSON_ARRAY())")
    )
    meta: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("(JSON_OBJECT())")
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    deleted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)


class AiInsight(Base):
    __tablename__ = "ai_insights"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)


Index("idx_entries_occurred", Entry.occurred_at.desc())
Index("idx_entries_kind", Entry.kind, Entry.occurred_at.desc())
Index("idx_entries_status", Entry.status, Entry.due_at)
Index("idx_insights_period", AiInsight.scope, AiInsight.period_start.desc())
```

- [ ] **Step 4: 实现 Alembic env 与初始迁移**

替换 `backend/alembic/env.py`：

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured and not configured.startswith("driver://"):
        return configured
    return get_settings().lifeos_database_url.replace("+aiomysql", "+pymysql")


config.set_main_option("sqlalchemy.url", _sync_url())
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

创建 `backend/alembic/versions/0001_initial.py`：

```python
"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entries",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("occurred_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("amount", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CNY"),
        sa.Column("category", sa.String(20), nullable=True),
        sa.Column("status", sa.String(10), nullable=True),
        sa.Column("due_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("mood", sa.Integer(), nullable=True),
        sa.Column("energy", sa.Integer(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("(JSON_ARRAY())")),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("(JSON_OBJECT())")),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.execute("CREATE INDEX idx_entries_occurred ON entries (occurred_at DESC)")
    op.execute("CREATE INDEX idx_entries_kind ON entries (kind, occurred_at DESC)")
    op.create_index("idx_entries_status", "entries", ["status", "due_at"])

    op.create_table(
        "ai_insights",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("period_start", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("period_end", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.execute("CREATE INDEX idx_insights_period ON ai_insights (scope, period_start DESC)")


def downgrade() -> None:
    op.drop_table("ai_insights")
    op.drop_table("entries")
```

- [ ] **Step 5: 实现测试 fixture**

`backend/tests/conftest.py`：

```python
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db import get_session
from app.main import create_app

_settings = get_settings()
TEST_URL = _settings.lifeos_test_database_url
if not TEST_URL:
    raise RuntimeError("LIFEOS_TEST_DATABASE_URL 未设置；测试必须使用独立测试库")

SYNC_TEST_URL = TEST_URL.replace("+aiomysql", "+pymysql")

test_engine = create_async_engine(TEST_URL, pool_pre_ping=True)
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
```

- [ ] **Step 6: 运行迁移与测试确认通过**

```bash
cd E:/Code/LifeOS/backend
uv run alembic upgrade head
uv run pytest tests/test_schema.py -v
uv run ruff check app tests alembic
```

预期：`alembic upgrade head` 成功；schema 测试 PASS；ruff 无错误。

注意：`alembic upgrade head` 使用 `.env` 中的 `LIFEOS_DATABASE_URL`（生产库 `lifeos`）。测试库由 `conftest.py` 自动迁移。

- [ ] **Step 7: 提交**

```bash
cd E:/Code/LifeOS
git add backend
git commit -m "feat(backend): 添加 MySQL ORM 模型与 Alembic 初始迁移

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 3: SQLite → MySQL 数据迁移

**Files:**
- Create: `backend/scripts/__init__.py`
- Create: `backend/scripts/migrate_sqlite_to_mysql.py`
- Create: `backend/tests/test_migration.py`

**Interfaces:**
- Produces: `parse_dt(value) -> datetime | None`、`load_sqlite(path) -> tuple[list[dict], list[dict]]`、`migrate(source, target_url, dry_run=False) -> tuple[int, int]`、`verify(source, target_url) -> bool`。
- Consumes: `Settings`（Task 1）、MySQL schema（Task 2）。

- [ ] **Step 1: 写失败的迁移测试**

`backend/tests/test_migration.py`：

```python
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from app.config import get_settings
from scripts.migrate_sqlite_to_mysql import migrate, verify

SOURCE_SCHEMA = """
CREATE TABLE entries (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, content TEXT NOT NULL, title TEXT,
  occurred_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  amount REAL, currency TEXT NOT NULL DEFAULT 'CNY', category TEXT, status TEXT,
  due_at TEXT, mood INTEGER, energy INTEGER, tags TEXT NOT NULL DEFAULT '[]',
  meta TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL DEFAULT 'manual', deleted_at TEXT
);
CREATE TABLE ai_insights (
  id TEXT PRIMARY KEY, scope TEXT NOT NULL, period_start TEXT NOT NULL,
  period_end TEXT NOT NULL, model TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


def make_source(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SOURCE_SCHEMA)
    conn.execute(
        "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "e1", "expense", "午饭 32", None,
            "2026-11-09T12:30:00+08:00", "2026-11-09T12:30:00+08:00", "2026-11-09T12:30:00+08:00",
            32, "CNY", "餐饮", None, None, None, None, '[]', '{}', "manual", None,
        ),
    )
    conn.execute(
        "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "e2", "journal", "深夜记录", None,
            "2026-11-09T14:00:00Z", "2026-11-09T14:00:00Z", "2026-11-09T14:00:00Z",
            None, "CNY", None, None, None, None, None, '["技术"]', '{}', "manual", None,
        ),
    )
    conn.execute(
        "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "e3", "todo", "已删除的待办", None,
            "2026-11-08T09:00:00+08:00", "2026-11-08T09:00:00+08:00", "2026-11-08T09:00:00+08:00",
            None, "CNY", None, "open", None, None, None, '[]', '{}', "manual",
            "2026-11-09T10:00:00+08:00",
        ),
    )
    conn.execute(
        "INSERT INTO ai_insights VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "i1", "daily", "2026-11-09T00:00:00+08:00", "2026-11-10T00:00:00+08:00",
            "local", '{"headline":"测试"}', "2026-11-09T10:00:00+08:00",
        ),
    )
    conn.commit()
    conn.close()


def test_migration_normalizes_time_and_is_idempotent(tmp_path: Path):
    source = tmp_path / "lifeos.db"
    make_source(source)
    target_url = get_settings().lifeos_test_database_url.replace("+aiomysql", "+pymysql")

    assert migrate(source, target_url) == (3, 1)
    assert migrate(source, target_url) == (3, 1)

    engine = create_engine(target_url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM entries")).scalar_one() == 3
        assert conn.execute(text("SELECT COUNT(*) FROM ai_insights")).scalar_one() == 1
        rows = conn.execute(text("SELECT id, occurred_at FROM entries ORDER BY id")).all()
        by_id = {row.id: row.occurred_at for row in rows}
        assert by_id["e1"] == datetime(2026, 11, 9, 4, 30, 0)
        assert by_id["e2"] == datetime(2026, 11, 9, 14, 0, 0)
        assert by_id["e3"] == datetime(2026, 11, 8, 1, 0, 0)

    assert verify(source, target_url) is True
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_migration.py -v
```

预期：失败，`scripts.migrate_sqlite_to_mysql` 不存在。

- [ ] **Step 3: 实现迁移脚本**

`backend/scripts/__init__.py`：空文件。

`backend/scripts/migrate_sqlite_to_mysql.py`：

```python
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text

from app.config import get_settings

ENTRY_COLUMNS = (
    "id", "kind", "content", "title", "occurred_at", "created_at", "updated_at",
    "amount", "currency", "category", "status", "due_at", "mood", "energy",
    "tags", "meta", "source", "deleted_at",
)

ENTRY_UPSERT = text(
    """
    INSERT INTO entries (id, kind, content, title, occurred_at, created_at, updated_at,
                         amount, currency, category, status, due_at, mood, energy,
                         tags, meta, source, deleted_at)
    VALUES (:id, :kind, :content, :title, :occurred_at, :created_at, :updated_at,
            :amount, :currency, :category, :status, :due_at, :mood, :energy,
            :tags, :meta, :source, :deleted_at)
    ON DUPLICATE KEY UPDATE
      kind=VALUES(kind), content=VALUES(content), title=VALUES(title),
      occurred_at=VALUES(occurred_at), created_at=VALUES(created_at),
      updated_at=VALUES(updated_at), amount=VALUES(amount), currency=VALUES(currency),
      category=VALUES(category), status=VALUES(status), due_at=VALUES(due_at),
      mood=VALUES(mood), energy=VALUES(energy), tags=VALUES(tags), meta=VALUES(meta),
      source=VALUES(source), deleted_at=VALUES(deleted_at)
    """
)

INSIGHT_UPSERT = text(
    """
    INSERT INTO ai_insights (id, scope, period_start, period_end, model, payload, created_at)
    VALUES (:id, :scope, :period_start, :period_end, :model, :payload, :created_at)
    ON DUPLICATE KEY UPDATE
      scope=VALUES(scope), period_start=VALUES(period_start), period_end=VALUES(period_end),
      model=VALUES(model), payload=VALUES(payload), created_at=VALUES(created_at)
    """
)


def parse_dt(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"时间缺少时区: {value}")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def parse_json(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def load_sqlite(path: Path) -> tuple[list[dict], list[dict]]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        entries = [dict(row) for row in conn.execute("SELECT * FROM entries")]
        insights = [dict(row) for row in conn.execute("SELECT * FROM ai_insights")]
    finally:
        conn.close()
    return entries, insights


def normalize_entry(row: dict) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "content": row["content"],
        "title": row.get("title"),
        "occurred_at": parse_dt(row["occurred_at"]),
        "created_at": parse_dt(row["created_at"]),
        "updated_at": parse_dt(row["updated_at"]),
        "amount": Decimal(str(row["amount"])) if row.get("amount") is not None else None,
        "currency": row.get("currency") or "CNY",
        "category": row.get("category"),
        "status": row.get("status"),
        "due_at": parse_dt(row.get("due_at")),
        "mood": row.get("mood"),
        "energy": row.get("energy"),
        "tags": json.dumps(parse_json(row.get("tags"), []), ensure_ascii=False),
        "meta": json.dumps(parse_json(row.get("meta"), {}), ensure_ascii=False),
        "source": row.get("source") or "manual",
        "deleted_at": parse_dt(row.get("deleted_at")),
    }


def normalize_insight(row: dict) -> dict:
    return {
        "id": row["id"],
        "scope": row["scope"],
        "period_start": parse_dt(row["period_start"]),
        "period_end": parse_dt(row["period_end"]),
        "model": row["model"],
        "payload": json.dumps(parse_json(row.get("payload"), {}), ensure_ascii=False),
        "created_at": parse_dt(row["created_at"]),
    }


def migrate(source: Path, target_url: str, dry_run: bool = False) -> tuple[int, int]:
    entries, insights = load_sqlite(source)
    if dry_run:
        print(f"[dry-run] entries={len(entries)} insights={len(insights)}")
        return len(entries), len(insights)

    engine = create_engine(target_url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            for row in entries:
                conn.execute(ENTRY_UPSERT, normalize_entry(row))
            for row in insights:
                conn.execute(INSIGHT_UPSERT, normalize_insight(row))
    finally:
        engine.dispose()
    print(f"已迁移 entries={len(entries)} insights={len(insights)}")
    return len(entries), len(insights)


def verify(source: Path, target_url: str) -> bool:
    entries, insights = load_sqlite(source)
    engine = create_engine(target_url, pool_pre_ping=True)
    ok = True
    try:
        with engine.connect() as conn:
            target_entries = conn.execute(text("SELECT COUNT(*) FROM entries")).scalar_one()
            target_insights = conn.execute(text("SELECT COUNT(*) FROM ai_insights")).scalar_one()
            source_kinds = Counter(row["kind"] for row in entries)
            target_kinds = dict(
                conn.execute(text("SELECT kind, COUNT(*) FROM entries GROUP BY kind")).all()
            )
            source_total = sum(
                Decimal(str(row["amount"]))
                for row in entries
                if row["kind"] == "expense" and row.get("amount") is not None
            )
            target_total = conn.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM entries WHERE kind = 'expense'")
            ).scalar_one()

            checks = [
                ("entries count", len(entries), target_entries),
                ("insights count", len(insights), target_insights),
                ("kind counts", dict(source_kinds), target_kinds),
                ("expense total", source_total, Decimal(str(target_total))),
            ]
            for label, expected, actual in checks:
                matched = expected == actual
                ok = ok and matched
                print(f"{'OK ' if matched else 'FAIL'} {label}: source={expected} target={actual}")
    finally:
        engine.dispose()
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="把 data/lifeos.db 迁移到 MySQL")
    parser.add_argument("--sqlite", default="data/lifeos.db", help="SQLite 文件路径（相对仓库根目录）")
    parser.add_argument("--database-url", default=None, help="目标 MySQL URL；默认取 .env")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    parser.add_argument("--verify", action="store_true", help="迁移后逐表核对")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / args.sqlite).resolve()
    if not source.exists():
        raise SystemExit(f"找不到 SQLite 文件: {source}")

    target = args.database_url or get_settings().lifeos_database_url.replace("+aiomysql", "+pymysql")
    migrate(source, target, dry_run=args.dry_run)
    if args.verify and not args.dry_run:
        if not verify(source, target):
            sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_migration.py -v
uv run ruff check scripts tests
```

预期：迁移测试 PASS；ruff 无错误。

- [ ] **Step 5: 对真实数据执行迁移并核对**

```bash
cd E:/Code/LifeOS/backend
uv run python scripts/migrate_sqlite_to_mysql.py --dry-run
uv run python scripts/migrate_sqlite_to_mysql.py --verify
```

预期：`--dry-run` 报告 `entries=28 insights=13`；`--verify` 四项全部 `OK`，退出码 0。

- [ ] **Step 6: 提交**

```bash
cd E:/Code/LifeOS
git add backend
git commit -m "feat(backend): 添加 SQLite 到 MySQL 的数据迁移脚本

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 4: Pydantic 契约与仓储层

**Files:**
- Create: `backend/app/schemas.py`
- Create: `backend/app/repositories/__init__.py`
- Create: `backend/app/repositories/entries.py`
- Create: `backend/app/repositories/insights.py`
- Create: `backend/tests/test_repositories_entries.py`

**Interfaces:**
- Produces: `EntryCreate`、`EntryPatch`、`EntryRead`、`EntryListResponse`、`ListQuery`、`Stats`、`Insight`、`CaptureRequest`、`CaptureParsed`、`CaptureResponse`、`InsightResponse`；仓储函数 `create_entry`、`get_entry`、`update_entry`、`delete_entry`、`list_entries`、`entries_in_range`、`save_insight`、`latest_insight`。
- Consumes: `Entry`、`AiInsight`（Task 2）、`to_utc_naive`、`utcnow`（Task 1）。

- [ ] **Step 1: 写仓储层失败的测试**

`backend/tests/test_repositories_entries.py`：

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.entries import (
    create_entry,
    delete_entry,
    get_entry,
    list_entries,
    update_entry,
)
from app.schemas import EntryCreate, EntryPatch, ListQuery

UTC = timezone.utc


def make_entry(**overrides) -> EntryCreate:
    data = {
        "kind": "journal",
        "content": "测试记录",
        "occurred_at": datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        "tags": [],
    }
    data.update(overrides)
    return EntryCreate(**data)


async def test_create_and_get_entry(session: AsyncSession):
    entry = await create_entry(session, make_entry())
    await session.commit()

    fetched = await get_entry(session, entry.id)
    assert fetched is not None
    assert fetched.content == "测试记录"
    assert fetched.occurred_at == datetime(2026, 11, 9, 12, 0)


async def test_patch_keeps_missing_fields_and_sets_explicit_null(session: AsyncSession):
    entry = await create_entry(
        session,
        make_entry(title="标题", category="餐饮", amount=32, kind="expense"),
    )
    await session.commit()

    await update_entry(session, entry.id, EntryPatch(content="只改内容"))
    await session.commit()
    fetched = await get_entry(session, entry.id)
    assert fetched is not None
    assert fetched.content == "只改内容"
    assert fetched.title == "标题"
    assert fetched.category == "餐饮"
    assert float(fetched.amount) == 32.0

    await update_entry(session, entry.id, EntryPatch(title=None, amount=None, category=None))
    await session.commit()
    fetched = await get_entry(session, entry.id)
    assert fetched is not None
    assert fetched.title is None
    assert fetched.amount is None
    assert fetched.category is None


async def test_soft_delete_hides_entry(session: AsyncSession):
    entry = await create_entry(session, make_entry())
    await session.commit()

    assert await delete_entry(session, entry.id) is True
    await session.commit()

    assert await get_entry(session, entry.id) is None
    items = await list_entries(session, ListQuery())
    assert items == []


async def test_list_orders_by_utc_not_string(session: AsyncSession):
    earlier = await create_entry(
        session,
        make_entry(
            content="earlier",
            occurred_at=datetime(2026, 11, 9, 9, 0, tzinfo=timezone(timedelta(hours=8))),
        ),
    )
    later = await create_entry(
        session,
        make_entry(content="later", occurred_at=datetime(2026, 11, 9, 1, 30, tzinfo=UTC)),
    )
    await session.commit()

    items = await list_entries(session, ListQuery())
    assert [item.id for item in items] == [later.id, earlier.id]


async def test_tag_filter_matches_chinese_tag(session: AsyncSession):
    tagged = await create_entry(session, make_entry(content="产品想法", tags=["产品", "灵感"]))
    await create_entry(session, make_entry(content="别的记录", tags=["生活"]))
    await session.commit()

    items = await list_entries(session, ListQuery(tag="产品"))
    assert [item.id for item in items] == [tagged.id]


async def test_list_filters_and_pagination(session: AsyncSession):
    for index in range(3):
        await create_entry(
            session,
            make_entry(
                kind="expense",
                content=f"午饭 {index}",
                amount=index + 1,
                category="餐饮",
                occurred_at=datetime(2026, 11, 9, 12, index, tzinfo=UTC),
            ),
        )
    await session.commit()

    first = await list_entries(session, ListQuery(kind="expense", limit=2, offset=0))
    second = await list_entries(session, ListQuery(kind="expense", limit=2, offset=2))
    assert len(first) == 2
    assert len(second) == 1
    assert all(item.kind == "expense" for item in first + second)

    searched = await list_entries(session, ListQuery(q="午饭 1"))
    assert len(searched) == 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_repositories_entries.py -v
```

预期：失败，`app.schemas` 或仓储模块不存在。

- [ ] **Step 3: 实现 Pydantic 契约**

`backend/app/schemas.py`：

```python
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    model_validator,
)

from app.core.time import to_iso_z

Kind = Literal["journal", "thought", "expense", "todo", "habit", "metric"]
TodoStatus = Literal["open", "done", "dropped"]
Source = Literal["manual", "capture", "import", "api"]


def to_camel(value: str) -> str:
    head, *rest = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        protected_namespaces=(),
    )


Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Title = Annotated[str, StringConstraints(max_length=200)]


class EntryCreate(CamelModel):
    kind: Kind
    content: Content
    occurred_at: AwareDatetime | None = None
    title: Title | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    category: str | None = Field(default=None, max_length=20)
    status: TodoStatus | None = None
    due_at: AwareDatetime | None = None
    mood: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=5)
    tags: list[Tag] = Field(default_factory=list, max_length=20)
    meta: dict[str, Any] = Field(default_factory=dict)
    source: Source = "manual"


class EntryPatch(CamelModel):
    kind: Kind | None = None
    content: Content | None = None
    occurred_at: AwareDatetime | None = None
    title: Title | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    category: str | None = Field(default=None, max_length=20)
    status: TodoStatus | None = None
    due_at: AwareDatetime | None = None
    mood: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=5)
    tags: list[Tag] | None = Field(default=None, max_length=20)
    meta: dict[str, Any] | None = None

    @model_validator(mode="after")
    def reject_null_for_non_nullable_fields(self) -> EntryPatch:
        non_nullable = {"kind", "content", "occurred_at", "currency", "tags", "meta"}
        for field_name in non_nullable:
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} 不能为 null")
        return self


class EntryRead(CamelModel):
    id: str
    kind: Kind
    content: str
    title: str | None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime
    amount: float | None
    currency: str
    category: str | None
    status: TodoStatus | None
    due_at: datetime | None
    mood: int | None
    energy: int | None
    tags: list[str]
    meta: dict[str, Any]
    source: Source

    @field_serializer("occurred_at", "created_at", "updated_at", "due_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        return to_iso_z(value) if value is not None else None


class EntryListResponse(CamelModel):
    items: list[EntryRead]
    count: int


class ListQuery(BaseModel):
    from_: AwareDatetime | None = None
    to: AwareDatetime | None = None
    kind: Kind | None = None
    status: TodoStatus | None = None
    q: str | None = None
    tag: str | None = None
    limit: int = 500
    offset: int = 0


class CategoryTotal(CamelModel):
    category: str
    total: float
    count: int


class Stats(CamelModel):
    from_: datetime = Field(alias="from")
    to: datetime
    total_spent: float
    by_category: list[CategoryTotal]
    by_kind: dict[str, int]
    open_todos: int
    done_todos: int
    avg_mood: float | None
    entry_count: int

    @field_serializer("from_", "to")
    def serialize_datetime(self, value: datetime) -> str:
        return to_iso_z(value)


class Insight(CamelModel):
    scope: Literal["daily", "weekly"]
    from_: datetime = Field(alias="from")
    to: datetime
    headline: str
    summary: str
    themes: list[str]
    spending: str
    todos: str
    mood: Literal["up", "flat", "down", "unknown"]
    suggestion: str
    model: str
    generated_at: datetime

    @field_serializer("from_", "to", "generated_at")
    def serialize_datetime(self, value: datetime) -> str:
        return to_iso_z(value)


class CaptureRequest(CamelModel):
    text: Content
    at: AwareDatetime | None = None


class CaptureParsed(CamelModel):
    kind: Kind
    content: str
    tags: list[str]
    amount: float | None
    category: str | None
    due_at: datetime | None
    status: Literal["open"] | None
    confidence: float
    note: str

    @field_serializer("due_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        return to_iso_z(value) if value is not None else None


class CaptureResponse(CamelModel):
    entry: EntryRead
    parsed: CaptureParsed


class InsightResponse(CamelModel):
    insight: Insight
    warning: str | None
    stats: Stats
```

- [ ] **Step 4: 实现仓储层**

`backend/app/repositories/__init__.py`：空文件。

`backend/app/repositories/entries.py`：

```python
from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import to_utc_naive, utcnow
from app.models import Entry
from app.schemas import EntryCreate, EntryPatch, ListQuery

DATETIME_FIELDS = {"occurred_at", "due_at"}


async def create_entry(session: AsyncSession, data: EntryCreate) -> Entry:
    now = utcnow()
    entry = Entry(
        id=str(uuid4()),
        kind=data.kind,
        content=data.content,
        title=data.title,
        occurred_at=to_utc_naive(data.occurred_at) if data.occurred_at else to_utc_naive(now),
        created_at=to_utc_naive(now),
        updated_at=to_utc_naive(now),
        amount=data.amount,
        currency=data.currency,
        category=data.category,
        status=data.status or ("open" if data.kind == "todo" else None),
        due_at=to_utc_naive(data.due_at) if data.due_at else None,
        mood=data.mood,
        energy=data.energy,
        tags=data.tags,
        meta=data.meta,
        source=data.source,
        deleted_at=None,
    )
    session.add(entry)
    await session.flush()
    return entry


async def get_entry(session: AsyncSession, entry_id: str) -> Entry | None:
    result = await session.execute(
        select(Entry).where(Entry.id == entry_id, Entry.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def update_entry(session: AsyncSession, entry_id: str, patch: EntryPatch) -> Entry | None:
    entry = await get_entry(session, entry_id)
    if entry is None:
        return None

    for field_name in patch.model_fields_set:
        value = getattr(patch, field_name)
        if field_name in DATETIME_FIELDS and value is not None:
            value = to_utc_naive(value)
        setattr(entry, field_name, value)

    entry.updated_at = to_utc_naive(utcnow())
    await session.flush()
    return entry


async def delete_entry(session: AsyncSession, entry_id: str) -> bool:
    entry = await get_entry(session, entry_id)
    if entry is None:
        return False
    now = to_utc_naive(utcnow())
    entry.deleted_at = now
    entry.updated_at = now
    await session.flush()
    return True


async def list_entries(session: AsyncSession, query: ListQuery) -> list[Entry]:
    stmt = select(Entry).where(Entry.deleted_at.is_(None))
    if query.from_ is not None:
        stmt = stmt.where(Entry.occurred_at >= to_utc_naive(query.from_))
    if query.to is not None:
        stmt = stmt.where(Entry.occurred_at < to_utc_naive(query.to))
    if query.kind is not None:
        stmt = stmt.where(Entry.kind == query.kind)
    if query.status is not None:
        stmt = stmt.where(Entry.status == query.status)
    if query.q:
        stmt = stmt.where(Entry.content.like(f"%{query.q}%"))
    if query.tag:
        stmt = stmt.where(func.json_contains(Entry.tags, json.dumps(query.tag, ensure_ascii=False)))
    stmt = stmt.order_by(Entry.occurred_at.desc()).limit(query.limit).offset(query.offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def entries_in_range(session: AsyncSession, from_: datetime, to: datetime) -> list[Entry]:
    result = await session.execute(
        select(Entry)
        .where(
            Entry.deleted_at.is_(None),
            Entry.occurred_at >= to_utc_naive(from_),
            Entry.occurred_at < to_utc_naive(to),
        )
        .order_by(Entry.occurred_at.desc())
    )
    return list(result.scalars().all())
```

`backend/app/repositories/insights.py`：

```python
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import to_utc_naive, utcnow
from app.models import AiInsight
from app.schemas import Insight


async def save_insight(session: AsyncSession, insight: Insight) -> AiInsight:
    row = AiInsight(
        id=str(uuid4()),
        scope=insight.scope,
        period_start=to_utc_naive(insight.from_),
        period_end=to_utc_naive(insight.to),
        model=insight.model,
        payload=insight.model_dump(mode="json", by_alias=True),
        created_at=to_utc_naive(utcnow()),
    )
    session.add(row)
    await session.flush()
    return row


async def latest_insight(session: AsyncSession, scope: str) -> dict | None:
    result = await session.execute(
        select(AiInsight)
        .where(AiInsight.scope == scope)
        .order_by(AiInsight.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row.payload if row is not None else None
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_repositories_entries.py -v
uv run ruff check app tests
```

预期：全部 PASS，ruff 无错误。

- [ ] **Step 6: 提交**

```bash
cd E:/Code/LifeOS
git add backend
git commit -m "feat(backend): 添加 Pydantic 契约与记录仓储层

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 5: 读接口 entries / stats 与统计聚合

**Files:**
- Create: `backend/app/services/stats.py`
- Create: `backend/app/api/deps.py`
- Create: `backend/app/api/routes/entries.py`
- Create: `backend/app/api/routes/stats.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_api_entries_read.py`
- Create: `backend/tests/test_api_stats.py`

**Interfaces:**
- Produces: `compute_stats(entries, from_, to) -> Stats`；`GET /api/entries`、`GET /api/entries/{id}`、`GET /api/stats`。
- Consumes: 仓储层（Task 4）、`EntryRead`、`Stats`（Task 4）。

- [ ] **Step 1: 写读接口失败的测试**

`backend/tests/test_api_entries_read.py`：

```python
import re
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.entries import create_entry, delete_entry
from app.schemas import EntryCreate

UTC = timezone.utc
ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def seed(session: AsyncSession, **overrides):
    data = {
        "kind": "journal",
        "content": "测试记录",
        "occurred_at": datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        "tags": [],
    }
    data.update(overrides)
    entry = await create_entry(session, EntryCreate(**data))
    await session.commit()
    return entry


async def test_list_entries_contract(client: AsyncClient, session: AsyncSession):
    entry = await seed(session, tags=["产品"])
    response = await client.get("/api/entries")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    item = body["items"][0]
    assert item["id"] == entry.id
    assert item["occurredAt"].endswith("Z")
    assert ISO_Z.match(item["occurredAt"])
    assert set(item) == {
        "id", "kind", "content", "title", "occurredAt", "createdAt", "updatedAt",
        "amount", "currency", "category", "status", "dueAt", "mood", "energy",
        "tags", "meta", "source",
    }
    assert item["tags"] == ["产品"]


async def test_list_filters(client: AsyncClient, session: AsyncSession):
    await seed(session, kind="expense", content="午饭 32", amount=32, category="餐饮")
    await seed(session, kind="todo", content="交房租", status="open")
    await seed(session, kind="journal", content="今天很累", tags=["情绪"])

    expense = await client.get("/api/entries?kind=expense")
    assert expense.json()["count"] == 1

    search = await client.get("/api/entries?q=房租")
    assert search.json()["count"] == 1

    tag = await client.get("/api/entries?tag=情绪")
    assert tag.json()["count"] == 1

    paged = await client.get("/api/entries?limit=2&offset=2")
    assert paged.json()["count"] == 1


async def test_get_entry_and_404(client: AsyncClient, session: AsyncSession):
    entry = await seed(session)

    found = await client.get(f"/api/entries/{entry.id}")
    assert found.status_code == 200
    assert found.json()["id"] == entry.id

    missing = await client.get("/api/entries/not-exists")
    assert missing.status_code == 404
    assert missing.json() == {"error": "记录不存在"}


async def test_soft_deleted_entry_is_hidden(client: AsyncClient, session: AsyncSession):
    entry = await seed(session)
    await delete_entry(session, entry.id)
    await session.commit()

    listing = await client.get("/api/entries")
    assert listing.json()["count"] == 0

    detail = await client.get(f"/api/entries/{entry.id}")
    assert detail.status_code == 404
```

`backend/tests/test_api_stats.py`：

```python
import re
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.entries import create_entry
from app.schemas import EntryCreate

UTC = timezone.utc
ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def test_stats_aggregates_and_serializes(client: AsyncClient, session: AsyncSession):
    rows = [
        dict(kind="expense", content="午饭", amount=32, category="餐饮", mood=4),
        dict(kind="expense", content="咖啡", amount=18, category="餐饮", mood=2),
        dict(kind="expense", content="打车", amount=48, category="交通"),
        dict(kind="todo", content="写周报", status="done"),
        dict(kind="todo", content="交房租", status="open"),
        dict(kind="journal", content="今天还不错"),
    ]
    for row in rows:
        await create_entry(
            session,
            EntryCreate(occurred_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC), **row),
        )
    await session.commit()

    response = await client.get(
        "/api/stats?from=2026-11-09T00:00:00.000Z&to=2026-11-10T00:00:00.000Z"
    )
    assert response.status_code == 200
    body = response.json()

    assert body["totalSpent"] == 98.0
    assert body["entryCount"] == 6
    assert body["openTodos"] == 1
    assert body["doneTodos"] == 1
    assert body["avgMood"] == 3.0
    assert body["byKind"] == {"expense": 3, "todo": 2, "journal": 1}
    assert body["byCategory"][0] == {"category": "餐饮", "total": 50.0, "count": 2}
    assert body["byCategory"][1] == {"category": "交通", "total": 48.0, "count": 1}
    assert ISO_Z.match(body["from"])
    assert ISO_Z.match(body["to"])


async def test_stats_excludes_soft_deleted(client: AsyncClient, session: AsyncSession):
    from app.repositories.entries import delete_entry

    entry = await create_entry(
        session,
        EntryCreate(
            kind="expense",
            content="午饭",
            amount=32,
            category="餐饮",
            occurred_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        ),
    )
    await session.commit()
    await delete_entry(session, entry.id)
    await session.commit()

    response = await client.get(
        "/api/stats?from=2026-11-09T00:00:00.000Z&to=2026-11-10T00:00:00.000Z"
    )
    assert response.json()["entryCount"] == 0
    assert response.json()["totalSpent"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_api_entries_read.py tests/test_api_stats.py -v
```

预期：失败，路由/服务尚不存在。

- [ ] **Step 3: 实现统计服务**

`backend/app/services/stats.py`：

```python
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.models import Entry
from app.schemas import CategoryTotal, Stats


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_stats(entries: list[Entry], from_: datetime, to: datetime) -> Stats:
    by_kind: Counter[str] = Counter()
    by_category: dict[str, dict[str, Decimal | int]] = {}
    total_spent = Decimal("0")
    open_todos = 0
    done_todos = 0
    mood_sum = 0
    mood_count = 0

    for entry in entries:
        by_kind[entry.kind] += 1
        if entry.kind == "expense":
            amount = entry.amount or Decimal("0")
            total_spent += amount
            key = entry.category or "其他"
            bucket = by_category.setdefault(key, {"total": Decimal("0"), "count": 0})
            bucket["total"] = bucket["total"] + amount
            bucket["count"] = int(bucket["count"]) + 1
        if entry.kind == "todo":
            if entry.status == "done":
                done_todos += 1
            elif entry.status == "open":
                open_todos += 1
        if entry.mood is not None:
            mood_sum += entry.mood
            mood_count += 1

    categories = [
        CategoryTotal(
            category=category,
            total=float(_money(bucket["total"])),
            count=int(bucket["count"]),
        )
        for category, bucket in by_category.items()
    ]
    categories.sort(key=lambda item: item.total, reverse=True)

    avg_mood = None
    if mood_count:
        avg_mood = float(
            (Decimal(mood_sum) / Decimal(mood_count)).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
        )

    return Stats(
        from_=from_,
        to=to,
        total_spent=float(_money(total_spent)),
        by_category=categories,
        by_kind=dict(by_kind),
        open_todos=open_todos,
        done_todos=done_todos,
        avg_mood=avg_mood,
        entry_count=len(entries),
    )
```

- [ ] **Step 4: 实现路由并注册**

`backend/app/api/deps.py`：

```python
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
```

`backend/app/api/routes/entries.py`：

```python
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import AwareDatetime

from app.api.deps import SessionDep
from app.repositories.entries import get_entry, list_entries
from app.schemas import EntryListResponse, EntryRead, Kind, ListQuery, TodoStatus

router = APIRouter(prefix="/entries", tags=["entries"])


@router.get("", response_model=EntryListResponse)
async def list_entries_route(
    session: SessionDep,
    from_: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    to: Annotated[AwareDatetime | None, Query()] = None,
    kind: Annotated[Kind | None, Query()] = None,
    status: Annotated[TodoStatus | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    tag: Annotated[str | None, Query(max_length=30)] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EntryListResponse:
    query = ListQuery(
        from_=from_,
        to=to,
        kind=kind,
        status=status,
        q=q,
        tag=tag,
        limit=limit,
        offset=offset,
    )
    items = await list_entries(session, query)
    return EntryListResponse(
        items=[EntryRead.model_validate(item) for item in items],
        count=len(items),
    )


@router.get("/{entry_id}", response_model=EntryRead)
async def get_entry_route(entry_id: str, session: SessionDep) -> EntryRead:
    entry = await get_entry(session, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return EntryRead.model_validate(entry)
```

`backend/app/api/routes/stats.py`：

```python
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.api.deps import SessionDep
from app.repositories.entries import entries_in_range
from app.schemas import Stats
from app.services.stats import compute_stats

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=Stats)
async def stats_route(
    session: SessionDep,
    from_: Annotated[AwareDatetime, Query(alias="from")],
    to: Annotated[AwareDatetime, Query()],
) -> Stats:
    entries = await entries_in_range(session, from_, to)
    return compute_stats(entries, from_, to)
```

修改 `backend/app/main.py`：在导入区加入

```python
from app.api.routes.entries import router as entries_router
from app.api.routes.stats import router as stats_router
```

在 `app.include_router(health_router, prefix="/api")` 后加入：

```python
    app.include_router(entries_router, prefix="/api")
    app.include_router(stats_router, prefix="/api")
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_api_entries_read.py tests/test_api_stats.py -v
uv run ruff check app tests
```

预期：全部 PASS，ruff 无错误。

- [ ] **Step 6: 提交**

```bash
cd E:/Code/LifeOS
git add backend
git commit -m "feat(backend): 添加 entries 与 stats 读接口

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 6: 写接口、校验错误映射与删除

**Files:**
- Create: `backend/app/core/errors.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/routes/entries.py`
- Create: `backend/tests/test_api_entries_write.py`

**Interfaces:**
- Produces: `POST /api/entries`、`PATCH /api/entries/{id}`、`DELETE /api/entries/{id}`；统一 400 校验错误格式。
- Consumes: 仓储层（Task 4）、`EntryCreate`、`EntryPatch`（Task 4）。

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_api_entries_write.py`：

```python
import re

from httpx import AsyncClient

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def create_sample(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/entries",
        json={
            "kind": "expense",
            "content": "午饭 32 元",
            "occurredAt": "2026-11-09T12:30:00.000+08:00",
            "amount": 32,
            "category": "餐饮",
            "title": "工作日午餐",
            "tags": ["工作餐"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_entry_returns_201_and_contract(client: AsyncClient):
    body = await create_sample(client)

    assert body["kind"] == "expense"
    assert body["content"] == "午饭 32 元"
    assert body["amount"] == 32.0
    assert body["category"] == "餐饮"
    assert body["source"] == "manual"
    assert body["occurredAt"] == "2026-11-09T04:30:00.000Z"
    assert ISO_Z.match(body["createdAt"])
    assert ISO_Z.match(body["updatedAt"])


async def test_patch_keeps_omitted_fields_and_clears_explicit_null(client: AsyncClient):
    created = await create_sample(client)
    entry_id = created["id"]

    patched = await client.patch(f"/api/entries/{entry_id}", json={"content": "晚饭 32 元"})
    assert patched.status_code == 200
    body = patched.json()
    assert body["content"] == "晚饭 32 元"
    assert body["title"] == "工作日午餐"
    assert body["amount"] == 32.0
    assert body["category"] == "餐饮"

    cleared = await client.patch(
        f"/api/entries/{entry_id}",
        json={"title": None, "amount": None, "category": None},
    )
    assert cleared.status_code == 200
    body = cleared.json()
    assert body["title"] is None
    assert body["amount"] is None
    assert body["category"] is None
    assert body["content"] == "晚饭 32 元"


async def test_patch_rejects_null_for_non_nullable_fields(client: AsyncClient):
    created = await create_sample(client)

    response = await client.patch(f"/api/entries/{created['id']}", json={"occurredAt": None})
    assert response.status_code == 400
    assert response.json()["error"] == "参数不合法"

    response = await client.patch(f"/api/entries/{created['id']}", json={"tags": None})
    assert response.status_code == 400


async def test_validation_error_format(client: AsyncClient):
    response = await client.post("/api/entries", json={})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "参数不合法"
    assert "content" in body["detail"]


async def test_delete_returns_204_then_404(client: AsyncClient):
    created = await create_sample(client)

    deleted = await client.delete(f"/api/entries/{created['id']}")
    assert deleted.status_code == 204
    assert deleted.content == b""

    again = await client.delete(f"/api/entries/{created['id']}")
    assert again.status_code == 404
    assert again.json() == {"error": "记录不存在"}


async def test_stats_missing_range_returns_400(client: AsyncClient):
    response = await client.get("/api/stats")
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "参数不合法"
    assert "from" in body["detail"] or "to" in body["detail"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_api_entries_write.py -v
```

预期：失败，写接口与错误处理器尚不存在。

- [ ] **Step 3: 实现错误格式化与处理器**

`backend/app/core/errors.py`：

```python
from fastapi.exceptions import RequestValidationError


def format_validation_detail(exc: RequestValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        location = [
            str(item)
            for item in error.get("loc", ())
            if item not in ("body", "query", "path")
        ]
        field = ".".join(location) or "参数"
        parts.append(f"{field}：{error.get('msg', '不合法')}")
    return "；".join(parts)
```

修改 `backend/app/main.py`：

```python
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

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
    app.include_router(stats_router, prefix="/api")
    return app


app = create_app()
```

- [ ] **Step 4: 实现写接口**

在 `backend/app/api/routes/entries.py` 中把导入改成：

```python
from app.repositories.entries import (
    create_entry as repo_create_entry,
    delete_entry as repo_delete_entry,
    get_entry,
    list_entries,
    update_entry as repo_update_entry,
)
from app.schemas import (
    EntryCreate,
    EntryListResponse,
    EntryPatch,
    EntryRead,
    Kind,
    ListQuery,
    TodoStatus,
)
```

在文件末尾追加：

```python
@router.post("", response_model=EntryRead, status_code=201)
async def create_entry_route(payload: EntryCreate, session: SessionDep) -> EntryRead:
    entry = await repo_create_entry(session, payload)
    return EntryRead.model_validate(entry)


@router.patch("/{entry_id}", response_model=EntryRead)
async def update_entry_route(
    entry_id: str, payload: EntryPatch, session: SessionDep
) -> EntryRead:
    entry = await repo_update_entry(session, entry_id, payload)
    if entry is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return EntryRead.model_validate(entry)


@router.delete("/{entry_id}", status_code=204)
async def delete_entry_route(entry_id: str, session: SessionDep) -> None:
    if not await repo_delete_entry(session, entry_id):
        raise HTTPException(status_code=404, detail="记录不存在")
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_api_entries_write.py -v
uv run pytest -q
uv run ruff check app tests
```

预期：写接口测试 PASS，已有测试不回归，ruff 无错误。

- [ ] **Step 6: 提交**

```bash
cd E:/Code/LifeOS
git add backend
git commit -m "feat(backend): 添加记录写接口与统一错误格式

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 7: 快速捕捉解析器与 capture 接口

**Files:**
- Create: `backend/app/services/capture.py`
- Create: `backend/app/api/routes/capture.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_capture.py`
- Create: `backend/tests/test_api_capture.py`

**Interfaces:**
- Produces: `CaptureResult`、`DueDate`、`parse_capture(text, now) -> CaptureResult`、`parse_due_date(text, now) -> DueDate | None`；`POST /api/capture`。
- Consumes: `EntryCreate`、`CaptureRequest`、`CaptureParsed`、`CaptureResponse`（Task 4）、仓储层（Task 4）。

- [ ] **Step 1: 写解析器失败的测试**

`backend/tests/test_capture.py`：

```python
from datetime import datetime, timedelta, timezone

from app.services.capture import parse_capture, parse_due_date

NOW = datetime(2026, 11, 9, 15, 30, tzinfo=timezone(timedelta(hours=8)))  # 周一


def test_amount_with_unit_becomes_expense_and_category():
    result = parse_capture("午饭 32 元和同事", NOW)
    assert result.kind == "expense"
    assert result.amount == 32
    assert result.category == "餐饮"
    assert result.confidence > 0.9


def test_currency_symbol():
    result = parse_capture("打车 ¥48.5", NOW)
    assert result.kind == "expense"
    assert result.amount == 48.5
    assert result.category == "交通"


def test_wan_amount():
    result = parse_capture("交房租 1.2万", NOW)
    assert result.kind == "expense"
    assert result.amount == 12000
    assert result.category == "住房"


def test_number_plus_category_word():
    result = parse_capture("咖啡 25", NOW)
    assert result.kind == "expense"
    assert result.amount == 25


def test_explicit_prefix_wins():
    result = parse_capture("闪念：今天想到一个点子，关于记账 20 元的事", NOW)
    assert result.kind == "thought"
    assert result.amount is None


def test_reminder_becomes_todo_and_parses_tomorrow():
    result = parse_capture("记得明天交房租", NOW)
    assert result.kind == "todo"
    assert result.status == "open"
    assert result.due_at is not None
    assert result.due_at.day == 10


def test_daily_reflection_is_not_expense():
    result = parse_capture("今天天气很好，突然觉得该慢一点", NOW)
    assert result.kind != "expense"
    assert result.amount is None


def test_long_text_becomes_journal():
    result = parse_capture(
        "今天下午开了三个会，脑子有点糊。回来的路上一直在想那个架构问题，"
        "后来在地铁上突然想通了：其实不需要同步层，服务端就是唯一真相。",
        NOW,
    )
    assert result.kind == "journal"


def test_tags_are_extracted_and_removed():
    result = parse_capture("想到一个装修的点子 #装修 #灵感", NOW)
    assert result.tags == ["装修", "灵感"]
    assert "#" not in result.content


def test_due_date_month_day():
    due = parse_due_date("11月20日交房租", NOW)
    assert due is not None
    assert due.due_at.month == 11
    assert due.due_at.day == 20


def test_due_date_weekday_and_next_week():
    this_week = parse_due_date("周三开会", NOW)
    next_week = parse_due_date("下周三开会", NOW)
    assert this_week is not None
    assert next_week is not None
    assert this_week.due_at.weekday() == 2
    assert next_week.due_at.weekday() == 2
    assert next_week.due_at > this_week.due_at


def test_clock_time_is_not_amount():
    result = parse_capture("今天 3点 开会", NOW)
    assert result.kind != "expense"
    assert result.amount is None


def test_bare_number_is_expense():
    result = parse_capture("32", NOW)
    assert result.kind == "expense"
    assert result.amount == 32


def test_chinese_tags_and_deduplication():
    result = parse_capture("产品想法 #产品 #产品 #灵感", NOW)
    assert result.tags == ["产品", "灵感"]


def test_todo_prefix_strips_prefix():
    result = parse_capture("todo: 预约牙医", NOW)
    assert result.kind == "todo"
    assert result.content == "预约牙医"


def test_expense_note_is_human_readable():
    result = parse_capture("午饭 32 元", NOW)
    assert result.note == "记录为支出 ¥32 · 餐饮"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_capture.py -v
```

预期：失败，`app.services.capture` 不存在。

- [ ] **Step 3: 实现解析器**

`backend/app/services/capture.py`：

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.schemas import Kind

Category = Literal["餐饮", "交通", "购物", "住房", "娱乐", "医疗", "学习", "其他"]

PREFIXES: list[tuple[re.Pattern[str], Kind]] = [
    (re.compile(r"^(?:todo|todos|task|待办|任务|要做)\s*[:：]\s*", re.IGNORECASE), "todo"),
    (re.compile(r"^(?:支出|记账|花费|消费|花了)\s*[:：]\s*"), "expense"),
    (re.compile(r"^(?:日记|日志)\s*[:：]\s*"), "journal"),
    (re.compile(r"^(?:闪念|想法|念头|灵感)\s*[:：]\s*"), "thought"),
]

CATEGORY_KEYWORDS: list[tuple[Category, list[str]]] = [
    ("餐饮", [
        "吃", "饭", "早餐", "午餐", "晚餐", "午饭", "晚饭", "夜宵", "宵夜", "咖啡",
        "奶茶", "外卖", "火锅", "烧烤", "面条", "米粉", "包子", "零食", "水果", "食堂",
        "饮料", "可乐", "啤酒", "聚餐", "下馆子",
    ]),
    ("交通", [
        "打车", "地铁", "公交", "高铁", "火车票", "机票", "加油", "停车", "滴滴",
        "单车", "油费", "过路费", "车票", "网约车", "高速",
    ]),
    ("住房", ["房租", "水电", "电费", "水费", "物业", "宽带", "燃气", "暖气", "装修"]),
    ("医疗", ["医院", "看病", "药", "挂号", "体检", "牙", "诊所", "疫苗", "医保"]),
    ("学习", ["书", "课程", "学费", "培训", "考试", "网课", "教材", "证书", "报班"]),
    ("娱乐", [
        "电影", "游戏", "演出", "演唱会", "ktv", "会员", "订阅", "剧本杀", "桌游",
        "旅游", "门票", "展览", "音乐会",
    ]),
    ("购物", [
        "买", "衣服", "裤子", "鞋", "外套", "t恤", "快递", "淘宝", "京东", "拼多多",
        "超市", "日用品", "洗发水", "纸巾", "家居", "耳机", "数码",
    ]),
]

EXPENSE_VERBS = re.compile(r"(花了|付了|支付|消费|买了|充值|缴费|交了|打车|加油|吃了|喝了|点了|下单)")
TODO_WEAK = re.compile(r"(记得|别忘了|别忘|要记得|待办|截止|ddl|提醒我)", re.IGNORECASE)
KEEP_AS_JOURNAL = re.compile(r"(今天|昨天|最近|这周|感觉|觉得|因为|所以|后来|然后|其实|好像|突然|想起)")
WEEKDAY_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 0, "天": 0}


@dataclass
class AmountHit:
    amount: float
    raw: str
    explicit: bool


@dataclass
class DueDate:
    due_at: datetime
    matched: str


@dataclass
class CaptureResult:
    kind: Kind
    content: str
    tags: list[str]
    amount: float | None
    category: Category | None
    due_at: datetime | None
    status: Literal["open"] | None
    confidence: float
    note: str


def _to_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _round_money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _format_amount(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def find_amount(text: str) -> AmountHit | None:
    match = re.search(r"(\d+(?:\.\d{1,2})?)\s*万(?:元|块)?", text, re.ASCII)
    if match:
        amount = _round_money(Decimal(match.group(1)) * 10000)
        return AmountHit(amount, match.group(0), True)

    match = re.search(r"[¥￥$]\s*(\d[\d,]*(?:\.\d{1,2})?)", text, re.ASCII)
    if match:
        return AmountHit(_to_number(match.group(1)), match.group(0), True)

    match = re.search(
        r"(\d[\d,]*(?:\.\d{1,2})?)\s*(?:元|块钱|块|人民币|rmb)", text, re.ASCII | re.IGNORECASE
    )
    if match:
        return AmountHit(_to_number(match.group(1)), match.group(0), True)

    match = re.search(
        r"(?:花了|付了|支付了?|消费了?|支出|充值了?)\s*(\d+(?:\.\d{1,2})?)", text, re.ASCII
    )
    if match:
        return AmountHit(_to_number(match.group(1)), match.group(0), True)

    return None


def find_loose_number(text: str) -> AmountHit | None:
    blocked_pattern = re.compile(
        r"(\d+(?:\.\d{1,2})?)\s*(点|分|月|日|号|年|岁|个|次|公里|km|kg|斤|天|人|杯|层|楼)",
        re.IGNORECASE | re.ASCII,
    )
    blocked = {match.start() for match in blocked_pattern.finditer(text)}

    for match in re.finditer(r"(\d+(?:\.\d{1,2})?)", text, re.ASCII):
        index = match.start()
        if index in blocked:
            continue
        around = text[max(0, index - 1): index + len(match.group(0)) + 1]
        if re.search(r"[-/.]\s*\d", around):
            continue
        return AmountHit(_to_number(match.group(1)), match.group(1), False)
    return None


def detect_category(text: str) -> Category | None:
    lowered = text.lower()
    for category, words in CATEGORY_KEYWORDS:
        if any(word.lower() in lowered for word in words):
            return category
    return None


def detect_prefix(text: str) -> tuple[Kind, str] | None:
    for pattern, kind in PREFIXES:
        match = pattern.match(text)
        if match:
            return kind, text[match.end():].strip()
    return None


def extract_tags(text: str) -> tuple[list[str], str]:
    tags: list[str] = []

    def replace(match: re.Match[str]) -> str:
        tags.append(match.group(2))
        return match.group(1)

    cleaned = re.sub(r"(^|[\s，,。、])#([\w-]{1,20})", replace, text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return list(dict.fromkeys(tags)), cleaned


def parse_due_date(text: str, now: datetime | None = None) -> DueDate | None:
    now = now or datetime.now().astimezone()
    base = now.replace(hour=9, minute=0, second=0, microsecond=0)

    def apply_hour(value: datetime) -> datetime:
        if re.search(r"(晚|夜|下午)", text):
            return value.replace(hour=20)
        if re.search(r"中午", text):
            return value.replace(hour=12)
        return value.replace(hour=9)

    relative: list[tuple[str, int]] = [
        ("大后天", 3),
        ("后天", 2),
        ("明天|明日|明早|明晚", 1),
        ("今天|今日|今晚", 0),
    ]
    for pattern, delta in relative:
        match = re.search(pattern, text)
        if match:
            return DueDate(apply_hour(base + timedelta(days=delta)), match.group(0))

    week = re.search(r"(下)?\s*(?:周|星期)([一二三四五六日天])", text)
    if week and week.group(2):
        target = WEEKDAY_MAP[week.group(2)]
        current = now.isoweekday() % 7
        delta = (target - current + 7) % 7
        if week.group(1):
            delta += 7
        return DueDate(apply_hour(base + timedelta(days=delta)), week.group(0))

    month_day = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", text, re.ASCII)
    if month_day:
        month = int(month_day.group(1))
        day = int(month_day.group(2))
        try:
            candidate = now.replace(
                month=month, day=day, hour=9, minute=0, second=0, microsecond=0
            )
        except ValueError:
            return None
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if candidate < today_start:
            candidate = candidate.replace(year=candidate.year + 1)
        return DueDate(apply_hour(candidate), month_day.group(0))

    return None


def parse_capture(raw: str, now: datetime | None = None) -> CaptureResult:
    now = now or datetime.now().astimezone()
    text = raw.strip()

    prefix = detect_prefix(text)
    if prefix is not None:
        kind_hint, text = prefix
    else:
        kind_hint = None

    tags, text = extract_tags(text)
    amount_hit = find_amount(text)
    category = detect_category(text)
    expense_verb = bool(EXPENSE_VERBS.search(text))
    bare_number = None if amount_hit else find_loose_number(text)

    is_bare_amount = bool(
        re.fullmatch(r"[¥￥$]?\s*\d+(?:\.\d{1,2})?\s*(?:元|块|块钱)?", text, re.ASCII)
    )
    looks_like_expense = bool(
        amount_hit
        or is_bare_amount
        or (bare_number and (expense_verb or category) and len(text) <= 30)
    )

    if kind_hint is not None:
        kind = kind_hint
        confidence = 0.98
    elif looks_like_expense and (
        (amount_hit and amount_hit.explicit) or expense_verb or category or is_bare_amount
    ):
        kind = "expense"
        confidence = 0.94 if (amount_hit and amount_hit.explicit) else 0.75 if is_bare_amount else 0.82
    elif TODO_WEAK.search(text) or re.match(r"^(要|得|该|必须)\s*\S", text):
        kind = "todo"
        confidence = 0.8 if TODO_WEAK.search(text) else 0.66
    elif len(text) >= 40 or KEEP_AS_JOURNAL.search(text):
        kind = "journal"
        confidence = 0.68
    else:
        kind = "thought"
        confidence = 0.6

    amount = None
    if kind == "expense":
        if amount_hit is not None:
            amount = amount_hit.amount
        elif bare_number is not None:
            amount = bare_number.amount

    final_category = (category or "其他") if kind == "expense" else None

    due_at = None
    due_text = ""
    if kind == "todo":
        due = parse_due_date(text, now)
        if due is not None:
            due_at = due.due_at
            due_text = due.matched
            confidence = min(0.95, confidence + 0.1)

    if kind == "expense":
        amount_text = f" ¥{_format_amount(amount)}" if amount is not None else "（未识别到金额）"
        category_text = f" · {final_category}" if final_category else ""
        note = f"记录为支出{amount_text}{category_text}"
    elif kind == "todo":
        note = f"记为待办{'，截止「' + due_text + '」' if due_text else '，未识别截止时间'}"
    elif kind == "journal":
        note = "记为日记"
    else:
        note = "记为闪念"

    return CaptureResult(
        kind=kind,
        content=text or raw.strip(),
        tags=tags,
        amount=amount,
        category=final_category,
        due_at=due_at,
        status="open" if kind == "todo" else None,
        confidence=max(0.4, min(0.99, confidence)),
        note=note,
    )
```

- [ ] **Step 4: 运行解析器测试确认通过**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_capture.py -v
uv run ruff check app/services/capture.py
```

预期：16 条测试全部 PASS，ruff 无错误。

- [ ] **Step 5: 写 capture 接口失败的测试**

`backend/tests/test_api_capture.py`：

```python
import re

from httpx import AsyncClient

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def test_capture_creates_expense(client: AsyncClient):
    response = await client.post(
        "/api/capture",
        json={"text": "午饭 32 元和同事", "at": "2026-11-09T15:30:00.000+08:00"},
    )
    assert response.status_code == 201
    body = response.json()

    assert body["entry"]["kind"] == "expense"
    assert body["entry"]["content"] == "午饭 32 元和同事"
    assert body["entry"]["amount"] == 32.0
    assert body["entry"]["category"] == "餐饮"
    assert body["entry"]["source"] == "capture"
    assert body["entry"]["occurredAt"] == "2026-11-09T07:30:00.000Z"
    assert ISO_Z.match(body["entry"]["occurredAt"])

    assert body["parsed"]["kind"] == "expense"
    assert body["parsed"]["amount"] == 32.0
    assert body["parsed"]["category"] == "餐饮"
    assert body["parsed"]["note"] == "记录为支出 ¥32 · 餐饮"
    assert body["parsed"]["confidence"] > 0.9


async def test_capture_todo_serializes_due_date(client: AsyncClient):
    response = await client.post(
        "/api/capture",
        json={"text": "记得明天交房租", "at": "2026-11-09T15:30:00.000+08:00"},
    )
    assert response.status_code == 201
    body = response.json()

    assert body["entry"]["kind"] == "todo"
    assert body["entry"]["status"] == "open"
    assert body["entry"]["dueAt"].endswith("Z")
    assert ISO_Z.match(body["entry"]["dueAt"])
    assert body["parsed"]["status"] == "open"
    assert body["parsed"]["content"] == "记得明天交房租"


async def test_capture_extracts_tags(client: AsyncClient):
    response = await client.post(
        "/api/capture",
        json={"text": "产品想法 #产品 #灵感", "at": "2026-11-09T15:30:00.000+08:00"},
    )
    body = response.json()
    assert body["entry"]["tags"] == ["产品", "灵感"]
    assert "#" not in body["entry"]["content"]
```

- [ ] **Step 6: 实现 capture 路由**

`backend/app/api/routes/capture.py`：

```python
from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core.time import utcnow
from app.repositories.entries import create_entry
from app.schemas import CaptureParsed, CaptureRequest, CaptureResponse, EntryCreate, EntryRead
from app.services.capture import parse_capture

router = APIRouter(tags=["capture"])


@router.post("/capture", response_model=CaptureResponse, status_code=201)
async def capture_route(payload: CaptureRequest, session: SessionDep) -> CaptureResponse:
    now = payload.at or utcnow()
    parsed = parse_capture(payload.text, now)
    entry = await create_entry(
        session,
        EntryCreate(
            kind=parsed.kind,
            content=parsed.content or payload.text,
            occurred_at=now,
            amount=parsed.amount,
            currency="CNY",
            category=parsed.category,
            status=parsed.status,
            due_at=parsed.due_at,
            tags=parsed.tags,
            meta={"captureNote": parsed.note, "confidence": parsed.confidence},
            source="capture",
        ),
    )
    return CaptureResponse(
        entry=EntryRead.model_validate(entry),
        parsed=CaptureParsed.model_validate(parsed),
    )
```

修改 `backend/app/main.py`：在导入区加入

```python
from app.api.routes.capture import router as capture_router
```

在 `app.include_router(entries_router, prefix="/api")` 后加入：

```python
    app.include_router(capture_router, prefix="/api")
```

- [ ] **Step 7: 运行全部测试确认通过**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_capture.py tests/test_api_capture.py -v
uv run pytest -q
uv run ruff check app tests
```

预期：全部 PASS，ruff 无错误。

- [ ] **Step 8: 提交**

```bash
cd E:/Code/LifeOS
git add backend
git commit -m "feat(backend): 移植快速捕捉解析器与 capture 接口

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 8: AI 回顾服务与 insights 接口

**Files:**
- Modify: `backend/app/services/insight.py`
- Create: `backend/app/api/routes/insights.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_api_insights.py`

**Interfaces:**
- Produces: `InsightResult`、`generate_insight(entries, stats, scope, settings=None) -> InsightResult`、`local_insight(stats, scope)`；`GET /api/insights`。
- Consumes: `Insight`、`InsightResponse`、`Stats`（Task 4）、`save_insight`（Task 4）、`compute_stats`（Task 5）。

- [ ] **Step 1: 写失败的 insights 测试**

`backend/tests/test_api_insights.py`：

```python
import json
from datetime import datetime, timezone

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AiInsight
from app.repositories.entries import create_entry
from app.schemas import EntryCreate

UTC = timezone.utc
URL = "https://api.deepseek.com/v1/chat/completions"
RANGE = "?scope=daily&from=2026-11-09T00:00:00.000Z&to=2026-11-10T00:00:00.000Z"


@pytest.fixture
def llm_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def seed_entry(session: AsyncSession):
    entry = await create_entry(
        session,
        EntryCreate(
            kind="expense",
            content="午饭 32 元",
            amount=32,
            category="餐饮",
            occurred_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        ),
    )
    await session.commit()
    return entry


async def test_insights_without_key_falls_back(
    client: AsyncClient, session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    await seed_entry(session)

    response = await client.get(f"/api/insights{RANGE}")
    assert response.status_code == 200
    body = response.json()

    assert body["insight"]["model"] == "local"
    assert "未配置 LLM_API_KEY" in body["warning"]
    assert body["insight"]["headline"].startswith("今天")
    assert body["stats"]["totalSpent"] == 32.0

    count = await session.scalar(select(func.count()).select_from(AiInsight))
    assert count == 1


@respx.mock
async def test_insights_uses_model_and_saves_snapshot(
    client: AsyncClient, session: AsyncSession, llm_env
):
    await seed_entry(session)
    model_payload = {
        "headline": "今天花得不多",
        "summary": "午饭花了 32 元，状态平稳。",
        "themes": ["工作日的节奏"],
        "spending": "只有一顿午饭。",
        "todos": "没有待办。",
        "mood": "flat",
        "suggestion": "保持记录。",
    }
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(model_payload, ensure_ascii=False)}}]},
        )
    )

    response = await client.get(f"/api/insights{RANGE}")
    assert response.status_code == 200
    body = response.json()

    assert route.called
    assert body["warning"] is None
    assert body["insight"]["model"] == "deepseek-chat"
    assert body["insight"]["headline"] == "今天花得不多"
    assert body["insight"]["mood"] == "flat"

    count = await session.scalar(select(func.count()).select_from(AiInsight))
    assert count == 1


@respx.mock
async def test_insights_retries_without_json_mode_on_400(
    client: AsyncClient, session: AsyncSession, llm_env
):
    await seed_entry(session)
    payload = {
        "headline": "重试成功",
        "summary": "摘要",
        "themes": [],
        "spending": "没有记账",
        "todos": "没有待办",
        "mood": "unknown",
        "suggestion": "继续记",
    }
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(400),
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
            ),
        ]
    )

    response = await client.get(f"/api/insights{RANGE}")
    assert response.status_code == 200
    assert route.call_count == 2
    assert response.json()["insight"]["headline"] == "重试成功"


@respx.mock
async def test_insights_falls_back_on_model_failure(
    client: AsyncClient, session: AsyncSession, llm_env
):
    await seed_entry(session)
    respx.post(URL).mock(side_effect=httpx.TimeoutException("timeout"))

    response = await client.get(f"/api/insights{RANGE}")
    assert response.status_code == 200
    body = response.json()

    assert body["insight"]["model"] == "local"
    assert "模型调用失败" in body["warning"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_api_insights.py -v
```

预期：失败，insights 路由/服务尚不完整。

- [ ] **Step 3: 实现 AI 服务**

把 `backend/app/services/insight.py` 完整替换为：

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

from app.config import Settings, get_settings
from app.core.time import to_iso_z, utcnow
from app.models import Entry
from app.schemas import Insight, Stats

SYSTEM_PROMPT = """你是 LifeOS 的生活记录分析助手。用户会给你一段时间内的全部记录（JSON 数组）。
你的任务是把这些碎片还原成「这个人这段时间过得怎么样」。

硬性要求：
1. 只使用记录里出现的事实，不要编造、不要推测记录中没有的事。
2. 需要举例时，引用记录里的原话片段，不要改写。
3. 语气像一个很了解他、但不奉承的老朋友：具体、克制、不说教。
4. 只输出 JSON 对象，不要 markdown 代码块，不要任何额外说明。

输出字段：
{
  "headline": "一句话概括（不超过 20 字）",
  "summary": "120-200 字的白描：做了什么、钱花在哪、待办推进得怎样、情绪如何",
  "themes": ["反复出现的主题或念头，最多 3 条，每条不超过 12 字"],
  "spending": "对消费结构的一句判断（没有记账数据就写「这段时间没有记账」）",
  "todos": "对待办推进情况的一句判断（没有待办就写「这段时间没有待办」）",
  "mood": "up | flat | down | unknown",
  "suggestion": "一条具体可执行的建议，不超过 40 字，不要空泛"
}"""


@dataclass
class InsightResult:
    insight: Insight
    warning: str | None


def llm_status(settings: Settings) -> dict[str, object]:
    return {
        "configured": bool(settings.llm_api_key),
        "model": settings.llm_model,
        "baseUrl": settings.llm_base_url,
    }


def _fmt_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def _kind_label(kind: str) -> str:
    return {
        "journal": "日记",
        "thought": "闪念",
        "expense": "记账",
        "todo": "待办",
        "habit": "习惯",
        "metric": "指标",
    }.get(kind, kind)


def compact_entries(entries: list[Entry]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for entry in entries[:200]:
        item: dict[str, object] = {
            "t": to_iso_z(entry.occurred_at),
            "kind": entry.kind,
            "text": entry.content[:240],
        }
        if entry.amount is not None:
            item["amount"] = float(entry.amount)
        if entry.category:
            item["category"] = entry.category
        if entry.status:
            item["status"] = entry.status
        if entry.due_at is not None:
            item["due"] = to_iso_z(entry.due_at)
        if entry.mood is not None:
            item["mood"] = entry.mood
        if entry.tags:
            item["tags"] = entry.tags
        items.append(item)
    return items


def _stats_payload(stats: Stats) -> dict[str, object]:
    return {
        "总记录数": stats.entry_count,
        "分类计数": stats.by_kind,
        "总支出": stats.total_spent,
        "分类支出": [category.model_dump(by_alias=True) for category in stats.by_category],
        "待办": {"进行中": stats.open_todos, "已完成": stats.done_todos},
        "平均心情": stats.avg_mood,
    }


def parse_json_loose(text: str) -> dict[str, object]:
    cleaned = re.sub(r"^\s*```(?:json)?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start: end + 1])
        raise ValueError("模型返回的不是合法 JSON")


async def call_model(entries: list[Entry], stats: Stats, scope: str, settings: Settings) -> dict:
    payload = {
        "scope": scope,
        "from": to_iso_z(stats.from_),
        "to": to_iso_z(stats.to),
        "stats": _stats_payload(stats),
        "entries": compact_entries(entries),
    }
    body = {
        "model": settings.llm_model,
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {settings.llm_api_key}",
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            url,
            json={**body, "response_format": {"type": "json_object"}},
            headers=headers,
        )
        if response.status_code == 400:
            response = await client.post(url, json=body, headers=headers)
        response.raise_for_status()
        data = response.json()

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise ValueError("模型返回为空")
    return parse_json_loose(content)


def _str(value: object, fallback: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def local_insight(stats: Stats, scope: str) -> Insight:
    range_label = "今天" if scope == "daily" else "这周"
    top = stats.by_category[0] if stats.by_category else None
    parts: list[str] = []

    if stats.entry_count == 0:
        parts.append(f"{range_label}还没有任何记录。")
    else:
        kinds = "、".join(
            f"{_kind_label(kind)} {count}" for kind, count in stats.by_kind.items()
        )
        parts.append(f"{range_label}记了 {stats.entry_count} 条：{kinds}。")

    if stats.total_spent > 0:
        top_text = f"，其中{top.category}最多（¥{_fmt_number(top.total)}）" if top else ""
        parts.append(f"花了 ¥{_fmt_number(stats.total_spent)}{top_text}。")

    if stats.open_todos + stats.done_todos > 0:
        parts.append(f"待办完成 {stats.done_todos} / {stats.open_todos + stats.done_todos} 条。")

    headline = f"{range_label}还是空白" if stats.entry_count == 0 else f"{range_label}记了 {stats.entry_count} 条"
    spending = (
        f"共 ¥{_fmt_number(stats.total_spent)}"
        + (f"，{top.category}占大头" if top else "")
        if stats.total_spent > 0
        else "这段时间没有记账"
    )
    todos = (
        f"完成 {stats.done_todos}，还剩 {stats.open_todos}"
        if stats.open_todos + stats.done_todos > 0
        else "这段时间没有待办"
    )
    mood = (
        "unknown"
        if stats.avg_mood is None
        else "up"
        if stats.avg_mood >= 3.6
        else "down"
        if stats.avg_mood <= 2.4
        else "flat"
    )

    return Insight(
        scope=scope,
        from_=stats.from_,
        to=stats.to,
        headline=headline,
        summary="".join(parts),
        themes=[f"消费集中在{top.category}"] if top else [],
        spending=spending,
        todos=todos,
        mood=mood,
        suggestion=(
            "待办积压了，先挑一件今天能做完的"
            if stats.open_todos > 3
            else "继续记，样本越多越能看出规律"
        ),
        model="local",
        generated_at=utcnow(),
    )


async def generate_insight(
    entries: list[Entry],
    stats: Stats,
    scope: str,
    settings: Settings | None = None,
) -> InsightResult:
    settings = settings or get_settings()
    fallback = local_insight(stats, scope)

    if not settings.llm_api_key:
        return InsightResult(fallback, "未配置 LLM_API_KEY，当前是本地统计版摘要")
    if not entries:
        return InsightResult(fallback, None)

    try:
        raw = await call_model(entries, stats, scope, settings)
        themes = raw.get("themes", [])
        insight = Insight(
            scope=scope,
            from_=stats.from_,
            to=stats.to,
            headline=_str(raw.get("headline"), fallback.headline),
            summary=_str(raw.get("summary"), fallback.summary),
            themes=[theme for theme in themes if isinstance(theme, str)][:3]
            if isinstance(themes, list)
            else [],
            spending=_str(raw.get("spending"), fallback.spending),
            todos=_str(raw.get("todos"), fallback.todos),
            mood=raw.get("mood") if raw.get("mood") in ("up", "flat", "down", "unknown") else "unknown",
            suggestion=_str(raw.get("suggestion"), fallback.suggestion),
            model=settings.llm_model,
            generated_at=utcnow(),
        )
        return InsightResult(insight, None)
    except Exception as error:
        return InsightResult(fallback, f"模型调用失败（{error}），已退回本地统计版")
```

- [ ] **Step 4: 实现 insights 路由**

`backend/app/api/routes/insights.py`：

```python
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.api.deps import SessionDep
from app.core.time import day_range, to_day_key, utcnow, week_range
from app.repositories.entries import entries_in_range
from app.repositories.insights import save_insight
from app.schemas import InsightResponse
from app.services.insight import generate_insight
from app.services.stats import compute_stats

router = APIRouter(tags=["insights"])


@router.get("/insights", response_model=InsightResponse)
async def insights_route(
    session: SessionDep,
    scope: Annotated[Literal["daily", "weekly"], Query()] = "daily",
    from_: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    to: Annotated[AwareDatetime | None, Query()] = None,
) -> InsightResponse:
    if from_ is not None and to is not None:
        range_from, range_to = from_, to
    elif scope == "weekly":
        range_from, range_to = week_range()
    else:
        range_from, range_to = day_range(to_day_key(utcnow()))

    entries = await entries_in_range(session, range_from, range_to)
    stats = compute_stats(entries, range_from, range_to)
    result = await generate_insight(entries, stats, scope)
    await save_insight(session, result.insight)
    return InsightResponse(insight=result.insight, warning=result.warning, stats=stats)
```

修改 `backend/app/main.py`：在导入区加入

```python
from app.api.routes.insights import router as insights_router
```

在 `app.include_router(capture_router, prefix="/api")` 后加入：

```python
    app.include_router(insights_router, prefix="/api")
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_api_insights.py -v
uv run pytest -q
uv run ruff check app tests
```

预期：全部 PASS，ruff 无错误。

- [ ] **Step 6: 提交**

```bash
cd E:/Code/LifeOS
git add backend
git commit -m "feat(backend): 移植 AI 回顾服务与 insights 接口

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 9: 静态托管、SPA 兜底与启动日志

**Files:**
- Create: `backend/app/core/static.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_static.py`

**Interfaces:**
- Produces: `resolve_static_file(web_dist, raw_path) -> Path | None`；SPA 兜底、路径穿越防护、启动日志。
- Consumes: `Settings.web_dist`（Task 1）、`create_app`（Task 1-8）。

- [ ] **Step 1: 写失败的静态托管测试**

`backend/tests/test_static.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_static.py -v
```

预期：失败，静态托管与路径解析尚未实现。

- [ ] **Step 3: 实现静态路径工具**

`backend/app/core/static.py`：

```python
from pathlib import Path


def resolve_static_file(web_dist: Path, raw_path: str) -> Path | None:
    if not raw_path:
        return None
    root = web_dist.resolve()
    candidate = (root / raw_path).resolve()
    if not candidate.is_relative_to(root):
        return None
    return candidate if candidate.is_file() else None
```

- [ ] **Step 4: 实现 SPA 兜底与启动日志**

把 `backend/app/main.py` 完整替换为：

```python
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
```

- [ ] **Step 5: 运行静态测试确认通过**

```bash
cd E:/Code/LifeOS/backend
uv run pytest tests/test_static.py -v
uv run pytest -q
uv run ruff check app tests
```

预期：全部 PASS，ruff 无错误。

- [ ] **Step 6: 提交**

```bash
cd E:/Code/LifeOS
git add backend
git commit -m "feat(backend): 添加静态托管与 SPA 兜底

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Task 10: 种子脚本、根脚本、文档与最终验收

**Files:**
- Create: `backend/scripts/seed.py`
- Modify: `package.json`
- Modify: `package-lock.json`（由 npm 命令更新）
- Modify: `.env.example`
- Modify: `tsconfig.json`
- Modify: `README.md`
- Delete: `server/ai.ts`、`server/db.ts`、`server/index.ts`、`server/repo.ts`、`server/seed.ts`

**Interfaces:**
- Produces: `npm run dev` / `npm start` / `npm run seed` / `npm run test:py` 全链路可用；README 与配置更新；Node 后端移除。
- Consumes: 全部前序任务。

- [ ] **Step 1: 移植种子脚本**

`backend/scripts/seed.py`：

```python
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Entry
from app.repositories.entries import create_entry
from app.schemas import EntryCreate
from app.services.capture import parse_capture

ITEMS: list[tuple[int, int, int, str]] = [
    (0, 8, 20, "早上跑了 3 公里，风有点凉，但跑完脑子很清醒"),
    (0, 9, 5, "记得今天下午把方案发出去"),
    (0, 12, 30, "午饭 28 元 食堂"),
    (0, 14, 10, "突然想到一个点子，LifeOS 不该有四个模块，应该是一条流 #产品"),
    (0, 16, 45, "打车 32"),
    (0, 21, 15, "今天开了三个会，脑子有点糊。回来的路上一直在想那个架构问题，后来在地铁上突然想通了：其实不需要同步层，服务端就是唯一真相。"),
    (1, 9, 0, "todo: 预约牙医"),
    (1, 10, 30, "咖啡 22"),
    (1, 13, 0, "午饭 35 元 和同事"),
    (1, 19, 40, "买书 89 元《系统之美》，翻了前两章就停不下来"),
    (1, 22, 0, "感觉最近睡眠不太好，可能是因为睡前看手机太久"),
    (2, 8, 45, "地铁 6"),
    (2, 12, 15, "午饭 26 元 面馆"),
    (2, 20, 30, "晚饭 68 元 和同事聚餐 #社交"),
    (2, 23, 10, "在想要不要换掉现在这套技术栈，重写成本太高，但维护成本也高 #技术"),
    (3, 10, 20, "记得周五前把预算表整理好"),
    (3, 15, 45, "奶茶 18"),
    (3, 19, 0, "电影票 70，看了一半就困了"),
    (4, 11, 30, "交房租 4200"),
    (4, 18, 20, "这个月的电费 260，比上个月多了不少"),
    (5, 9, 40, "想到一个产品点子：把待办和日记合在一起，做完的事自动变成回顾 #产品 #灵感"),
    (5, 21, 0, "给爸妈打电话了吗？"),
]


async def main(force: bool) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.lifeos_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            existing = await session.scalar(select(func.count()).select_from(Entry))
            if existing and not force:
                print(f"库里已有 {existing} 条记录，跳过。想强制追加请加 --force")
                return

            now = datetime.now().astimezone()
            created = 0
            for days_ago, hour, minute, text in ITEMS:
                at = (now - timedelta(days=days_ago)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                parsed = parse_capture(text, at)
                await create_entry(
                    session,
                    EntryCreate(
                        kind=parsed.kind,
                        content=parsed.content,
                        occurred_at=at,
                        amount=parsed.amount,
                        currency="CNY",
                        category=parsed.category,
                        status=parsed.status,
                        due_at=parsed.due_at,
                        tags=parsed.tags,
                        meta={"seeded": True, "captureNote": parsed.note},
                        source="import",
                    ),
                )
                created += 1

            await session.commit()
            print(f"已写入 {created} 条演示记录。")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.force))
```

- [ ] **Step 2: 更新根目录 scripts 与依赖**

```bash
cd E:/Code/LifeOS
npm uninstall fastify @fastify/cors @fastify/static tsx
```

然后把 `package.json` 调整为：

```json
{
  "name": "lifeos",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "description": "LifeOS — 把日记、闪念、记账、待办收敛到一条事件流里的个人生活系统",
  "engines": {
    "node": ">=22.18"
  },
  "scripts": {
    "dev": "concurrently -k -n api,web -c cyan,magenta \"npm:dev:api\" \"npm:dev:web\"",
    "dev:api": "cd backend && uv run uvicorn app.main:app --reload --port 8787",
    "dev:web": "vite --config web/vite.config.ts",
    "build": "vite build --config web/vite.config.ts",
    "start": "cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8787",
    "seed": "cd backend && uv run python scripts/seed.py",
    "typecheck": "tsc -p tsconfig.json --noEmit",
    "test": "node shared/capture.test.ts",
    "test:py": "cd backend && uv run pytest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "zod": "^3.24.1"
  },
  "devDependencies": {
    "@types/node": "^22.10.2",
    "@types/react": "^18.3.17",
    "@types/react-dom": "^18.3.5",
    "@vitejs/plugin-react": "^4.3.4",
    "concurrently": "^9.1.0",
    "typescript": "^5.7.2",
    "vite": "^6.0.5"
  }
}
```

- [ ] **Step 3: 更新 `.env.example`**

```bash
# ── 服务 ─────────────────────────────────────────────
LIFEOS_PORT=8787

# ── MySQL ────────────────────────────────────────────
# 密码含特殊字符时需要 URL 编码
LIFEOS_DATABASE_URL=mysql+aiomysql://lifeos:CHANGE_ME@127.0.0.1:3306/lifeos?charset=utf8mb4
LIFEOS_TEST_DATABASE_URL=mysql+aiomysql://lifeos:CHANGE_ME@127.0.0.1:3306/lifeos_test?charset=utf8mb4

# ── 大模型（可选）────────────────────────────────────
# 不填也能跑：回顾页会退化成「本地统计版」摘要。
# 兼容任何 OpenAI Chat Completions 协议的服务。
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

- [ ] **Step 4: 更新 tsconfig 并删除 Node 后端**

把 `tsconfig.json` 的 `include` 改为：

```json
"include": ["shared/**/*.ts", "web/src/**/*.ts", "web/src/**/*.tsx", "web/vite.config.ts"]
```

删除 Node 后端（git 历史仍保留）：

```bash
cd E:/Code/LifeOS
git rm -r server
```

- [ ] **Step 5: 重写 README**

把 `README.md` 替换为：

````markdown
# LifeOS

把 **日记 / 闪念 / 记账 / 待办** 收敛到**一条事件流**里的个人生活系统，附带一个把碎片读成「你这段时间过得怎么样」的 AI 回顾层。

后端：Python 3.12 + FastAPI + SQLAlchemy 2.0 + MySQL 8.0。前端：React 18 + Vite 6，零改动复用。

## 视图

| 视图 | 干什么 |
|---|---|
| 待办 | 只分「进行中 / 已完成」，逾期标红 |
| 捕捉 | 一个框，写完直接回车。类型是猜的，猜错了点「改」一键纠正 |
| 时间线 | 所有记录按天排开，可筛选、搜索、编辑、删除 |
| 日记 | 选日期、**一天一篇**、全屏写作，草稿自动留在本机 |
| 记账 | 月度总额、分类条形图、日均、按天明细 |
| 回顾 | 让模型读一遍你的记录，产出 headline / 摘要 / 主题 / 建议 |

## 目录

```text
backend/                Python 后端
  app/                  FastAPI 应用（routes → services → repositories → models）
  alembic/              MySQL schema 迁移
  scripts/              初始化、数据迁移、种子数据
  tests/                pytest
shared/                 前端共享的 TS 契约与解析器
web/                    React + Vite PWA
data/lifeos.db          旧 SQLite 数据库（迁移后保留作备份）
dist/web                前端构建产物
```

## 环境要求

- **Node ≥ 22.18**（前端构建与测试）
- **Python 3.12** + **uv**
- **MySQL 8.0**

## 首次设置

### 1. 初始化 MySQL

复制 `backend/scripts/init_mysql.sql.example` 为本地 SQL，替换 `CHANGE_ME` 为强密码，然后用 root 执行一次：

```bash
mysql -u root -p < backend/scripts/init_mysql.local.sql
```

脚本会创建 `lifeos`、`lifeos_test` 两个库和 `lifeos` 账号。

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入上一步使用的 MySQL 密码
```

### 3. 安装依赖、迁移、导入旧数据

```bash
npm install
cd backend
uv sync
uv run alembic upgrade head
uv run python scripts/migrate_sqlite_to_mysql.py --verify
```

`--verify` 会核对 entries 数量、按 kind 计数、支出合计和 ai_insights 数量；全部 `OK` 才继续。

## 开发

```bash
npm run dev        # FastAPI :8787 + Vite :5173
```

打开 <http://localhost:5173>。

## 生产

```bash
npm run build      # 输出 dist/web
npm start          # FastAPI :8787，同时提供页面和接口
```

启动日志会打印局域网地址，例如：

```text
局域网访问 http://192.168.1.7:8787   ← 手机用这个（同一 WiFi）
```

## 命令

```bash
npm run dev        # 开发（接口 + 前端热更新）
npm run build      # 构建前端到 dist/web
npm start          # 生产模式，单端口 8787
npm test           # 前端 TS 解析器测试
npm run test:py    # 后端 pytest
npm run seed       # 灌演示数据（--force 追加）
npm run typecheck  # 前端类型检查
```

后端代码质量：

```bash
cd backend
uv run ruff check .
```

## 数据与备份

- 数据库：MySQL `lifeos`
- 备份：`mysqldump -u lifeos -p lifeos > lifeos-backup.sql`
- 旧 `data/lifeos.db` 不再写入，保留用于回滚或对照

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 服务状态、数据库、模型是否已配置 |
| GET | `/api/entries?from&to&kind&status&q&tag&limit&offset` | 查询记录 |
| POST | `/api/entries` | 新建 |
| PATCH | `/api/entries/:id` | 部分更新 |
| DELETE | `/api/entries/:id` | 软删除 |
| POST | `/api/capture` | 传一句话，服务端解析并落库 |
| GET | `/api/stats?from&to` | 聚合统计 |
| GET | `/api/insights?scope=daily\|weekly` | 生成回顾 |

## 接上大模型（可选）

`.env` 里填 `LLM_API_KEY` 即可。兼容任何 OpenAI Chat Completions 协议的服务：

```bash
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

不填也能用：回顾页会自动退化成「本地统计版」摘要。

## 设计原则

1. 所有记录都在一张 `entries` 表里，`kind` 只决定字段和视图。
2. 时间统一存 UTC，展示层转本地；API 输出固定 `YYYY-MM-DDTHH:mm:ss.sssZ`。
3. 记账金额独立成列，才能聚合；只展示的字段进 `meta`。
4. 捕捉靠规则引擎，零延迟、零成本、可测试；模型只做回顾。
5. 没有 API Key 也有降级路径，页面永远有内容。
````

- [ ] **Step 6: 运行完整测试与构建**

```bash
cd E:/Code/LifeOS
npm test
npm run test:py
cd backend && uv run ruff check .
cd E:/Code/LifeOS
npm run build
```

预期：TS 解析器 13 条通过；pytest 全部通过；ruff 无错误；Vite 构建成功输出 `dist/web`。

- [ ] **Step 7: 停止旧 Node 服务并启动 Python 服务做冒烟测试**

先停止占用 8787 的旧 Node 进程：

```bash
powershell.exe -NoProfile -Command "Get-NetTCPConnection -LocalPort 8787 -State Listen | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }"
```

启动 Python 服务并验证：

```bash
cd E:/Code/LifeOS/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8787 > /tmp/lifeos-api.log 2>&1 &
API_PID=$!
sleep 5

curl -s http://127.0.0.1:8787/api/health
curl -s "http://127.0.0.1:8787/api/entries?limit=1"
curl -s "http://127.0.0.1:8787/api/insights?scope=daily" | head -c 600
curl -s http://127.0.0.1:8787/ | head -5

kill $API_PID
```

预期：

- health 返回 `ok: true`、MySQL 标识、`llm.configured: false`
- entries 返回迁移后的记录，时间以 `Z` 结尾
- insights 返回本地统计版和 warning
- `/` 返回前端 HTML

再手动打开 `http://localhost:8787`，依次检查待办、捕捉、时间线、日记、记账、回顾六个视图；手机用启动日志中的局域网地址访问一次。

- [ ] **Step 8: 最终提交**

```bash
cd E:/Code/LifeOS
git status --short
git add -A
git commit -m "refactor: 后端迁移到 Python/FastAPI + MySQL

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

检查 `git status` 应为干净，`git log --oneline` 能看到从基线到最终提交的完整历史。








