# 日记删除确认与回顾聊天设计

- 状态：已批准（2026-11-10）
- 日期：2026-11-10
- 项目：LifeOS

## 1. 目标与边界

增加两项功能：日记删除前二次确认；回顾视图内支持与 AI 对话，并在服务端长期保存日/周独立的会话。用户可浏览历史会话、恢复上下文并继续对话。

沿用现有单用户个人应用、FastAPI + MySQL + React 架构及 OpenAI Chat Completions 兼容模型配置。不引入登录/多用户、流式输出、向量检索或自动记忆摘要。

## 2. 已确认的交互

### 2.1 日记删除

在 `web/src/components/DiaryView.tsx` 点击日记卡片的「删除」后显示确认弹窗。取消、按 Escape 或点击遮罩关闭弹窗，不调用删除 API；只有确认后才调用既有 `DELETE /api/entries/:id` 软删除接口。请求期间禁用重复提交；成功后关闭弹窗、刷新列表并提示；失败时保留弹窗、展示错误并允许重试或取消。复用现有 modal 样式，不抽取全局弹窗系统。

### 2.2 回顾聊天

- 日回顾和周回顾有独立对话；切换「今天 / 本周」进入各自当前周期会话。
- 回顾页提供历史会话列表，按最近活动时间倒序，可筛选日/周；选择历史周期后可看该周期回顾并继续原会话。
- 历史列表只显示至少有一轮成功问答的会话。会话可单独删除；删除前确认，删除不影响 entries 或回顾快照。
- 聊天支持 Enter 发送、Shift+Enter 换行；显示消息角色、加载状态和错误。失败时保留输入，避免将非 AI 降级摘要伪装成聊天回复。
- 聊天内容和相应周期的记录会发送到 `.env` 中配置的模型服务，界面清楚说明这一点。未配置模型时，回顾摘要与历史浏览仍可用，发送入口禁用并说明原因。

## 3. 存储与记忆

### 3.1 周期键

复用 `backend/app/core/time.py` 的本地时区边界：日周期为本地自然日；周会话以本地周一作为周期身份，但实际统计区间沿用现有 `/api/insights` 的「本周至今天结束」（周一 0 点到明天 0 点），不是完整未来一周。边界以 UTC 写入 `DATETIME(3)`。会话唯一键为 `(scope, period_start)`，scope 为 `daily` 或 `weekly`。当前周的会话随回顾刷新/继续聊天采用最新的本周统计区间；重新打开历史周会话则使用该会话保存的 period_start/period_end，保持历史上下文稳定。切换客户端时区不会重算既有会话周期；日期展示使用服务端返回的边界。

### 3.2 表结构

通过 Alembic 新增两张表，不改 `entries`、`ai_insights`：

- `review_chat_sessions`：id、scope、period_start、period_end、created_at、updated_at、latest_sequence。`(scope, period_start)` 唯一。当前日/周会话成功追加一轮消息时可更新 period_end 到最新当前范围，以跟随当前周数据；GET 读取保持只读；过往周期的 period_end 不再变化。历史快照按会话保存的完整范围精确匹配。
- `review_chat_messages`：id、session_id、sequence、role（user/assistant）、content、created_at。`(session_id, sequence)` 唯一；session_id 外键级联删除。

sequence 在单个会话内严格递增，消息排序不依赖毫秒时间戳。会话周期范围和 ID 作为服务器权威数据。

### 3.3 模型上下文

每次模型请求含：

1. 固定中文系统提示：具体克制、只依赖输入事实、不编造、不要求 JSON 格式。
2. 该会话周期的记录（复用回顾压缩格式，最多 200 条，每条内容最多 240 字）和统计。
3. 对应周期最近一次 `ai_insights` 快照的 headline、summary、themes、spending、todos、suggestion（如有）。
4. 最近 20 条已保存对话消息，以及本轮用户消息。

全部消息长期保存在 MySQL；最近 20 条仅是每次注入的上下文上限，不会删除旧消息。单条用户消息上限 4,000 字符。继续历史会话时严格按会话自身范围加载记录和快照，而非当前日期。

### 3.4 并发和事务

调用外部模型期间不持有数据库事务或行锁。服务端先读取上下文和会话 `latest_sequence`，请求模型成功后，在短事务中以该序号做乐观并发更新，再追加 user/assistant 两条消息并原子提交。若其他请求已更新会话，则返回 409、不保存本轮消息；客户端保留输入并提示刷新/重试。前端同一会话发送中禁用重复提交。

首次发送不预先持久化空会话；只有模型成功后，才创建会话并保存问答。唯一周期键处理并发首次发送，竞争失败方返回可重试的 409。模型未配置、超时、HTTP 错误、空答复或响应无效时，不创建会话、不存用户消息，并返回安全、可展示的错误；不得泄露密钥或上游 HTML。

## 4. 后端结构与 API

遵循现有分层：新增 `app/api/routes/review_chats.py`、`app/services/review_chat.py`、`app/repositories/review_chats.py`；ORM 放 `models.py`，契约放 `schemas.py`。LLM 请求可抽出小型通用 helper，但必须保持现有 `services/insight.py` 回顾 JSON 请求、400 重试和本地降级行为不变。新迁移需由部署者按现有流程显式执行 `uv run alembic upgrade head`，应用启动不自动改表。

新增路由，错误格式沿用 `{error, detail?}`：

- `GET /api/review-chats?scope=daily|weekly|all&limit=50&cursor=...`：会话元数据分页（默认 50、最大 100），按最后活动时间倒序；同时间以 session ID 做稳定次序，cursor 包含这两个排序值；不返回正文。返回 scope、period、消息数、最后活动时间及下一页 cursor。列表结果仅含有完整成功问答的会话。
- `GET /api/review-chats/current?scope=daily|weekly`：当前周期的会话（可空）、最近消息页、当前范围对应的已保存 insight（可空）和统计；无会话不创建会话。当前日期范围由服务端确定；GET 保持只读。ReviewView 仍调用既有 `GET /api/insights?scope=...` 生成/刷新当前摘要，再请求此接口读取范围完全匹配的最新快照；当前会话虽然以 period_start 唯一，但若之前日期的 period_end 已过，当前查看和续聊使用本次当前周期范围，而不是旧的 period_end。历史会话只读取按已保存 period_start/period_end 精确匹配的快照，不调用 insights 生成新摘要。打开当前视图或用户按「重新生成」时刷新摘要；切换至历史会话不触发 insights。
- `GET /api/review-chats/{session_id}?beforeSequence=...&limit=100`：指定历史会话、最近或更早消息页、关联 insight 和该周期统计；默认最近 100 条，最多 100 条，返回 `hasMore` 与翻页游标。不存在返回 404。
- `POST /api/review-chats/messages`：当前周期请求传 `scope`、可选 `sessionId` 和 `message`；服务端按当前周期范围读数据，sessionId（若提供）必须匹配当前 scope 与 period_start（周内 period_end 会变化）。历史会话请求只传 `sessionId` 和 `message`，使用该 session 保存的周期范围；没有当前 session 时在首轮成功后创建，有则复用。历史 sessionId 是范围权威值，不重新计算当前周期。成功响应含会话和本轮 user/assistant 消息；当前会话 period_end 仅在成功写入消息时更新。历史统计从该周期当前未删除记录重新计算，历史回顾内容则使用已保存快照。
- `DELETE /api/review-chats/{session_id}`：删除会话及级联消息，成功 204，不存在 404。

历史周期关联最近一条 scope、period_start、period_end 完全匹配的 `ai_insights` 快照；打开历史会话不调用回顾模型、不生成新快照。若快照确实不存在，返回 `insight: null`，统计仍可由该周期记录计算。当前周期每次回顾摘要成功刷新并产生新的 `ai_insights` 快照后，聊天上下文使用该周期最新的匹配快照；历史会话的周期快照匹配按保存范围选择最新版本。

发消息流程：校验 → 解析当前或已有历史会话范围 → 获取范围内记录、统计、快照和最近 20 条消息 → 调用配置的模型 → 校验答复非空 → 以乐观并发检查原子保存 user/assistant 两条消息 → 提交并返回。LLM 失败返回可展示的 502/503；输入无效 400；版本冲突 409；不存在 404。所有失败不留半轮消息。

## 5. 前端结构

### 日记

`DiaryView.tsx` 保存待确认条目、删除中状态和错误；弹窗复用 `modal-backdrop` / `modal`，有明确标题、说明、取消及危险操作按钮，支持 Escape 和遮罩关闭。

### 回顾

`web/src/api.ts` 增加历史列表、当前会话、会话详情分页、发送和删除封装。`ReviewView.tsx` 管理 scope、当前/历史会话选择、消息分页和加载状态：切换日/周加载当前周期；选择历史项加载相应快照与最新消息；「加载更早」按 sequence 插入消息列表顶部；全局历史列表支持分页和日/周筛选。

聊天区域自动滚动到新消息，发送失败保留输入并显示重试提示。删除选中会话成功后清空消息并切回当前周期；删除未选中会话只更新列表。发送期间禁用删除该会话。API 请求以服务端返回的消息为准，避免重载、多设备或失败重试时重复插入临时消息。

## 6. 隐私与兼容性

当前服务没有身份认证，新 API 沿用单用户部署边界，不承诺多用户隔离。聊天会发送周期记录、回顾快照和用户消息到配置的 LLM 服务，应在输入区明确提示。仅用户明确删除会话时清除聊天数据。现有 `/api/insights`、entries 契约以及无 Key 时本地统计版回顾不变。

## 7. 验证策略

### 后端

- Alembic upgrade/downgrade、新表约束与级联删除。
- 仓储测试：按周期创建/查询、周期唯一性、消息顺序、最近 20 条上下文、分页、删除级联和日/周隔离。
- API 测试：历史列表分页、当前空状态、加载及继续旧会话、参数校验、删除 204/404、并发冲突。
- 用 respx mock LLM：验证提示词、记录/快照/20 条上下文和 session 头；成功原子保存双消息；未配置 Key、超时、HTTP 错误、空答复均无持久化且不泄露凭据。
- 测试同一周期并发首次发送只产生一个会话。

### 前端与整体

- 自动化验证删除取消不调用 `api.remove`、确认只删除目标日记、失败保留弹窗并可关闭。
- 验证回顾周期切换、历史加载/分页/续聊/删除确认、发送失败保留输入和未配置模型禁用态。若项目无 React 组件测试工具，优先增加轻量开发依赖或提取可测试状态逻辑，不以手动点验作为唯一验收。
- 运行 `npm run typecheck`、`npm test`、`npm run build`；后端运行 `cd backend && uv run pytest`、`uv run ruff check .`。后端集成测试依赖配置正确且受安全守卫保护的 MySQL 测试库。

## 8. 不做

登录、多租户/权限；跨日周共享会话；自动摘要或向量记忆；无限上下文注入；流式输出、附件、语音、分享；会话导出和自动过期清理。
