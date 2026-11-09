/**
 * 仓储层（Repository）。
 *
 * 这是「将来换存储只改一层」的那一层：上层 API 只认这里的函数签名，
 * 不关心底下是 SQLite、Postgres 还是 Supabase。
 */
import { randomUUID } from 'node:crypto';
import { db } from './db.ts';
import { nowISO } from '../shared/date.ts';
import type { Entry, EntryCreate, EntryPatch, ListQuery, Stats } from '../shared/schema.ts';

interface Row {
  id: string;
  kind: string;
  content: string;
  title: string | null;
  occurred_at: string;
  created_at: string;
  updated_at: string;
  amount: number | null;
  currency: string;
  category: string | null;
  status: string | null;
  due_at: string | null;
  mood: number | null;
  energy: number | null;
  tags: string;
  meta: string;
  source: string;
  deleted_at: string | null;
}

function safeJSON<T>(raw: string, fallback: T): T {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function rowToEntry(row: Row): Entry {
  return {
    id: row.id,
    kind: row.kind as Entry['kind'],
    content: row.content,
    title: row.title,
    occurredAt: row.occurred_at,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    amount: row.amount,
    currency: row.currency,
    category: row.category,
    status: row.status as Entry['status'],
    dueAt: row.due_at,
    mood: row.mood,
    energy: row.energy,
    tags: safeJSON<string[]>(row.tags, []),
    meta: safeJSON<Record<string, unknown>>(row.meta, {}),
    source: row.source as Entry['source'],
  };
}

export function createEntry(input: EntryCreate): Entry {
  const now = nowISO();
  const row: Row = {
    id: randomUUID(),
    kind: input.kind,
    content: input.content,
    title: input.title ?? null,
    occurred_at: input.occurredAt ?? now,
    created_at: now,
    updated_at: now,
    amount: input.amount ?? null,
    currency: input.currency,
    category: input.category ?? null,
    status: input.status ?? (input.kind === 'todo' ? 'open' : null),
    due_at: input.dueAt ?? null,
    mood: input.mood ?? null,
    energy: input.energy ?? null,
    tags: JSON.stringify(input.tags),
    meta: JSON.stringify(input.meta),
    source: input.source,
    deleted_at: null,
  };

  db.prepare(
    `INSERT INTO entries
      (id, kind, content, title, occurred_at, created_at, updated_at, amount, currency, category, status, due_at, mood, energy, tags, meta, source)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    row.id,
    row.kind,
    row.content,
    row.title,
    row.occurred_at,
    row.created_at,
    row.updated_at,
    row.amount,
    row.currency,
    row.category,
    row.status,
    row.due_at,
    row.mood,
    row.energy,
    row.tags,
    row.meta,
    row.source,
  );

  return rowToEntry(row);
}

const PATCH_COLUMNS: Record<keyof EntryPatch, string> = {
  kind: 'kind',
  content: 'content',
  occurredAt: 'occurred_at',
  title: 'title',
  amount: 'amount',
  currency: 'currency',
  category: 'category',
  status: 'status',
  dueAt: 'due_at',
  mood: 'mood',
  energy: 'energy',
  tags: 'tags',
  meta: 'meta',
};

export function getEntry(id: string): Entry | null {
  const row = db.prepare('SELECT * FROM entries WHERE id = ? AND deleted_at IS NULL').get(id) as Row | undefined;
  return row ? rowToEntry(row) : null;
}

export function updateEntry(id: string, patch: EntryPatch): Entry | null {
  const sets: string[] = [];
  const values: Array<string | number | null> = [];

  for (const [key, column] of Object.entries(PATCH_COLUMNS) as Array<[keyof EntryPatch, string]>) {
    const value = patch[key];
    if (value === undefined) continue;
    sets.push(`${column} = ?`);
    if (key === 'tags') values.push(JSON.stringify(value));
    else if (key === 'meta') values.push(JSON.stringify(value));
    else values.push(value as string | number | null);
  }

  if (sets.length === 0) return getEntry(id);

  sets.push('updated_at = ?');
  values.push(nowISO());

  const result = db.prepare(`UPDATE entries SET ${sets.join(', ')} WHERE id = ? AND deleted_at IS NULL`).run(...values, id);
  return Number(result.changes) > 0 ? getEntry(id) : null;
}

/** 软删除：保留数据，将来做「回收站」和同步删除标记都靠它 */
export function deleteEntry(id: string): boolean {
  const result = db.prepare('UPDATE entries SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL').run(
    nowISO(),
    nowISO(),
    id,
  );
  return Number(result.changes) > 0;
}

export function listEntries(query: ListQuery): Entry[] {
  const where: string[] = ['deleted_at IS NULL'];
  const values: Array<string | number> = [];

  if (query.from) {
    where.push('occurred_at >= ?');
    values.push(query.from);
  }
  if (query.to) {
    where.push('occurred_at < ?');
    values.push(query.to);
  }
  if (query.kind) {
    where.push('kind = ?');
    values.push(query.kind);
  }
  if (query.status) {
    where.push('status = ?');
    values.push(query.status);
  }
  if (query.q) {
    where.push('content LIKE ?');
    values.push(`%${query.q}%`);
  }
  if (query.tag) {
    where.push('tags LIKE ?');
    values.push(`%"${query.tag}"%`);
  }

  const rows = db
    .prepare(`SELECT * FROM entries WHERE ${where.join(' AND ')} ORDER BY occurred_at DESC LIMIT ? OFFSET ?`)
    .all(...values, query.limit, query.offset) as unknown as Row[];

  return rows.map(rowToEntry);
}

export function stats(from: string, to: string): Stats {
  const rows = db
    .prepare("SELECT kind, category, amount, status, mood FROM entries WHERE deleted_at IS NULL AND occurred_at >= ? AND occurred_at < ?")
    .all(from, to) as unknown as Array<{ kind: string; category: string | null; amount: number | null; status: string | null; mood: number | null }>;

  const byKind: Record<string, number> = {};
  const catMap = new Map<string, { total: number; count: number }>();
  let totalSpent = 0;
  let openTodos = 0;
  let doneTodos = 0;
  let moodSum = 0;
  let moodCount = 0;

  for (const row of rows) {
    byKind[row.kind] = (byKind[row.kind] ?? 0) + 1;
    if (row.kind === 'expense') {
      const amount = row.amount ?? 0;
      totalSpent += amount;
      const key = row.category ?? '其他';
      const cur = catMap.get(key) ?? { total: 0, count: 0 };
      cur.total += amount;
      cur.count += 1;
      catMap.set(key, cur);
    }
    if (row.kind === 'todo') {
      if (row.status === 'done') doneTodos += 1;
      else if (row.status === 'open') openTodos += 1;
    }
    if (row.mood != null) {
      moodSum += row.mood;
      moodCount += 1;
    }
  }

  return {
    from,
    to,
    totalSpent: Math.round(totalSpent * 100) / 100,
    byCategory: [...catMap.entries()]
      .map(([category, v]) => ({ category, total: Math.round(v.total * 100) / 100, count: v.count }))
      .sort((a, b) => b.total - a.total),
    byKind,
    openTodos,
    doneTodos,
    avgMood: moodCount ? Math.round((moodSum / moodCount) * 10) / 10 : null,
    entryCount: rows.length,
  };
}

export function saveInsight(scope: string, from: string, to: string, model: string, payload: unknown): void {
  db.prepare('INSERT INTO ai_insights (id, scope, period_start, period_end, model, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)').run(
    randomUUID(),
    scope,
    from,
    to,
    model,
    JSON.stringify(payload),
    nowISO(),
  );
}

export function latestInsight(scope: string): Record<string, unknown> | null {
  const row = db.prepare('SELECT payload FROM ai_insights WHERE scope = ? ORDER BY created_at DESC LIMIT 1').get(scope) as
    | { payload: string }
    | undefined;
  return row ? safeJSON<Record<string, unknown>>(row.payload, {}) : null;
}
