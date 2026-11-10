# 日记删除确认与回顾聊天实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 日记软删除前二次确认，并在回顾页增加按日/周分开的 AI 聊天、服务端长期记忆和可续聊历史会话。

**Architecture:** 保持 React → FastAPI → service → repository → MySQL 的现有分层。聊天会话/消息新增两张表和 Alembic migration；模型调用成功后才在短事务中保存完整问答，以 `(scope, period_start)` 唯一键和 `latest_sequence` 乐观并发控制避免重复周期及过期上下文。前端在现有 ReviewView 内集成周期选择、聊天与历史列表；日记确认使用 DiaryView 和既有 modal 样式。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、SQLAlchemy 2 Async、MySQL 8、Alembic、httpx、pytest/respx；Node >=22.18、React 18、TypeScript 5.7、Vite 6、Vitest 3.x、jsdom、React Testing Library。仓库当前 `package-lock.json` 已跟踪，验证环境 Node v24.12.0 / npm 11.21.0。

**Spec:** `docs/superpowers/specs/2026-11-10-review-chat-and-diary-delete-design.md`

## Global Constraints

- 日周期为服务端本地自然日；周周期身份为本地周一，统计范围沿用当前回顾的周一至明天 0 点；DB 时间写 UTC `DATETIME(3)`。
- scope 仅为 `daily` 或 `weekly`；会话唯一键为 `(scope, period_start)`；历史会话使用会话保存的周期边界。
- 每次 LLM 请求只注入最近 20 条历史消息；所有完整消息长期保存，单条用户消息最多 4,000 字符。
- 回顾上下文最多 200 条记录，每条记录文本最多 240 字；聊天失败不创建空会话、不写半轮消息、不走本地摘要降级。
- 上游模型调用期间不得持有 DB 事务/行锁；读取完上下文后先将 ORM 数据转成普通值并结束只读事务，再请求模型；模型成功后开启短事务，用 `latest_sequence` 乐观检查并写入，冲突返回 409。
- 历史会话列表只显示有成功问答的会话，默认每页 50、最多 100；单会话消息默认最近 100、最多 100，靠 sequence 游标向前翻页。
- 新迁移由部署流程显式运行 `cd backend && uv run alembic upgrade head`；应用启动不自动变更 schema。
- 日记与聊天删除均在确认后执行；聊天删除只级联删除聊天数据，不改 entries 或 ai_insights。
- 聊天界面明确提示周期记录、回顾快照和用户消息会发到配置的 LLM 服务；不增加身份认证或多用户隔离。
- 现有 `/api/insights` JSON 输出、400 重试、本地统计降级行为必须保持不变。
- 所有 API 错误继续遵循 `{error, detail?}`；LLM 凭据或上游原始 HTML 不得进入用户响应。
- 不创建 git commit，除非用户明确要求提交。

## Review Focus

1. **当前会话切换日期/跨客户端时区：** 日/周边界须由服务端确定，已存在历史会话必须按其保存的边界续聊。测试归属 Task 5（当前/历史周期 API 测试）。
2. **模型在首轮失败：** 不应留下空会话或 user-only 消息。测试归属 Task 5（模型错误参数化 API 测试）。
3. **同一会话并发发送及首次创建竞争：** 最多一个基于同一 sequence 的请求成功，失败方得到 409 且无半轮数据。测试归属 Task 3 和 Task 5（CAS 仓储测试与并发 API/service 测试）。
4. **相同毫秒时间戳和消息历史过长：** 顺序与分页必须以 sequence 稳定，而非 created_at。测试归属 Task 3（仓储分页与排序测试）。
5. **用户内容极限与上游错误泄密：** 4,001 字符应为 400；上游异常中的 token/HTML 不得返回客户端。测试归属 Task 5（schema 与错误映射测试）。

任务编号以计划主体为准；本列表只映射风险测试，不构成额外子任务。

---

## 文件结构与接口契约

- Modify `backend/app/models.py`：定义 `ReviewChatSession`、`ReviewChatMessage` ORM。
- Modify `backend/app/schemas.py`：定义 Chat request/message/session/list/page/response 契约，沿用 camelCase aliases。
- Create `backend/alembic/versions/0002_review_chats.py`：会话/消息表、索引、唯一键及外键级联。
- Modify `backend/tests/conftest.py`：对新外键表用子表优先的 `DELETE` 清理；保持生产/测试库守卫。
- Create `backend/app/repositories/review_chats.py`：会话查询、列表分页、消息页、上下文、乐观追加与删除。
- Create `backend/app/services/review_chat.py`：周期解析、记录/统计/快照上下文、OpenAI 兼容 chat completion 调用、事务错误映射。
- Create `backend/app/api/routes/review_chats.py` 并 modify `backend/app/main.py`：暴露回顾聊天 HTTP 契约。
- Modify `web/src/api.ts`：定义前端契约和 chat API 方法。
- Modify `web/src/components/DiaryView.tsx`：二次确认日记删除。
- Modify `web/src/components/ReviewView.tsx`、`web/src/styles.css`：回顾摘要、周期聊天、历史列表、分页、删除确认与响应式样式。
- Modify `package.json`（以及需要时的 `package-lock.json`）：增加前端组件测试脚本/开发依赖，不影响现有 `npm test` 捕捉测试。
- Create `web/src/components/DiaryView.test.tsx`、`web/src/components/ReviewView.test.tsx`、`web/src/api.test.ts`、`web/src/test-setup.ts`；组件行为使用 Vitest + jsdom + Testing Library + jest-dom。
- Modify `README.md`：新增 API 与聊天数据隐私/迁移说明。

### 后端对外契约（供各 Task 共用）

- `ChatSessionSummary = {id: string, scope: 'daily'|'weekly', periodStart: string, periodEnd: string, messageCount: number, updatedAt: string}`。
- `ChatSession = ChatSessionSummary & {createdAt: string, latestSequence: number}`；`ChatMessage = {id: string, sessionId: string, sequence: number, role: 'user'|'assistant', content: string, createdAt: string}`。
- `GET /api/review-chats?scope=daily|weekly|all&limit=50&cursor=...` → `{items: ChatSessionSummary[], nextCursor: string | null}`。稳定排序：`updatedAt DESC, id DESC`；cursor 封装最后一条的两字段。
- `GET /api/review-chats/current?scope=daily|weekly` → `{session: ChatSession | null, messages: ChatMessage[], hasMore: boolean, beforeSequence: number | null, insight: Insight | null, stats: Stats}`。当前无 session 时 messages 为 `[]`，stats 使用服务端当前周期计算；该只读 endpoint 不生成或更新 insight。
- `GET /api/review-chats/{session_id}?beforeSequence=...&limit=100` → 同上；默认最近 100 条，`hasMore` 表示可向更早 sequence 翻页；只按保存的历史范围读取 insight，不重生成。
- `POST /api/review-chats/messages` 当前周期请求 `{scope, sessionId?: string, message}`；历史续聊请求 `{sessionId, message}` 且不带 scope → `{session: ChatSession, messages: [userMessage, assistantMessage]}`。当前请求带 sessionId 时须匹配服务端当前 scope 与 period_start（当前周 period_end 会推进），否则 409；ID 不存在 404。历史会话的 sessionId 权威确定周期范围。
- `DELETE /api/review-chats/{session_id}` → 204；不存在 404。
- 内部 service 接口： `get_current_chat(session, scope) -> ChatView`、`get_chat_session(session, session_id, before_sequence, limit) -> ChatView`、`list_chat_sessions(session, scope, limit, cursor) -> ChatSessionPage`、`send_chat_message(session, message, *, scope=None, session_id=None, settings=None) -> ChatSendResult`、`delete_chat_session(session, session_id) -> bool`。
- 前端 API 接口：`api.chatList({scope, limit, cursor})`、`api.chatCurrent(scope)`、`api.chatSession(id, {beforeSequence, limit})`、`api.sendChat({scope, sessionId?, message} | {sessionId, message})`、`api.deleteChat(id)`。`ChatView` 含 `session: ChatSession | null`、sequence 升序的 `messages`、`hasMore`、`beforeSequence`、`insight: Insight | null`、`stats: Stats`。
- 后端测试清理：新消息表与会话表使用 `DELETE FROM review_chat_messages` 后 `DELETE FROM review_chat_sessions`；原有无外键表仍按现状清理。

---

### Task 1: 日记删除确认与前端组件测试基础

**Files:**
- Modify: `package.json`
- Modify: `package-lock.json`
- Create: `web/vitest.config.ts`
- Create: `web/src/test-setup.ts`
- Modify: `web/src/components/DiaryView.tsx`
- Modify: `web/src/styles.css`（仅当既有 modal 缺少危险按钮样式时）
- Create: `web/src/components/DiaryView.test.tsx`

**Interfaces:**
- Consumes: 现有 `api.remove(id)`、`refresh()`、`notify()` 和 `.modal-backdrop` / `.modal` CSS。
- Produces: 日记删除需用户明确确认；取消、Escape、遮罩点击不调用 `api.remove`。

- [ ] **Step 1: 检查当前包管理器 lockfile 和安装状态**

Run: `git ls-files package-lock.json pnpm-lock.yaml yarn.lock`
Expected: 使用仓库已有 lockfile；不得引入第二种包管理器。

- [ ] **Step 2: 添加最小前端组件测试依赖和脚本**

在 package.json 增加 `test:web: "vitest run --config web/vitest.config.ts"`，保留现有 `test: "node shared/capture.test.ts"`。新增 `web/vitest.config.ts` 将 environment 设为 jsdom，配置 `setupFiles: ['./web/src/test-setup.ts']`，匹配 `web/src/**/*.test.ts` 和 `web/src/**/*.test.tsx`。创建 `web/src/test-setup.ts`：导入 `afterEach`、`cleanup` 并注册 `afterEach(cleanup)`（Vitest globals 关闭时保证组件卸载），导入 `@testing-library/jest-dom/vitest`，组件测试需从 `vitest` 显式导入 `describe/it/expect/vi`。仓库 floor 是 Node >=22.18；验证环境当前 Node v24.12.0 / npm 11.21.0。保持 React/Vite/TypeScript 不变。

Run: `npm install -D vitest@^3.2.4 jsdom@^26.1.0 @testing-library/react@^16.3.0 @testing-library/user-event@^14.6.1 @testing-library/jest-dom@^6.6.4`
Expected: package.json 和已跟踪的 package-lock.json 同步，现有生产依赖不发生非必要升级。

- [ ] **Step 3: 先写失败的删除交互测试**

用最小 `ViewProps` mock 渲染 `DiaryView`，准备一个 kind=journal 的 entry。覆盖：点删除只显示确认框且 `api.remove` 未调用；点取消关闭且不删除；按 Escape、点击遮罩关闭且不删除；点击弹窗内部不误关；确认只对目标 id 调用删除；删除期间按钮禁用；请求失败显示错误且弹窗仍在。

```tsx
it('does not delete until the user confirms', async () => {
  render(<DiaryView {...propsWithDiary} />);
  await user.click(screen.getByRole('button', { name: '删除' }));
  expect(screen.getByRole('dialog', { name: /删除日记/ })).toBeVisible();
  expect(api.remove).not.toHaveBeenCalled();
});
```

- [ ] **Step 4: 运行测试并确认因缺少确认弹窗而失败**

Run: `npm run test:web -- web/src/components/DiaryView.test.tsx`
Expected: FAIL，原因是确认对话框不存在；不得把依赖导入失败当作有效红灯。

- [ ] **Step 5: 在 DiaryView 实现确认状态和安全关闭**

删除按钮只设置待删除 entry；确认 handler 防止 `deletingId` 重复提交，再调用 `api.remove`。成功后 await `refresh()`、关闭弹窗并 notify；失败时保持弹窗、展示错误并可重试。监听 Escape 只在未删除中关闭；遮罩仅在点击 backdrop 本身时关闭，按钮在删除中禁用。现有 UI 有 `.danger` token 时复用它，否则仅补一个 `.btn-danger` 样式。

- [ ] **Step 6: 运行日记组件测试和既有测试**

Run: `npm run test:web -- web/src/components/DiaryView.test.tsx`，然后 `npm test`
Expected: 新删除交互及现有 capture 测试通过。

---

### Task 2: Chat ORM、Alembic migration 与测试数据库清理

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/0002_review_chats.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_schema.py`
- Create: `backend/tests/test_migration_review_chats.py`

**Interfaces:**
- Consumes: 现有 `Base`、MySQL DATETIME(3)、Alembic 0001 migration。
- Produces: `ReviewChatSession` 和 `ReviewChatMessage` ORM；表名分别为 `review_chat_sessions`、`review_chat_messages`；唯一键、sequence 和 FK 行为与 spec 一致。

- [ ] **Step 1: 为 schema/migration 写失败断言**

在 `test_schema.py` 增加表/索引检查，断言会话唯一约束 `(scope, period_start)`、消息唯一约束 `(session_id, sequence)`、消息到 session 外键 `ON DELETE CASCADE`，列包括 `latest_sequence`，并断言两张表使用 InnoDB/utf8mb4。migration downgrade/upgrade 单独放在 `test_migration_review_chats.py`，通过 `tests/conftest.py` 的受保护 config helper 执行；不要用裸 Alembic CLI 回滚当前 `.env` DB。

- [ ] **Step 2: 执行目标测试确认 schema 尚未实现**

Run: `cd backend && uv run pytest tests/test_schema.py -q`
Expected: FAIL，显示缺少 review chat 表/约束。

- [ ] **Step 3: 定义 ORM 模型及 migration**

session 有 UUID id、scope、period_start/end、created_at、updated_at、latest_sequence 默认 0；scope + period_start 唯一。message 有 UUID id、session_id、sequence、role、content、created_at；session_id + sequence 唯一，创建 `(session_id, sequence)` 查询索引并设置 FK cascade。migration `down_revision = "0001_initial"`；downgrade 先删 messages 再删 sessions。

- [ ] **Step 4: 更新 clean_tables fixture**

在既有 `TRUNCATE ai_insights/entries` 之前先 `DELETE FROM review_chat_messages`、再 `DELETE FROM review_chat_sessions`。`migrate_test_db` 的 session fixture 已先升级至 head，故两表存在；保持 MySQL 外键有效，不依赖 `TRUNCATE` 绕过级联关系。其它现有 entries/insights 清理照旧。

- [ ] **Step 5: 运行 schema 和 Alembic 检查**

Run: `cd backend && uv run pytest tests/test_schema.py -q && uv run alembic heads`
Expected: schema 测试通过，只有一个 head `0002_review_chats`。

- [ ] **Step 6: 为 migration 回滚测试复用受保护的测试 URL**

在 `tests/conftest.py` 抽出 `_alembic_config()` helper：只将已过 `validate_test_database_url(test_url, production_url)` 的 `SYNC_TEST_URL` 配入 Alembic Config，并正确转义 `%`。`test_migration_review_chats.py` 用该 config 先 downgrade 到 `0001_initial`，断言新表消失，再 upgrade `head` 并断言表恢复。fixture 用 `try/finally` 保证测试失败也尽力恢复 head。

Run: `cd backend && uv run pytest tests/test_migration_review_chats.py -q`
Expected: 测试只操作 `LIFEOS_TEST_DATABASE_URL` 的受 guard 保护 `*_test` 库，验证 downgrade/upgrade 且最终回到 head；绝不运行读取默认 `.env` URL 的裸 destructive Alembic 命令。

---

### Task 3: Chat repository 与稳定分页/乐观追加

**Files:**
- Create: `backend/app/repositories/review_chats.py`
- Create: `backend/tests/test_repositories_review_chats.py`

**Interfaces:**
- Consumes: Task 2 ORM models；SQLAlchemy AsyncSession。
- Produces: `find_chat_by_period(session, scope, period_start)`、`get_chat(session, session_id)`、`list_chats(session, scope, limit, cursor_values)`、`list_messages(session, session_id, *, before_sequence, limit)`、`recent_messages(session, session_id, limit=20)`、`append_messages_if_current(session, session_id, expected_sequence, user_text, assistant_text)`、`create_chat_with_messages(...)`、`delete_chat(session, session_id)`。
- `append_messages_if_current` 返回 bool；只有 CAS 命中时新增连续 sequence 的两条消息并更新 session latest_sequence/updated_at，调用方负责 commit/rollback。

- [ ] **Step 1: 写 repository 失败测试**
覆盖：同 scope + period_start 找到唯一 session；scope 或 period_start 不同互相隔离；消息按 sequence 排序，即使 created_at 一样；消息详情从最近 limit 返回且 `before_sequence` 可向旧消息翻页；最近上下文最多 20 条且新旧次序明确；CAS sequence 正确时添加两条、不匹配时完全不添加；删除会话级联消息。

- [ ] **Step 2: 运行 repository tests 确认失败**

Run: `cd backend && uv run pytest tests/test_repositories_review_chats.py -q`
Expected: FAIL，导入或 repository 方法缺失。

- [ ] **Step 3: 实现会话查询和分页**

历史列表 cursor 由 `(updated_at, id)` 构成；过滤条件为 `updated_at < cursor.updated_at OR (updated_at == cursor.updated_at AND id < cursor.id)`，排序 `updated_at DESC, id DESC`。只返回有至少一条 assistant 消息且存在完整 user/assistant 配对的会话；列表查询只取元数据和计数，不加载消息正文。

- [ ] **Step 4: 实现按 sequence 的消息读取与 CAS 追加**

默认详情查询取 `sequence DESC LIMIT limit+1`，裁剪后反转为升序供 UI；旧消息页用 `sequence < before_sequence`。CAS 先 `UPDATE review_chat_sessions SET latest_sequence=latest_sequence+2, updated_at=... WHERE id=:id AND latest_sequence=:expected`，rowcount 非 1 即冲突；在同一事务中新增 sequence `expected+1` 和 `expected+2` 两条消息。

- [ ] **Step 5: 实现首次成功时创建会话和级联删除**

会话及两条消息在同一个调用事务中写入，latest_sequence 设为 2；周期唯一键冲突交由 service 回滚并映射为 409。delete 返回是否找到 session。

- [ ] **Step 6: 运行 repository tests 与 linter**

Run: `cd backend && uv run pytest tests/test_repositories_review_chats.py -q && uv run ruff check app/repositories/review_chats.py tests/test_repositories_review_chats.py`
Expected: 测试与 ruff 均通过。

---

### Task 4: Chat service、LLM 安全错误映射与回顾上下文

**Files:**
- Create: `backend/app/services/review_chat.py`
- Create: `backend/tests/test_review_chat.py`
- Modify: `backend/app/core/time.py`（只在现有 helper 无法返回一致范围时；优先复用 `day_range` / `week_range`）

**Interfaces:**
- Consumes: Task 3 repository；`entries_in_range`、`compute_stats`、`compact_entries`、`Stats.model_dump(mode="json", by_alias=True)`、`Settings`、现有 `ai_insights` 快照。避免从 insight service 导入私有 `_stats_payload`。
- Produces: Task 1 plan 中定义的五个内部 service 方法；明确异常 `ChatNotConfigured`、`ChatNotFound`、`ChatConflict`、`ChatUpstreamError`，由路由映射为 503/404/409/502。

- [ ] **Step 1: 写 service 的失败测试**

用 respx mock URL `https://api.deepseek.com/v1/chat/completions` 和固定 Settings，覆盖成功模型回复、无 key、timeout、HTTP 500、空/无效 choices、历史 session 用保存周期而非当前时间。检查 HTTP 请求含 system prompt、周期记录/统计、匹配 `ai_insights` 摘要、最多最近 20 条历史对话、新问题、`authorization` 与 `x-opencode-session` header。

- [ ] **Step 2: 测试异常和边界输入**

Pydantic 请求 schema 拒绝空白 message 和 4,001 字符；service 将上游异常转换为不含原始响应正文/密钥的 `ChatUpstreamError`；未配置 key 不调用外部 HTTP。断言失败后 session/message 均未写入。

- [ ] **Step 3: 测试确认失败行为**

Run: `cd backend && uv run pytest tests/test_review_chat.py -q`
Expected: FAIL，service/API 或异常定义还不存在。


当前 daily 用 `day_range(to_day_key(utcnow()))`；weekly 用 `week_range()`，其 end 是今天结束的次日 0 点。当前 session 按服务端当前 scope 范围读取记录、统计与最新范围快照，即使 session.period_end 仍是之前保存的 end；历史 session 则严格按其保存的 start/end 读取。读取有效未软删 records；增加 `compact_entries` 的可选 `limit` 参数并保持默认 200，确保最近记录排序按既有 occurred_at DESC；内容仍截断 240 字。直接用 `Stats.model_dump(mode="json", by_alias=True)` 生成统计 JSON；没有匹配 insight 时为 null。只将所需字段/序号转成普通值后结束只读事务，不让 ORM 对象过期后再访问。当前 session 的 period_end 只在消息成功提交时更新到最新当前范围；GET 与模型失败不修改会话。
- [ ] **Step 5: 实现 OpenAI 兼容聊天请求**

使用 httpx AsyncClient timeout 90s、既有 base URL/model/API key/session id header；只解析 `choices[0].message.content` 非空字符串；普通文本回答，不加 response_format。模型调用期间不持有 DB 事务。异常中不把 Authorization 或上游 HTML 写入日志/返回对象。

- [ ] **Step 6: 实现发送服务与原子持久化**

拉取最近 20 条历史消息后调用模型；成功后才 repository append user/assistant。CAS miss 回滚并抛 ChatConflict；首次会话唯一键竞争 rollback 并抛 ChatConflict。LLM 失败不会创建 session，也不会写 user-only message。

- [ ] **Step 7: 运行 service tests 与 linter**

Run: `cd backend && uv run pytest tests/test_review_chat.py -q && uv run ruff check app/services/review_chat.py tests/test_review_chat.py`
Expected: 测试与 ruff 均通过。

---

### Task 5: Chat schemas、FastAPI routes 和集成测试

**Files:**
- Modify: `backend/app/schemas.py`
- Create: `backend/app/api/routes/review_chats.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_api_review_chats.py`

**Interfaces:**
- Consumes: Task 3 repository 和 Task 4 service；统一异常格式由 `main.py` 管理。
- Produces: Global contract 中五个 HTTP endpoints；Pydantic alias 使用 camelCase；`ChatMessageCreate.message` strip whitespace、1..4000 字符。

- [ ] **Step 1: 写 HTTP 集成测试**

使用项目 `client`/`session` fixture；mock 模型。覆盖当前空会话、当前 daily/weekly 周期、历史列表 all/daily/weekly 分页、详情最近/更早消息、继续历史会话、成功返回 user/assistant、删除 204 与 404、参数错误 400、未配置 key 503、LLM timeout 502、sequence 冲突 409。

- [ ] **Step 2: 运行 API tests 确认失败**

Run: `cd backend && uv run pytest tests/test_api_review_chats.py -q`
Expected: FAIL，路由尚未注册。

- [ ] **Step 3: 写 Pydantic 契约**

定义消息 role Literal、session/list/view/send DTO；定义 `ChatMessageText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]` 并用于请求字段（不要把 `strip_whitespace` 传给 `Field`）；时间采用现有 UTC `field_serializer` 约定；响应字段由 alias_generator 输出 camelCase。

- [ ] **Step 4: 写 routes 并注册 router**

使用 `SessionDep` 和 service；显式 `await session.commit()` 在成功响应前完成，异常 rollback。按明确异常映射 404/409/502/503，其他验证错误交给现有格式化处理。固定路径 `/current` 和 `/messages` 在动态 `/{session_id}` route 前注册，防止路径被动态段吞掉。加入 `app.include_router(review_chats_router, prefix="/api")`。

- [ ] **Step 5: 增加 API 所有权和边界断言**

验证历史 `sessionId` 不存在返回 404；已有 session 请求即使 payload 带另一 scope 也必须按 session period 执行或拒绝不支持的多余 scope，不得静默切到当前日/周；当前周首尾由 server local tz helper 决定；重复 session/message 不产生半轮写入。测试验证上游错误 body 内模拟的 `sk-secret` 不出现在响应。

- [ ] **Step 6: 运行 API、既有 insight 测试及 lint**

Run: `cd backend && uv run pytest tests/test_api_review_chats.py tests/test_api_insights.py -q && uv run ruff check app/api/routes/review_chats.py app/schemas.py app/main.py tests/test_api_review_chats.py`
Expected: 新聊天测试通过，既有 AI 回顾的 mock/400 重试/本地降级仍通过。

---

### Task 6: Web API 客户端类型与单元测试

**Files:**
- Modify: `web/src/api.ts`
- Create: `web/src/api.test.ts`
- Modify: `web/vitest.config.ts`（仅调整测试 include 到 `web/src/**/*.test.ts` 与 `web/src/**/*.test.tsx`）

**Interfaces:**
- Consumes: Task 5 JSON camelCase 契约。
- Produces: `ChatSessionSummary`、`ChatSession`、`ChatMessage`、`ChatView`、`ChatPage` 类型，以及 `api.chatList({scope, limit, cursor})`、`api.chatCurrent(scope)`、`api.chatSession(id, options)`、`api.sendChat(request)`、`api.deleteChat(id)` 方法。

- [ ] **Step 1: 写 API client 测试**

Mock global fetch，验证 list query encoding、当前周期路径、session cursor/limit、POST body 的当前 scope 与历史 sessionId 两种格式、DELETE 204（request helper 已支持 204）、错误响应 `detail` 映射为 Error。

- [ ] **Step 2: 运行测试确认 API 方法缺失**

Run: `npm run test:web -- web/src/api.test.ts`
Expected: FAIL，api chat 方法尚不存在。

- [ ] **Step 3: 为响应契约添加 TS 类型和方法**

添加严格字段类型和 URLSearchParams 构造；历史 sessionId 请求不传当前 scope；分页参数按服务端约定命名 `beforeSequence`、`limit`；不改变现有 `api.insight`。

- [ ] **Step 4: 运行 API client 测试和类型检查**

Run: `npm run test:web -- web/src/api.test.ts && npm run typecheck`
Expected: tests 与 TypeScript 通过。

---

### Task 7: ReviewView 的聊天、会话历史与周期状态

**Files:**
- Modify: `web/src/components/ReviewView.tsx`
- Modify: `web/src/components/ReviewView.test.tsx`
- Modify: `web/src/api.ts`（只在视图测试揭露缺少必要 API 表达时）
- Modify: `web/src/test-setup.ts`（如果 jsdom 缺少 `scrollIntoView`，提供 no-op mock）

**Interfaces:**
- Consumes: Task 6 `api.chatList({scope, limit, cursor})`、`api.chatCurrent(scope)`、`api.chatSession(id, {beforeSequence, limit})`、`api.sendChat(request)`、`api.deleteChat(id)`；现有 `api.insight(scope)`；`ReviewView({llmConfigured: boolean})`。
- Produces: 在摘要下方工作的日/周聊天；历史列表、详情恢复、分页与续聊；失败保留输入；删除会话需确认。

- [ ] **Step 1: 写当前周期和历史会话 UI 的失败测试**

Mock `api.insight`、`api.chatList`、`api.chatCurrent`、`api.chatSession`；挂载/切换 daily 或 weekly 时先调用 `api.insight(scope)` 刷新当前摘要快照，再调用只读 `api.chatCurrent(scope)` 加载当前会话、该周期已存快照和消息；选择历史会话时只调用 `api.chatSession(id)`，不调用 insights 覆盖其摘要；测试加载更早消息追加到列表顶部且顺序正确。另测切换 scope 不串消息、`llmConfigured={false}` 禁用发送而仍可浏览聊天，true 时发送可用。

- [ ] **Step 2: 写发送/错误/删除失败测试**

测试 Enter 发送而 Shift+Enter 插入换行；发送时按钮禁用；API reject 后输入保留、显示错误且不插入 assistant 假消息；点击删除历史会话仅弹确认，取消不调用 API，确认后 DELETE 并从列表移除；删除当前选中会话后切回当前周期。

- [ ] **Step 3: 运行视图测试确认失败**

Run: `npm run test:web -- web/src/components/ReviewView.test.tsx`
Expected: FAIL，因为 ReviewView 当前没有聊天和历史入口。

- [ ] **Step 4: 将 ReviewView 状态按 scope/session 隔离**

维护 `scope`、`selectedSessionId`（null 代表当前周期）、`ChatView`、列表游标、消息游标、draft、loading/sending/error、待删除 session。用 request id 或 AbortController 丢弃切 scope/选会话后过期的异步响应；切 scope 默认回到该 scope 当前会话。

- [ ] **Step 5: 实现历史加载和分页**

历史列表有 daily/weekly/all 筛选、加载更多按钮；当前会话用 `api.chatCurrent(scope)`；历史项用 `api.chatSession(id, {limit: 100})`；旧消息页用返回的 `beforeSequence` 请求并合并到 messages 前方、按 sequence 去重。历史查看同步展示该周期 insight/stats，不调用 `api.insight` 覆盖历史数据。

- [ ] **Step 6: 实现发送和删除确认状态**

Enter 仅在非组合输入、输入非空且未 sending 时发送；Shift+Enter 只换行。成功响应只合并服务端返回的两条消息并清空 draft；失败保留 draft。session delete 需确认，发送期间禁用当前 session delete，选中会话删除成功后回 current。

- [ ] **Step 7: 运行 ReviewView 组件测试与类型检查**

Run: `npm run test:web -- web/src/components/ReviewView.test.tsx && npm run typecheck`
Expected: review/chat UI behaviors tests and typecheck pass.

---

### Task 8: Review/chat responsive styling, privacy copy and README

**Files:**
- Modify: `web/src/styles.css`
- Modify: `web/src/components/ReviewView.tsx`（若隐私说明/ARIA copy 尚未加）
- Modify: `web/src/App.tsx`（Task 7 已完成时不再重复修改）
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 7 DOM classes and existing design tokens/responsive breakpoints.
- Produces: 手机上可用的聊天/历史布局；清楚的模型数据发送说明；文档准确描述新 API 和 migration。

- [ ] **Step 1: 写或补充 UI 测试断言关键提示与禁用态**

断言有明确“聊天会将本周期记录和对话发送到已配置的模型服务”提示；`health`/模型未配置状态下发送控件禁用，历史浏览不禁用。

- [ ] **Step 2: 运行 ReviewView 测试确认提示/样式需求**

Run: `npm run test:web -- web/src/components/ReviewView.test.tsx`
Expected: 已有状态测试通过，新隐私提示断言在文案未实现时失败。

- [ ] **Step 3: 实现响应式和状态样式**

为聊天气泡、历史周期列表、输入区、加载/错误/未配置、空状态、加载更多按钮和危险删除操作加 scoped class；沿用现有 CSS variables；在窄屏下历史列表可折叠/横向选择且输入区不被底部 tabbar 遮挡。增加 focus-visible、aria-live 消息更新和按钮 accessible name。

- [ ] **Step 4: 更新 README API、隐私和迁移说明**

增补会话/消息/删除端点表；说明部署前执行 `cd backend && uv run alembic upgrade head`、聊天内容会发往配置的 LLM、消息服务端持久保存及可单独删除、历史列表可继续旧会话。保留原有 API/模型说明。

- [ ] **Step 5: 运行前端测试和类型检查**

Run: `npm run test:web && npm run typecheck`
Expected: 所有新组件/API 测试通过，TypeScript 无错误。

---

### Task 9: 全量回归与数据库迁移验证

**Files:**
- Modify only failing implementation/tests/docs discovered above.
- Review only: API contract agreement between `docs/superpowers/specs/2026-11-10-review-chat-and-diary-delete-design.md` and this plan before running destructive migration checks; no code or migration command uses production DB URL.

**Interfaces:**
- Consumes: Tasks 1–8 merged working tree。
- Produces: 完成的功能、migration 和测试结果；不提交 git commit。

- [ ] **Step 1: 运行全部前端测试、类型和生产构建**

Run: `npm test && npm run test:web && npm run typecheck && npm run build`
Expected: 捕捉既有测试、所有新增组件/API 测试、类型检查及 Vite production build 均成功。

- [ ] **Step 2: 运行完整后端测试与 Ruff**

Run: `cd backend && uv run pytest && uv run ruff check .`
Expected: 所有既有与新增测试通过、ruff 无错误。测试会清理 `LIFEOS_TEST_DATABASE_URL` 对应库数据，必须先确认其为 `_test` 库并与生产库不同。

- [ ] **Step 3: 验证 Alembic migration 当前 head**

Run: `cd backend && uv run pytest tests/test_migration_review_chats.py -q && uv run alembic heads`
Expected: `test_migration_review_chats.py` 通过受 guard 保护的测试 URL 断言数据库 version 是 `0002_review_chats`；`alembic heads` 显示唯一 head。禁止裸跑 `alembic current`，它会读 `.env` 中的默认数据库 URL。

- [ ] **Step 4: 查看最终 diff 和工作区**

Run: `git diff --check && git status --short && git diff --stat`
Expected: 无 whitespace 错误；改动仅限本计划文件清单及测试 lockfile；没有意外数据、dist 或 `.env` 文件。
