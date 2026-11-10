# LifeOS

把 **日记 / 闪念 / 记账 / 待办** 收敛到**一条事件流**里的个人生活系统，附带一个把碎片读成「你这段时间过得怎么样」的 AI 回顾层。

后端：Python 3.12 + FastAPI + SQLAlchemy 2.0 + MySQL 8.0。前端：React 18 + Vite 6，零改动复用。

## 视图

| 视图 | 干什么 |
|---|---|
| 待办 | 只分「进行中 / 已完成」，逾期标红 |
| 捕捉 | 一个框，写完直接回车。类型是猜的，猜错了点「改」一键纠正 |
| 时间线 | 所有记录按天排开，可筛选、搜索、编辑、删除 |
| 日记 | 选日期、当天可写**多篇**，保存后落到下面的记录列表，全屏写作，草稿自动留在本机 |
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

### 3. 安装依赖并迁移数据库

```bash
npm install
cd backend
uv sync
uv run alembic upgrade head
```

全新克隆到此即可。`data/` 已被 `.gitignore` 排除，不会包含旧 SQLite 文件。

#### 可选：导入旧 SQLite 数据

仅当 `data/lifeos.db` 存在（从旧版本升级）时，在 `backend/` 目录执行：

```bash
uv run python scripts/migrate_sqlite_to_mysql.py --verify
```

`--verify` 会核对 entries 数量、按 kind 计数、支出合计和 ai_insights 数量；全部 `OK` 才继续。全新克隆没有这个文件，跳过这一步。

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

## 故障排查

### 启动时报「MySQL 数据库连接失败」

服务启动时会先执行 `SELECT 1` 探测数据库，连不上会直接退出并打印数据库地址。先确认 MySQL 正在运行，账号密码与 `.env` 一致：

```bash
mysqladmin ping -h 127.0.0.1 -u lifeos -p
# 或
mysql -u lifeos -p -e "SELECT 1"
```

## 命令

```bash
npm run dev        # 开发（接口 + 前端热更新）
npm run build      # 构建前端到 dist/web
npm start          # 生产模式，单端口 8787
npm test           # 前端 TS 解析器测试
npm run test:py    # 后端 pytest
npm run seed -- --force  # 灌演示数据（库里已有数据时追加）
npm run typecheck  # 前端类型检查
```

后端代码质量：

```bash
cd backend
uv run ruff check .
```

## 数据与备份

- 数据库：MySQL `lifeos`
- 备份：`mysqldump -u lifeos -p lifeos > lifeos-backup.sql`（该文件已在 `.gitignore` 中）
- 旧 SQLite 库不再写入，保留用于回滚或对照。完整备份需要同时复制 `data/lifeos.db`、`data/lifeos.db-wal`、`data/lifeos.db-shm`；只复制 `.db` 可能丢失尚在 WAL 里的数据

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 服务状态、数据库、模型是否已配置 |
| GET | `/api/entries?from&to&kind&status&q&tag&limit&offset` | 查询记录 |
| GET | `/api/entries/:id` | 查询单条记录 |
| POST | `/api/entries` | 新建 |
| PATCH | `/api/entries/:id` | 部分更新 |
| DELETE | `/api/entries/:id` | 软删除 |
| POST | `/api/capture` | 传一句话，服务端解析并落库 |
| GET | `/api/stats?from&to` | 聚合统计 |
| GET | `/api/insights?scope=daily\|weekly` | 生成回顾 |

## 接上大模型（可选）

`.env` 里填 `LIFEOS_LLM_API_KEY` 即可。兼容任何 OpenAI Chat Completions 协议的服务：

```bash
LIFEOS_LLM_API_KEY=sk-xxx
LIFEOS_LLM_BASE_URL=https://api.deepseek.com/v1
LIFEOS_LLM_MODEL=deepseek-chat
```

OpenCode Go（OpenAI 兼容端点，模型 ID 是 `deepseek-v4.1-flash`，`[1M]` 只是 Claude Code 的别名）：

```bash
LIFEOS_LLM_API_KEY=oc_sk_xxx
LIFEOS_LLM_BASE_URL=https://opencode.ai/inference/go/openai/v1
LIFEOS_LLM_MODEL=deepseek-v4.1-flash
LIFEOS_LLM_SESSION_ID=lifeos
```

`LIFEOS_LLM_SESSION_ID` 会作为 `x-opencode-session` 头发送，供 OpenCode Go 做会话路由；普通 OpenAI 兼容服务可以忽略。

不填也能用：回顾页会自动退化成「本地统计版」摘要。

## 设计原则

1. 所有记录都在一张 `entries` 表里，`kind` 只决定字段和视图。
2. 时间统一存 UTC，展示层转本地；API 输出固定 `YYYY-MM-DDTHH:mm:ss.sssZ`。
3. 记账金额独立成列，才能聚合；只展示的字段进 `meta`。
4. 捕捉靠规则引擎，零延迟、零成本、可测试；模型只做回顾。
5. 没有 API Key 也有降级路径，页面永远有内容。
