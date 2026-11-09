/**
 * 存储层：node:sqlite（Node 22.5+ 内置，零原生依赖、零编译）。
 *
 * 为什么不是 Postgres/Supabase：v0.1 是单人使用、数据量在十万条以内，
 * 一个文件型 SQLite 就够，且备份 = 复制一个文件。
 * 表结构刻意按「将来能平滑迁到 Postgres」的方式设计：全部是普通列 + TEXT 时间戳。
 */
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';

const dataDir = resolve(process.env.LIFEOS_DATA_DIR ?? 'data');
mkdirSync(dataDir, { recursive: true });

export const DB_PATH = join(dataDir, 'lifeos.db');

export const db = new DatabaseSync(DB_PATH);

db.exec('PRAGMA journal_mode = WAL');
db.exec('PRAGMA synchronous = NORMAL');

db.exec(`
  CREATE TABLE IF NOT EXISTS entries (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    content     TEXT NOT NULL,
    title       TEXT,
    occurred_at TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    amount      REAL,
    currency    TEXT NOT NULL DEFAULT 'CNY',
    category    TEXT,
    status      TEXT,
    due_at      TEXT,
    mood        INTEGER,
    energy      INTEGER,
    tags        TEXT NOT NULL DEFAULT '[]',
    meta        TEXT NOT NULL DEFAULT '{}',
    source      TEXT NOT NULL DEFAULT 'manual',
    deleted_at  TEXT
  );

  CREATE INDEX IF NOT EXISTS idx_entries_occurred ON entries (occurred_at DESC);
  CREATE INDEX IF NOT EXISTS idx_entries_kind     ON entries (kind, occurred_at DESC);
  CREATE INDEX IF NOT EXISTS idx_entries_status   ON entries (status, due_at);

  CREATE TABLE IF NOT EXISTS ai_insights (
    id           TEXT PRIMARY KEY,
    scope        TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end   TEXT NOT NULL,
    model        TEXT NOT NULL,
    payload      TEXT NOT NULL,
    created_at   TEXT NOT NULL
  );

  CREATE INDEX IF NOT EXISTS idx_insights_period ON ai_insights (scope, period_start DESC);
`);

export function closeDb(): void {
  db.close();
}
