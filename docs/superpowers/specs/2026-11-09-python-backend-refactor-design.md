# LifeOS 后端 Python/FastAPI 重构设计

- 状态：已批准
- 日期：2026-11-09
- 目标分支：`refactor/python-backend`
- 重构前基线：`3a3548e chore: 重构前基线（Node/Fastify + SQLite）`

## 1. 背景与目标

LifeOS 目前的后端是 Node 22+ 内置 TypeScript 类型擦除 + Fastify 5 + `node:sqlite`。本次重构把后端整体迁移到 Python，主要动机是**学习与架构演练**，同时保留现有产品行为。

目标：

1. 用 Python/FastAPI 完整替换 Node/Fastify 后端，职责一一对应。
2. **前端 React 零改动**：API 路径、JSON 字段、状态码、错误格式、静态托管方式全部保持兼容。
3. 数据库从 SQLite 迁移到本机 **MySQL 8.0**，现有数据全量迁移。
4. 采用分层架构，让业务、数据访问、HTTP 边界清晰分离，便于测试和后续演进。
5. 保持 `:8787` 单端口同时提供 API 和构建后的前端页面。
6. 建立可回滚的 git 基线，任何阶段都能对比和回退。

## 2. 非目标

本次不做：

- 前端代码改动或 UI 重做
- 登录鉴权、多用户、权限模型
- 新功能（向量检索、自动聚类、定时任务等）
- PostgreSQL、Docker、云数据库
- 把 MySQL 暴露到公网
- 改变现有数据模型语义

## 3. 现状摘要

- 前端：React 18 + Vite 6，六个视图（待办、捕捉、时间线、日记、记账、回顾）。
- 后端：Fastify 5，`server/index.ts` 提供 9 个 REST 端点，并托管 `dist/web`。
- 数据：SQLite 文件 `data/lifeos.db`，WAL 模式，两张表 `entries` / `ai_insights`。
- 共享层：`shared/schema.ts`（zod 契约）、`shared/capture.ts`（规则解析器）、`shared/date.ts`（时间工具）。前端直接 import 这些模块。
- 当前数据：28 条 entries（27 条有效 + 1 条软删除）、13 条 ai_insights 快照。
- 已知数据问题：23 条时间带 `+08:00`，5 条带 `Z`，与「统一 UTC」的设计约定不一致；迁移时统一归一化为 UTC。

## 4. 技术选型

| 领域 | 选择 | 理由 |
|---|---|---|
| Web 框架 | FastAPI | 异步、Pydantic 校验、依赖注入、自动 OpenAPI，和现有 zod 契约最对口 |
| 校验/序列化 | Pydantic v2 | 请求校验、响应模型、camelCase 别名、自定义序列化 |
| ORM | SQLAlchemy 2.0（async） | 现代 ORM，类型清晰，便于练分层与仓储模式 |
| MySQL 驱动 | `aiomysql`（运行时）、`pymysql`（Alembic） | 异步运行时 + 同步迁移，配置从同一 URL 派生 |
| 迁移 | Alembic | 显式 schema 版本管理，不在应用启动时建表 |
| AI 调用 | `httpx.AsyncClient` | 异步、超时控制清晰 |
| 配置 | `pydantic-settings` | 环境变量校验、fail-fast |
| 依赖管理 | `uv` + `pyproject.toml` + `uv.lock` | 本机已安装 uv 0.12.7 |
| 测试 | pytest + pytest-asyncio + httpx ASGITransport + respx | 单元 + API 集成 + HTTP mock |
| 代码质量 | ruff | lint + format，单一工具 |

Python 版本固定 **3.12**（`backend/.python-version`）。

## 5. 目标架构

### 5.1 目录结构

```
backend/
├── pyproject.toml
├── uv.lock
├── .python-version
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── main.py              # create_app、lifespan、CORS、异常处理、静态托管、启动日志
│   ├── config.py            # pydantic-settings
│   ├── db.py                # async engine / async_sessionmaker
│   ├── models.py            # SQLAlchemy ORM：Entry、AiInsight
│   ├── schemas.py           # Pydantic 请求/响应模型
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py          # get_session 等依赖
│   │   └── routes/
│   │       ├── health.py
│   │       ├── entries.py
│   │       ├── capture.py
│   │       ├── stats.py
│   │       └── insights.py
│   ├── services/
│   │   ├── capture.py       # 捕捉解析器（纯函数）
│   │   ├── insight.py       # AI 回顾 + 本地降级
│   │   └── stats.py         # 聚合统计
│   ├── repositories/
│   │   ├── entries.py
│   │   └── insights.py
│   └── core/
│       ├── time.py          # UTC 归一化、to_iso_z、日/月/周区间
│       └── errors.py        # 异常类型 + 错误响应格式
├── scripts/
│   ├── migrate_sqlite_to_mysql.py
│   ├── seed.py
│   └── init_mysql.sql.example
└── tests/
    ├── conftest.py
    ├── test_capture.py
    ├── test_api_entries.py
    ├── test_api_capture.py
    ├── test_api_stats.py
    ├── test_api_insights.py
    └── test_contract.py
```

### 5.2 分层职责

- **api/routes**：只处理 HTTP 解析、状态码、依赖注入，不写业务规则。
- **services**：业务逻辑，纯函数优先；capture 解析器不依赖数据库。
- **repositories**：所有 SQL/ORM 访问集中在此，路由和服务不直接使用 `select()`。
- **models**：数据库映射；**schemas**：对外契约。两者不混用。
- **core**：跨层工具（时间、错误），不依赖业务模块。

依赖方向：`api → services → repositories → models`，`schemas` 在 api 与 services 边界使用。

### 5.3 事务与依赖注入

- `get_session` 依赖每个请求创建一个 `AsyncSession`，请求成功提交、异常回滚，最后关闭。
- 服务/仓储函数显式接收 `AsyncSession`，便于测试和复用。
- 不引入全局可变状态；配置通过 `lifespan` 和依赖注入传递。

## 6. 数据层

### 6.1 MySQL 库与账号

- 服务：本机 MySQL 8.0.40，`MySQL80`，端口 3306。
- 数据库：
  - `lifeos`：生产数据。
  - `lifeos_test`：pytest 专用。
- 字符集：`utf8mb4`，排序规则 `utf8mb4_0900_ai_ci`，引擎 InnoDB。
- 专用账号 `lifeos@localhost` 与 `lifeos@127.0.0.1`（URL 使用 `127.0.0.1`，两个 host 都授权，避免 MySQL 的 host 匹配差异），密码只存 `.env`。
- `backend/scripts/init_mysql.sql.example` 提供建库、建账号、授权语句；由用户以 root 执行一次。root 密码不写入任何文件。

### 6.2 表结构

**entries**

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | `CHAR(36)` | PRIMARY KEY，UUID 字符串 |
| `kind` | `VARCHAR(16)` | NOT NULL |
| `content` | `MEDIUMTEXT` | NOT NULL；上限 20,000 字符 |
| `title` | `VARCHAR(200)` | NULL |
| `occurred_at` | `DATETIME(3)` | NOT NULL |
| `created_at` | `DATETIME(3)` | NOT NULL |
| `updated_at` | `DATETIME(3)` | NOT NULL |
| `amount` | `DECIMAL(12,2)` | NULL |
| `currency` | `CHAR(3)` | NOT NULL DEFAULT `'CNY'` |
| `category` | `VARCHAR(20)` | NULL |
| `status` | `VARCHAR(10)` | NULL |
| `due_at` | `DATETIME(3)` | NULL |
| `mood` | `TINYINT UNSIGNED` | NULL |
| `energy` | `TINYINT UNSIGNED` | NULL |
| `tags` | `JSON` | NOT NULL，默认 `(JSON_ARRAY())` |
| `meta` | `JSON` | NOT NULL，默认 `(JSON_OBJECT())` |
| `source` | `VARCHAR(16)` | NOT NULL DEFAULT `'manual'` |
| `deleted_at` | `DATETIME(3)` | NULL，软删除 |

索引：

- `idx_entries_occurred (occurred_at DESC)`
- `idx_entries_kind (kind, occurred_at DESC)`
- `idx_entries_status (status, due_at)`

**ai_insights**

| 列 | 类型 | 约束/说明 |
|---|---|---|
| `id` | `CHAR(36)` | PRIMARY KEY |
| `scope` | `VARCHAR(10)` | NOT NULL |
| `period_start` | `DATETIME(3)` | NOT NULL |
| `period_end` | `DATETIME(3)` | NOT NULL |
| `model` | `VARCHAR(100)` | NOT NULL |
| `payload` | `JSON` | NOT NULL |
| `created_at` | `DATETIME(3)` | NOT NULL |

索引：`idx_insights_period (scope, period_start DESC)`。

### 6.3 时间与金额约定

- 所有时间以 **UTC naive** 写入 `DATETIME(3)`；读取后附加 `timezone.utc`。
- 不使用 `TIMESTAMP`：避免 2038 上限和连接时区隐式转换。
- 输入时间必须带时区；进入仓储层前统一 `astimezone(UTC).replace(tzinfo=None)`。
- 输出时间必须序列化为 `YYYY-MM-DDTHH:mm:ss.sssZ`（毫秒固定 3 位）。
- 金额在 ORM 层是 `Decimal`；响应模型转 `float`，保证 JSON number。
- 金额舍入和 `avgMood` 使用 `Decimal + ROUND_HALF_UP`，对齐 JS `Math.round`。

### 6.4 Alembic

- `alembic upgrade head` 创建两张表和索引。
- 应用启动**不**自动建表。
- Alembic 使用同步 URL（`mysql+pymysql`），从 `LIFEOS_DATABASE_URL` 替换 driver 得到。
- 初始迁移为唯一版本，后续 schema 演进都走新 revision。

## 7. SQLite → MySQL 数据迁移

脚本：`backend/scripts/migrate_sqlite_to_mysql.py`。

要求：

1. 只读打开 `data/lifeos.db`，不修改源文件。
2. 迁移 `entries` 全部行（含软删除）和 `ai_insights` 全部行，保留原 `id` 与时间。
3. 时间用 `datetime.fromisoformat` 解析（支持 `+08:00` 和 `Z`），统一转 UTC naive。
4. `amount` 用 `Decimal(str(value))`；`tags` / `meta` / `payload` 解析 JSON 后写入 JSON 列。
5. 按主键 upsert，幂等，可重复执行。
6. 支持：
   - `--dry-run`：只报告将迁移的数量，不写库。
   - `--verify`：核对表行数、按 kind 计数、金额合计、`ai_insights` 数量；不一致时退出码非 0。
7. 迁移前打印源库统计；迁移后打印目标库统计。
8. 旧 `data/lifeos.db` 原样保留，不删除。

预期基线（2026-11-09）：28 条 entries、13 条 ai_insights。

## 8. API 契约

### 8.1 端点

| 方法 | 路径 | 成功状态 | 说明 |
|---|---|---|---|
| GET | `/api/health` | 200 | `{ok, version, db, llm:{configured, model, baseUrl}, now}` |
| GET | `/api/entries` | 200 | 查询参数 `from,to,kind,status,q,tag,limit,offset`；返回 `{items, count}` |
| GET | `/api/entries/:id` | 200 | 不存在或已软删除 → 404 |
| POST | `/api/entries` | 201 | 创建记录 |
| PATCH | `/api/entries/:id` | 200 | 部分更新；不存在 → 404 |
| DELETE | `/api/entries/:id` | 204 | 软删除；不存在 → 404 |
| POST | `/api/capture` | 201 | 入参 `{text, at?}`；返回 `{entry, parsed}` |
| GET | `/api/stats` | 200 | `from`、`to` 必填；缺失 → 400 |
| GET | `/api/insights` | 200 | `scope=daily / weekly`（默认 daily）、可选 `from/to`；返回 `{insight, warning, stats}` |

查询参数：

- `from` / `to`：带时区的 ISO 8601，语义为 `occurred_at >= from`、`occurred_at < to`。
- `kind`：`journal|thought|expense|todo|habit|metric`。
- `status`：`open|done|dropped`。
- `q`：内容模糊搜索，最长 200。
- `tag`：标签精确匹配，使用 `JSON_CONTAINS`。
- `limit`：默认 500，范围 1–2000；`offset`：≥ 0。

### 8.2 请求校验

Pydantic v2 规则与现有 zod 契约一致：

- `kind`：`journal|thought|expense|todo|habit|metric` 之一。
- `content`：trim 后 1–20,000 字符。
- `title`：最长 200 字符，可空。
- `amount`：有限、非负。
- `currency`：长度 3，默认 `CNY`。
- `category`：最长 20。
- `mood` / `energy`：1–5 整数。
- `tags`：最多 20 个，每个 1–30 字符。
- `meta`：JSON 对象，默认 `{}`。
- `dueAt` / `occurredAt`：必须带时区。
- `source`：`manual|capture|import|api`，默认 `manual`。

**PATCH 特殊规则**：所有字段可选且无默认值；使用 `model_fields_set` 判断“是否传了该字段”。未传 = 保持原值；显式传 `null` = 写入 NULL。禁止把未传字段刷成默认值。

### 8.3 响应序列化

- camelCase 别名：`occurredAt`, `createdAt`, `updatedAt`, `dueAt`, `deletedAt`。
- 时间统一 `to_iso_z()`，示例：`2026-11-09T09:34:11.695Z`。
- `amount` 输出 JSON number。
- `tags` 输出字符串数组；`meta` 输出对象。
- `source` 输出原枚举值。

Entry 响应字段固定为：

`id, kind, content, title, occurredAt, createdAt, updatedAt, amount, currency, category, status, dueAt, mood, energy, tags, meta, source`

Stats 响应字段固定为：

`from, to, totalSpent, byCategory[{category,total,count}], byKind, openTodos, doneTodos, avgMood, entryCount`

Insight 响应字段固定为：

`scope, from, to, headline, summary, themes, spending, todos, mood, suggestion, model, generatedAt`

### 8.4 错误格式

| 场景 | 状态码 | 响应 |
|---|---|---|
| 请求校验失败 | 400 | `{ "error": "参数不合法", "detail": "字段：原因；字段：原因" }` |
| 资源不存在 | 404 | `{ "error": "记录不存在" }` |
| `/api/*` 未命中 | 404 | `{ "error": "接口不存在" }` |
| 未处理异常 | 500 | `{ "error": "服务器内部错误" }`，细节只进日志 |

FastAPI 默认的 422 响应必须改写为上述 400 格式。`detail` 中的字段路径去掉 `body` / `query` 前缀。

### 8.5 静态托管与 SPA 兜底

- `dist/web` 路径从仓库根目录解析，可通过配置覆盖。
- API 路由优先注册；其余 GET/HEAD：
  1. 请求路径对应 `dist/web` 内真实文件 → 返回该文件。
  2. 路径带文件扩展名但文件不存在 → 404 纯文本 `静态资源不存在`。
  3. 其他路径 → 返回 `index.html`。
  4. 未构建前端 → 纯文本提示，内容与现有 Node 版一致。
- 不缓存 API 响应；PWA `sw.js` 行为保持不变。
- 启动日志：版本、本机地址、局域网地址、数据库目标、LLM 是否配置。

## 9. 业务逻辑移植

### 9.1 快速捕捉解析器

`app/services/capture.py` 是 `shared/capture.ts` 的纯函数等价实现。

必须保留：

- 前缀优先级：todo/待办 > 支出/记账/花费 > 日记 > 闪念。
- 金额识别：万、货币符号、元/块/人民币单位、支出动词、裸数字兜底。
- 分类关键词与优先级（餐饮 > 交通 > 住房 > 医疗 > 学习 > 娱乐 > 购物）。
- 待办判定：提醒语气、祈使语气。
- 日期解析：今天/明天/后天/大后天、周几/下周几、月日、上午/中午/下午/晚上时段。
- 标签抽取 `#tag` 并从正文移除。
- 日记启发式：长度 ≥ 40 或叙事关键词。
- 默认闪念、confidence 计算、中文 note 文案。

Python 实现细节：

- 标签正则使用 Unicode 感知的 `[\w-]`（标准库 `re` 不支持 `\p{L}`）。
- 数值正则使用 `re.ASCII` 对齐 JS 的 `\d`。
- 相对日期基于传入 `now` 的本地时区计算。
- 函数签名：`parse_capture(text: str, now: datetime) -> CaptureResult`、`parse_due_date(text: str, now: datetime) -> DueDate | None`。

前端继续使用 TS 解析器做即时预览；后端只在 `/api/capture` 使用 Python 解析器。两份实现以同一组测试用例锁定行为。

### 9.2 AI 回顾

`app/services/insight.py` 逐字保留现有行为：

- 相同 system prompt 与输出字段。
- compact entries：最多 200 条，正文截 240 字，包含时间、kind、金额、分类、状态、截止时间、mood、tags。
- 调用 OpenAI Chat Completions 兼容接口；90 秒超时；首次带 `response_format={"type":"json_object"}`，400 时去掉重试一次。
- 宽松 JSON 解析：去 markdown 代码块、截取首个 `{` 到最后一个 `}`。
- 字段缺失或类型错误时回退到本地摘要对应字段。
- `themes` 最多 3 条；`mood` 仅允许 `up|flat|down|unknown`。
- 无 Key：返回本地统计版，warning 为 `未配置 LLM_API_KEY，当前是本地统计版摘要`。
- 空记录：返回本地统计版，warning 为 `null`。
- 调用失败：返回本地统计版，warning 为 `模型调用失败（原因），已退回本地统计版`。
- 生成成功后写入 `ai_insights` 快照，`model` 记录实际模型名。

### 9.3 统计

- 支持 `from`/`to` 区间；只统计未软删除记录。
- `totalSpent` 为 expense 金额合计，保留 2 位。
- `byCategory` 按金额降序，每项 `{category,total,count}`。
- `byKind` 为各 kind 记录数。
- `openTodos` / `doneTodos` 仅统计 todo。
- `avgMood` 为有 mood 记录的平均值，保留 1 位；无数据为 `null`。
- `entryCount` 为区间内记录总数。

## 10. 配置与运行

### 10.1 环境变量

```bash
LIFEOS_PORT=8787
LIFEOS_DATABASE_URL=mysql+aiomysql://lifeos:密码@127.0.0.1:3306/lifeos?charset=utf8mb4
LIFEOS_TEST_DATABASE_URL=mysql+aiomysql://lifeos:密码@127.0.0.1:3306/lifeos_test?charset=utf8mb4

LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

- 配置文件为仓库根目录 `.env`，由 `pydantic-settings` 显式定位。
- 缺少 `LIFEOS_DATABASE_URL` 时启动失败并打印明确提示。
- 测试使用 `LIFEOS_TEST_DATABASE_URL`，禁止指向生产库。
- 数据库密码如含特殊字符需 URL 编码。

### 10.2 命令

首次设置：

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run python scripts/migrate_sqlite_to_mysql.py --verify
```

开发（根目录）：

```bash
npm run dev          # concurrently：FastAPI :8787 + Vite :5173
```

生产：

```bash
npm run build        # 前端不变，输出 dist/web
npm start            # FastAPI :8787
```

测试与质量：

```bash
npm test             # 保留：前端 TS 解析器测试
npm run test:py      # pytest
cd backend && uv run ruff check .
```

### 10.3 根目录脚本

- `dev:api`：`cd backend && uv run uvicorn app.main:app --reload --port 8787`
- `dev:web`：保持现状
- `dev`：concurrently 并行
- `start`：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8787`
- `seed`：`cd backend && uv run python scripts/seed.py`
- `test:py`：`cd backend && uv run pytest`
- `test`：保持 TS 解析器测试
- `build`：保持现状

依赖清理：从 `package.json` 移除 `fastify`、`@fastify/cors`、`@fastify/static`、`tsx`；保留 `zod`（前端仍使用 `shared/schema.ts`）。

## 11. 测试策略

### 11.1 单元测试

`tests/test_capture.py`：现有 `shared/capture.test.ts` 的 13 个用例逐条移植，覆盖：

1. 带单位金额 → 记账 + 分类
2. 货币符号
3. 万的口语写法
4. 数字 + 分类词
5. 显式前缀优先级
6. 记得/别忘 → 待办 + 明天
7. 日常感悟不误判为记账
8. 长文本判日记
9. 标签抽取
10. 月日日期解析
11. 周三/下周三
12. 「3点」不误判金额
13. 纯数字兜底

额外回归：中文标签、混合时区输入、`#标签` 去重。

### 11.2 API 集成测试

使用 `lifeos_test` 库：

- 会话 fixture：启动时 `alembic upgrade head`，每个用例前清空两张表。
- `httpx.AsyncClient(transport=ASGITransport(app=...))`。
- 覆盖：
  - entries：创建、查询、筛选、搜索、标签过滤、分页、PATCH 局部更新、显式 null、软删除、404。
  - capture：四种 kind、金额、标签、`at` 参数。
  - stats：空区间、分类排序、金额舍入、todo 计数。
  - insights：无 Key 降级、空记录、mock 模型成功、HTTP 400 重试、超时失败、快照落库。
  - health：字段形状。
  - contract：时间 `Z` 格式、camelCase 字段、错误格式、204。

### 11.3 验收命令

```bash
cd backend && uv run pytest
cd backend && uv run ruff check .
npm test
npm run build
```

## 12. 交付顺序

| 阶段 | 内容 | 验收 |
|---|---|---|
| 0 | git 基线、MySQL 库/账号、backend 脚手架、uv 依赖 | `uv sync` 成功，MySQL 可连 |
| 1 | ORM 模型 + Alembic 初始迁移 + 会话层 | `alembic upgrade head` 建出两张表 |
| 2 | SQLite → MySQL 迁移脚本 | `--verify` 数量/金额/按 kind 计数一致 |
| 3 | 读接口：health / entries / stats | curl 与 Node 版逐字段对比 |
| 4 | 写接口：CRUD + capture 解析器 | 13 条解析测试 + CRUD 集成测试通过 |
| 5 | AI 回顾 + 降级 + 快照 | 无 Key、mock 模型、快照测试通过 |
| 6 | 静态托管、SPA 兜底、启动日志 | 前端零改动可用，手机局域网可访问 |
| 7 | 根脚本、README、清理 Node 后端 | `npm run dev` / `npm start` 全链路可用 |
| 8 | 最终验收 | pytest、ruff、前端构建、六视图手测、迁移复核全部通过 |

## 13. 风险与缓解

| 风险 | 缓解 |
|---|---|
| MySQL 服务未启动导致服务不可用 | 启动时 fail-fast 并给出明确提示；README 写明检查命令 |
| 备份方式变化 | README 提供 `mysqldump lifeos > backup.sql`；保留旧 SQLite 文件 |
| 前后端两份 capture 实现漂移 | 同一组测试用例 + 额外回归用例；契约以测试为准 |
| 时间格式不兼容导致前端排序错误 | 统一 `to_iso_z()`，契约测试断言毫秒 + `Z` |
| PATCH 把未传字段刷成默认值 | `model_fields_set` + `exclude_unset`，集成测试覆盖 |
| MySQL 8 `caching_sha2_password` 认证失败 | 依赖包含 `cryptography`；URL 显式 charset |
| 数据迁移丢失或重复 | 幂等 upsert + `--dry-run` + `--verify` + 旧库只读保留 |
| 测试误连生产库 | 测试只读 `LIFEOS_TEST_DATABASE_URL`；缺失即失败并给出明确提示，不静默跳过 |

## 14. 验收标准

全部满足才视为完成：

1. `uv sync`、`uv run alembic upgrade head` 成功。
2. 迁移脚本 `--verify` 退出码 0；以迁移时源库实际计数为基准（2026-11-09 基线：entries 28 条含 1 条软删除、ai_insights 13 条），按 kind 计数和金额合计一致。
3. `uv run pytest` 全部通过；`uv run ruff check .` 无错误；`npm test` 13 条通过。
4. `npm run build` 成功，前端代码零改动。
5. `npm start` 后 `http://localhost:8787` 可打开六个视图；API 行为与 Node 版一致；手机局域网可访问。
6. `GET /api/health` 字段形状不变；`occurredAt` 等时间以 `Z` 结尾且毫秒 3 位；校验错误为 400 + `{error, detail}`；删除返回 204。
7. 未配置 `LLM_API_KEY` 时回顾页正常显示本地统计版和 warning。
8. 旧 Node 后端文件已删除，README、`.env.example`、根脚本更新完成，git 历史保留重构前基线。
