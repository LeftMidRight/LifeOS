/**
 * 全项目共享的数据模型。
 *
 * 设计要点：所有记录都是「某个时刻发生的一件事」，落在同一张 entries 表里。
 * kind 只决定「有哪些结构化字段」「在哪个视图里展示」，不是四张独立的表。
 * 这是让 AI 能跨领域分析的前提。
 */
import { z } from 'zod';

export const KINDS = ['journal', 'thought', 'expense', 'todo', 'habit', 'metric'] as const;
export type Kind = (typeof KINDS)[number];

export const KIND_LABEL: Record<Kind, string> = {
  journal: '日记',
  thought: '闪念',
  expense: '记账',
  todo: '待办',
  habit: '习惯',
  metric: '指标',
};

export const SOURCES = ['manual', 'capture', 'import', 'api'] as const;
export type Source = (typeof SOURCES)[number];

export const CATEGORIES = ['餐饮', '交通', '购物', '住房', '娱乐', '医疗', '学习', '其他'] as const;
export type Category = (typeof CATEGORIES)[number];

export const TODO_STATUS = ['open', 'done', 'dropped'] as const;
export type TodoStatus = (typeof TODO_STATUS)[number];

export interface Entry {
  id: string;
  kind: Kind;
  /** 主体文本。用户的原始表达，不做删改。 */
  content: string;
  title: string | null;
  /** 事件发生时间（≠ 创建时间）。ISO 8601，带时区偏移。 */
  occurredAt: string;
  createdAt: string;
  updatedAt: string;
  /** 仅 expense：金额。必须独立成列，否则无法聚合。 */
  amount: number | null;
  currency: string;
  category: string | null;
  /** 仅 todo */
  status: TodoStatus | null;
  dueAt: string | null;
  mood: number | null;
  energy: number | null;
  tags: string[];
  /** 类型专属的零散字段，不参与查询 */
  meta: Record<string, unknown>;
  source: Source;
}

/** 宽松但严格的 ISO 8601 校验（必须带时区，避免「本地时间」歧义） */
export const isoDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})$/, '需要带时区的 ISO 8601 时间');

export const entryCreateSchema = z.object({
  kind: z.enum(KINDS),
  content: z.string().trim().min(1, '内容不能为空').max(20_000),
  occurredAt: isoDate.optional(),
  title: z.string().max(200).nullish(),
  amount: z.number().finite().nonnegative().nullish(),
  currency: z.string().trim().length(3).default('CNY'),
  category: z.string().trim().max(20).nullish(),
  status: z.enum(TODO_STATUS).nullish(),
  dueAt: isoDate.nullish(),
  mood: z.number().int().min(1).max(5).nullish(),
  energy: z.number().int().min(1).max(5).nullish(),
  tags: z.array(z.string().trim().min(1).max(30)).max(20).default([]),
  meta: z.record(z.unknown()).default({}),
  source: z.enum(SOURCES).default('manual'),
});

export type EntryCreate = z.infer<typeof entryCreateSchema>;

/** 部分更新：每个字段都必须显式可选，且不能带 default（否则会把旧值刷成默认值） */
export const entryPatchSchema = z.object({
  kind: z.enum(KINDS).optional(),
  content: z.string().trim().min(1).max(20_000).optional(),
  occurredAt: isoDate.optional(),
  title: z.string().max(200).nullish(),
  amount: z.number().finite().nonnegative().nullish(),
  currency: z.string().trim().length(3).optional(),
  category: z.string().trim().max(20).nullish(),
  status: z.enum(TODO_STATUS).nullish(),
  dueAt: isoDate.nullish(),
  mood: z.number().int().min(1).max(5).nullish(),
  energy: z.number().int().min(1).max(5).nullish(),
  tags: z.array(z.string().trim().min(1).max(30)).max(20).optional(),
  meta: z.record(z.unknown()).optional(),
});

export type EntryPatch = z.infer<typeof entryPatchSchema>;

export const captureRequestSchema = z.object({
  text: z.string().trim().min(1, '内容不能为空').max(20_000),
  /** 由客户端指定「现在」，保证解析出的时间用的是客户端本地时区 */
  at: isoDate.optional(),
});

export const listQuerySchema = z.object({
  from: isoDate.optional(),
  to: isoDate.optional(),
  kind: z.enum(KINDS).optional(),
  status: z.enum(TODO_STATUS).optional(),
  q: z.string().trim().max(200).optional(),
  tag: z.string().trim().max(30).optional(),
  limit: z.coerce.number().int().min(1).max(2000).default(500),
  offset: z.coerce.number().int().min(0).default(0),
});

export type ListQuery = z.infer<typeof listQuerySchema>;

/** 聚合统计。放在 shared 层是因为前端和后端都要用它，它属于「接口契约」而不是实现细节。 */
export interface Stats {
  from: string;
  to: string;
  totalSpent: number;
  byCategory: Array<{ category: string; total: number; count: number }>;
  byKind: Record<string, number>;
  openTodos: number;
  doneTodos: number;
  avgMood: number | null;
  entryCount: number;
}

/** AI 回顾的结构化输出。字段固定，方便前端直接渲染，也方便入库。 */export interface Insight {
  scope: 'daily' | 'weekly';
  from: string;
  to: string;
  headline: string;
  summary: string;
  themes: string[];
  spending: string;
  todos: string;
  mood: 'up' | 'flat' | 'down' | 'unknown';
  suggestion: string;
  model: string;
  generatedAt: string;
}
