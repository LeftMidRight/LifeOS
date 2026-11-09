# LifeOS

把 **日记 / 闪念 / 记账 / 待办** 收敛到**一条事件流**里的个人生活系统，附带一个把碎片读成「你这段时间过得怎么样」的 AI 回顾层。

> 核心判断：这不是四个模块，是**一张表 + 六个视图**。四个模块会互相看不见，AI 也就无从分析。

| 视图 | 干什么 |
|---|---|
| 待办 | 只分「进行中 / 已完成」，逾期标红 |
| 捕捉 | 一个框，写完直接回车。类型是猜的，猜错了点「改」一键纠正 |
| 时间线 | 所有记录按天排开，可筛选、搜索、编辑、删除 |
| 日记 | 选日期、**一天一篇**、全屏写作，草稿自动留在本机 |
| 记账 | 月度总额、分类条形图、日均、按天明细 |
| 回顾 | 让模型读一遍你的记录，产出 headline / 摘要 / 主题 / 建议 |

### 日记为什么不做成独立表

日记在这个系统里就是 `kind = journal` 的记录，一天取「最近编辑的那一条」当主日记。
好处是：今天在「捕捉」里随手写的一大段话，打开日记页会**直接出现**，编辑后就变成正式日记——
不需要「导入 / 合并」这种动作。一条流的好处在这里兑现。

全屏编辑器只做三件事：铺满视口、隐藏所有导航；衬线字 + 2.0 行高；草稿实时写 `localStorage`。
没保存就按 Esc 关掉不会丢，下次进来会提示「已恢复未保存的草稿」。

```
E:\Code\LifeOS
├── shared/            前后端共享的契约层
│   ├── schema.ts      数据模型 + zod 校验（接口契约的唯一来源）
│   ├── capture.ts     自然语言 → 结构化记录（规则引擎，纯函数、可测试）
│   ├── date.ts        UTC 存储 / 本地展示的时区工具
│   └── capture.test.ts
├── server/
│   ├── db.ts          node:sqlite（Node 内置，零原生依赖）
│   ├── repo.ts        仓储层 —— 将来换 Postgres/Supabase 只改这一层
│   ├── ai.ts          LLM 回顾，没配 Key 自动降级为统计版
│   ├── index.ts       Fastify REST API + 前端静态托管
│   └── seed.ts        演示数据
├── web/               React + Vite 的 PWA
└── data/lifeos.db     你的数据（首次启动自动创建，已 gitignore）
```

---

## 快速开始

需要 **Node ≥ 22.18**（用到了内置 TypeScript 类型擦除和 `node:sqlite`）。

```bash
npm install          # 纯 JS 依赖，无需编译原生模块
npm run seed         # 可选：灌 22 条演示数据，先看看长什么样
npm run dev          # 接口 :8787 + 前端 :5173
```

打开 <http://localhost:5173>。

生产模式（推荐，单端口、可装成 App）：

```bash
npm run build        # 产物在 dist/web
npm start            # 只需 :8787，同时提供页面和接口
```

启动日志会打印局域网地址，例如：

```
局域网访问 http://192.168.1.7:8787   ← 手机用这个（同一 WiFi）
```

## 手机上怎么用

1. 电脑和手机连同一个 WiFi；
2. 手机浏览器打开启动日志里的局域网地址；
3. iOS：分享 → 添加到主屏幕；Android：菜单 → 安装应用。

手机和电脑看的是**同一个服务、同一个 SQLite 文件**，所以不存在「同步冲突」——
没有双向同步，就没有合并。这是 v0.1 刻意的取舍。

> 注意：局域网走 http，浏览器不把 http 内网地址视为安全上下文，所以**离线缓存（Service Worker）不会启用**，
> 页面本身照常可用。要真离线，需要 https（放到 VPS / Cloudflare Tunnel / 内网 Tailscale）。

## 接上大模型（可选）

复制 `.env.example` 为 `.env`，填 `LLM_API_KEY` 即可。兼容任何 OpenAI Chat Completions 协议的服务：

```bash
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

不填也能用：回顾页会自动退化成「本地统计版」摘要，永远有内容可看。
本地跑 Ollama 同样可以（`http://127.0.0.1:11434/v1`）。

---

## 数据模型

所有记录都在 `entries` 一张表里，`kind` 只决定有哪些结构化字段：

| 字段 | 说明 |
|---|---|
| `kind` | journal / thought / expense / todo / habit / metric |
| `occurredAt` | **事件发生时间**（≠ 创建时间），UI 上「昨天记的今天补」才对得上 |
| `content` | 用户原话，不做改写 |
| `amount` `category` | 仅记账。金额**必须是独立列**，否则没法 `sum group by` |
| `status` `dueAt` | 仅待办 |
| `tags` `meta` | 标签数组 / 类型专属零散字段（JSON） |
| `deletedAt` | 软删除，留给回收站和将来的同步删除标记 |

两条设计原则：

1. **要聚合的字段做成独立列，只用来展示的塞 `meta`。**
2. **时间统一存 UTC**（`toISOString()`）。SQLite 里时间是 TEXT，按字符串比大小——
   如果混着 `+08:00` 和 `Z` 两种写法，字典序就不等于时间序，查询会错位。展示层再转本地时区。

## 快速捕捉是怎么工作的

输入「午饭 32 元和同事」，`shared/capture.ts` 立刻给出：

```
记账 · ¥32 · 餐饮      记录为支出 ¥32 · 餐饮
```

它是**规则引擎**，不是模型调用。原因：

- 零延迟（敲完就能看见识别结果）、零成本（一天几十条不产生 token 账单）、可离线；
- 可测试：`npm test` 有 13 个用例，跑一次 11ms；
- 可解释：识别错了你一眼能看出是哪条规则，也知道该加什么规则。

判定顺序：显式前缀（`闪念：`/`todo:`）> 金额与支出动词 > 祈使语气 > 篇幅与叙事语气。
识别结果永远可以一键改成别的类型，所以规则不必完美。

大模型留给规则兜不住的模糊语义（例如判不出类型时长文本），那是下一步的事。

## AI 层：不做聊天框

「和 AI 聊我的人生」很酷，但低频、难调、容易幻觉。真正每天有价值的是**定时回顾**：

```
记录 → 聚合统计 → 结构化 prompt → JSON 输出 → 落库 ai_insights
```

- 输出字段固定（`headline / summary / themes / spending / todos / mood / suggestion`），前端直接渲染；
- prompt 里明确要求「只使用记录中的事实、举例引用原话」，压幻觉；
- 失败或没配 Key → 退回本地统计版，页面不会白屏。

`insights` 表存了每次生成的快照（含使用的模型），可回溯「上周 AI 说我什么」。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 服务状态、数据文件路径、模型是否已配置 |
| GET | `/api/entries?from&to&kind&status&q&tag&limit&offset` | 查询记录 |
| POST | `/api/entries` | 新建（携带前端解析好的结构化字段） |
| PATCH | `/api/entries/:id` | 部分更新 |
| DELETE | `/api/entries/:id` | 软删除 |
| POST | `/api/capture` | 传一句话，服务端解析并落库（给脚本 / 快捷指令用） |
| GET | `/api/stats?from&to` | 聚合统计（给未来的原生端，避免拉全量） |
| GET | `/api/insights?scope=daily\|weekly` | 生成回顾 |

```bash
# 命令行记一笔，顺手验证整套链路
curl -X POST http://localhost:8787/api/capture \
  -H 'content-type: application/json' \
  -d '{"text":"午饭 32 元和同事"}'
```

## 已经踩过的坑（别退回去）

1. **四个模块四张表** → 数据割裂，AI 无料可分析。所以只有一张 `entries`。
2. **让用户先选类型** → 记录率掉一半。所以只有一个框，类型靠猜 + 一键改。
3. **时间混用本地/UTC 字符串** → 查询区间错位，某天的记录莫名消失。所以统一 UTC。
4. **没有 Key 就打不开回顾页** → 个人工具通常活不过三天。所以永远有降级路径。

## 下一步（按价值排序）

- [ ] **捕捉页的今日列表**也接上编辑入口（时间线里已经可以改和删了）
- [ ] **向量检索**：条目 embed + sqlite-vec，「我上次说想学吉他是什么时候」
- [ ] **自动聚类**：每周把没标签的闪念聚成 2–3 个主题，提议归档到项目
- [ ] **定时任务**：每天早上自动生成昨日回顾，推到手机
- [ ] **多端**：Expo 原生端（复用 `shared/` 与 REST 契约）
- [ ] **导入**：微信/支付宝账单 CSV、日历事件

## 常用命令

```bash
npm run dev        # 开发（接口 + 前端热更新）
npm run build      # 构建前端到 dist/web
npm start          # 生产模式，单端口 8787
npm test           # 解析器单测
npm run typecheck  # 全项目类型检查
npm run seed       # 灌演示数据（加 --force 追加）
```

备份就是复制 `data/lifeos.db`（以及同目录的 `-wal` 文件）。
