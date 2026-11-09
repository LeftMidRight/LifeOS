/**
 * HTTP 服务层。
 *
 * 骨架选择上是「服务端为唯一真相」：手机、电脑打开的是同一个服务、同一个 SQLite 文件，
 * 所以「同步」这件事在 v0.1 里直接不存在 —— 没有双向同步就没有冲突合并。
 * 将来要换成 Supabase / 多设备离线，只需要替换 repo.ts 的实现。
 */
import Fastify from 'fastify';
import cors from '@fastify/cors';
import fastifyStatic from '@fastify/static';
import { existsSync } from 'node:fs';
import { networkInterfaces } from 'node:os';
import { join, resolve } from 'node:path';
import { z } from 'zod';

import { captureRequestSchema, entryCreateSchema, entryPatchSchema, isoDate, listQuerySchema } from '../shared/schema.ts';
import { parseCapture } from '../shared/capture.ts';
import { dayRange, nowISO, toDayKey, weekRange } from '../shared/date.ts';
import { DB_PATH, closeDb } from './db.ts';
import { createEntry, deleteEntry, getEntry, listEntries, saveInsight, stats, updateEntry } from './repo.ts';
import { generateInsight, llmStatus } from './ai.ts';

const VERSION = '0.1.0';
const PORT = Number(process.env.LIFEOS_PORT ?? 8787);

const app = Fastify({
  logger: { level: process.env.LOG_LEVEL ?? 'info' },
  bodyLimit: 1024 * 1024,
});

await app.register(cors, { origin: true });

app.setErrorHandler((error: unknown, _request, reply) => {
  if (error instanceof z.ZodError) {
    const detail = error.issues.map((i) => `${i.path.join('.') || '参数'}：${i.message}`).join('；');
    return reply.code(400).send({ error: '参数不合法', detail });
  }
  const err = error instanceof Error ? error : new Error(String(error));
  const statusCode = (err as Error & { statusCode?: number }).statusCode;
  const status = typeof statusCode === 'number' && statusCode >= 400 ? statusCode : 500;
  app.log.error({ err }, '请求处理失败');
  return reply.code(status).send({ error: err.message || '服务器内部错误' });
});

app.get('/api/health', async () => ({
  ok: true,
  version: VERSION,
  db: DB_PATH,
  llm: llmStatus(),
  now: nowISO(),
}));

// ── 记录 ──────────────────────────────────────────────
app.get('/api/entries', async (request) => {
  const query = listQuerySchema.parse(request.query);
  const items = listEntries(query);
  return { items, count: items.length };
});

app.get('/api/entries/:id', async (request, reply) => {
  const { id } = z.object({ id: z.string().min(1) }).parse(request.params);
  const entry = getEntry(id);
  if (!entry) return reply.code(404).send({ error: '记录不存在' });
  return entry;
});

app.post('/api/entries', async (request, reply) => {
  const input = entryCreateSchema.parse(request.body ?? {});
  const entry = createEntry(input);
  return reply.code(201).send(entry);
});

app.patch('/api/entries/:id', async (request, reply) => {
  const { id } = z.object({ id: z.string().min(1) }).parse(request.params);
  const patch = entryPatchSchema.parse(request.body ?? {});
  const entry = updateEntry(id, patch);
  if (!entry) return reply.code(404).send({ error: '记录不存在' });
  return entry;
});

app.delete('/api/entries/:id', async (request, reply) => {
  const { id } = z.object({ id: z.string().min(1) }).parse(request.params);
  if (!deleteEntry(id)) return reply.code(404).send({ error: '记录不存在' });
  return reply.code(204).send();
});

// ── 快速捕捉（供脚本 / 快捷指令 / 将来原生端调用）──────────
app.post('/api/capture', async (request, reply) => {
  const { text, at } = captureRequestSchema.parse(request.body ?? {});
  const now = at ? new Date(at) : new Date();
  const parsed = parseCapture(text, now);
  const entry = createEntry({
    kind: parsed.kind,
    content: parsed.content || text,
    occurredAt: now.toISOString(),
    amount: parsed.amount,
    currency: 'CNY',
    category: parsed.category,
    status: parsed.status,
    dueAt: parsed.dueAt,
    tags: parsed.tags,
    meta: { captureNote: parsed.note, confidence: parsed.confidence },
    source: 'capture',
  });
  return reply.code(201).send({ entry, parsed });
});

// ── 统计 ──────────────────────────────────────────────
app.get('/api/stats', async (request) => {
  const query = z
    .object({ from: isoDate, to: isoDate })
    .parse(request.query);
  const range = query.from && query.to ? { from: query.from, to: query.to } : dayRange(toDayKey(new Date()));
  return stats(range.from, range.to);
});

// ── AI 回顾 ───────────────────────────────────────────
app.get('/api/insights', async (request) => {
  const query = z
    .object({
      scope: z.enum(['daily', 'weekly']).default('daily'),
      from: isoDate.optional(),
      to: isoDate.optional(),
    })
    .parse(request.query);

  const range =
    query.from && query.to
      ? { from: query.from, to: query.to }
      : query.scope === 'weekly'
        ? weekRange()
        : dayRange(toDayKey(new Date()));

  const entries = listEntries({ ...range, limit: 2000, offset: 0 });
  const summary = stats(range.from, range.to);
  const result = await generateInsight(entries, summary, query.scope);

  saveInsight(query.scope, range.from, range.to, result.insight.model, result.insight);

  return { ...result, stats: summary };
});

// ── 前端静态资源（生产模式）────────────────────────────
const webRoot = resolve(process.cwd(), 'dist/web');
const hasWebBuild = existsSync(join(webRoot, 'index.html'));

if (hasWebBuild) {
  await app.register(fastifyStatic, { root: webRoot, wildcard: false });
}

app.setNotFoundHandler((request, reply) => {
  if (request.url.startsWith('/api/')) {
    return reply.code(404).send({ error: '接口不存在' });
  }
  if (!hasWebBuild) {
    return reply
      .code(404)
      .type('text/plain; charset=utf-8')
      .send('前端尚未构建。开发模式请用 npm run dev 打开 http://localhost:5173 ，或先执行 npm run build。');
  }

  // fastify/static 在启动时按「当时存在的文件」注册路由。
  // 重新 build 之后新增的 hash 资源不会自动注册，会被 SPA 兜底成 index.html，
  // 浏览器拿到 text/html 当 JS 执行 → 整页白屏。这里补一层磁盘兜底。
  const rawPath = decodeURIComponent(new URL(request.url, 'http://localhost').pathname).replace(/^\/+/, '');
  const candidate = resolve(webRoot, rawPath);

  if (rawPath && /\.[a-z0-9]{2,8}$/i.test(rawPath)) {
    if (candidate.startsWith(webRoot) && existsSync(candidate)) {
      return reply.sendFile(rawPath);
    }
    return reply.code(404).type('text/plain; charset=utf-8').send('静态资源不存在');
  }

  return reply.type('text/html').sendFile('index.html');
});

function lanUrls(port: number): string[] {
  const urls: string[] = [];
  for (const addresses of Object.values(networkInterfaces())) {
    for (const addr of addresses ?? []) {
      if (addr.family === 'IPv4' && !addr.internal) urls.push(`http://${addr.address}:${port}`);
    }
  }
  return urls;
}

await app.listen({ port: PORT, host: '0.0.0.0' });

app.log.info(`LifeOS v${VERSION} 已启动`);
app.log.info(`本机访问   http://localhost:${PORT}`);
for (const url of lanUrls(PORT)) {
  app.log.info(`局域网访问 ${url}   ← 手机用这个（同一 WiFi）`);
}
app.log.info(`数据文件   ${DB_PATH}`);
if (!hasWebBuild) {
  app.log.info('未检测到 dist/web：开发模式请用 npm run dev（前端 5173，接口 8787）');
}

for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.on(signal, async () => {
    app.log.info(`收到 ${signal}，正在关闭`);
    await app.close();
    closeDb();
    process.exit(0);
  });
}
