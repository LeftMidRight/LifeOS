/**
 * AI 分析层。
 *
 * 只做一件事：把一段时间内的记录，变成一段「人话总结」。
 * 刻意不做聊天框 —— 聊天是低频需求，且检索质量难保；定时回顾才是每天都会被看见的东西。
 *
 * 没配 API Key 时自动退化成「本地统计版」，保证开箱即用。这是很重要的设计约束：
 * 一个需要先配好 Key 才能用的个人工具，通常活不过三天。
 */
import { nowISO } from '../shared/date.ts';
import type { Entry, Insight, Stats } from '../shared/schema.ts';

const BASE_URL = (process.env.LLM_BASE_URL ?? 'https://api.deepseek.com/v1').replace(/\/+$/, '');
const API_KEY = process.env.LLM_API_KEY ?? '';
const MODEL = process.env.LLM_MODEL ?? 'deepseek-chat';

export function llmStatus() {
  return { configured: Boolean(API_KEY), model: MODEL, baseUrl: BASE_URL };
}

const SYSTEM_PROMPT = `你是 LifeOS 的生活记录分析助手。用户会给你一段时间内的全部记录（JSON 数组）。
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
}`;

interface InsightResult {
  insight: Insight;
  /** 有值说明退化了，前端会显示一行小字 */
  warning: string | null;
}

function compactEntries(entries: Entry[]): Array<Record<string, unknown>> {
  return entries.slice(0, 200).map((e) => {
    const item: Record<string, unknown> = {
      t: e.occurredAt,
      kind: e.kind,
      text: e.content.slice(0, 240),
    };
    if (e.amount != null) item.amount = e.amount;
    if (e.category) item.category = e.category;
    if (e.status) item.status = e.status;
    if (e.dueAt) item.due = e.dueAt;
    if (e.mood != null) item.mood = e.mood;
    if (e.tags.length) item.tags = e.tags;
    return item;
  });
}

function parseJsonLoose(text: string): Record<string, unknown> {
  const cleaned = text
    .replace(/^\s*```(?:json)?/i, '')
    .replace(/```\s*$/, '')
    .trim();
  try {
    return JSON.parse(cleaned) as Record<string, unknown>;
  } catch {
    const start = cleaned.indexOf('{');
    const end = cleaned.lastIndexOf('}');
    if (start >= 0 && end > start) {
      return JSON.parse(cleaned.slice(start, end + 1)) as Record<string, unknown>;
    }
    throw new Error('模型返回的不是合法 JSON');
  }
}

async function callModel(entries: Entry[], stats: Stats, scope: string): Promise<Record<string, unknown>> {
  const payload = {
    scope,
    from: stats.from,
    to: stats.to,
    stats: {
      总记录数: stats.entryCount,
      分类计数: stats.byKind,
      总支出: stats.totalSpent,
      分类支出: stats.byCategory,
      待办: { 进行中: stats.openTodos, 已完成: stats.doneTodos },
      平均心情: stats.avgMood,
    },
    entries: compactEntries(entries),
  };

  const body: Record<string, unknown> = {
    model: MODEL,
    temperature: 0.4,
    messages: [
      { role: 'system', content: SYSTEM_PROMPT },
      { role: 'user', content: JSON.stringify(payload) },
    ],
  };

  const send = async (withJsonMode: boolean): Promise<Response> => {
    const signal = AbortSignal.timeout(90_000);
    return fetch(`${BASE_URL}/chat/completions`, {
      method: 'POST',
      signal,
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${API_KEY}`,
      },
      body: JSON.stringify(withJsonMode ? { ...body, response_format: { type: 'json_object' } } : body),
    });
  };

  let res = await send(true);
  // 有些兼容层不支持 response_format，降级重试一次
  if (res.status === 400) res = await send(false);

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`模型接口返回 ${res.status}：${detail.slice(0, 200)}`);
  }

  const data = (await res.json()) as { choices?: Array<{ message?: { content?: string } }> };
  const content = data.choices?.[0]?.message?.content ?? '';
  if (!content) throw new Error('模型返回为空');
  return parseJsonLoose(content);
}

function str(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

/** 本地统计版摘要：没有 API Key 时的兜底，也用于模型失败时保底 */
function localInsight(stats: Stats, scope: 'daily' | 'weekly'): Insight {
  const rangeLabel = scope === 'daily' ? '今天' : '这周';
  const top = stats.byCategory[0];
  const parts: string[] = [];

  if (stats.entryCount === 0) {
    parts.push(`${rangeLabel}还没有任何记录。`);
  } else {
    parts.push(`${rangeLabel}记了 ${stats.entryCount} 条：` +
      Object.entries(stats.byKind)
        .map(([kind, count]) => `${kindLabel(kind)} ${count}`)
        .join('、') + '。');
  }

  if (stats.totalSpent > 0) {
    const topText = top ? `，其中${top.category}最多（¥${top.total}）` : '';
    parts.push(`花了 ¥${stats.totalSpent}${topText}。`);
  }
  if (stats.openTodos + stats.doneTodos > 0) {
    parts.push(`待办完成 ${stats.doneTodos} / ${stats.openTodos + stats.doneTodos} 条。`);
  }

  return {
    scope,
    from: stats.from,
    to: stats.to,
    headline: stats.entryCount === 0 ? `${rangeLabel}还是空白` : `${rangeLabel}记了 ${stats.entryCount} 条`,
    summary: parts.join(''),
    themes: top ? [`消费集中在${top.category}`] : [],
    spending: stats.totalSpent > 0 ? `共 ¥${stats.totalSpent}${top ? `，${top.category}占大头` : ''}` : '这段时间没有记账',
    todos: stats.openTodos + stats.doneTodos > 0 ? `完成 ${stats.doneTodos}，还剩 ${stats.openTodos}` : '这段时间没有待办',
    mood: stats.avgMood == null ? 'unknown' : stats.avgMood >= 3.6 ? 'up' : stats.avgMood <= 2.4 ? 'down' : 'flat',
    suggestion: stats.openTodos > 3 ? '待办积压了，先挑一件今天能做完的' : '继续记，样本越多越能看出规律',
    model: 'local',
    generatedAt: nowISO(),
  };
}

function kindLabel(kind: string): string {
  const map: Record<string, string> = {
    journal: '日记',
    thought: '闪念',
    expense: '记账',
    todo: '待办',
    habit: '习惯',
    metric: '指标',
  };
  return map[kind] ?? kind;
}

export async function generateInsight(
  entries: Entry[],
  stats: Stats,
  scope: 'daily' | 'weekly',
): Promise<InsightResult> {
  const fallback = localInsight(stats, scope);

  if (!API_KEY) {
    return { insight: fallback, warning: '未配置 LLM_API_KEY，当前是本地统计版摘要' };
  }
  if (entries.length === 0) {
    return { insight: fallback, warning: null };
  }

  try {
    const raw = await callModel(entries, stats, scope);
    const insight: Insight = {
      scope,
      from: stats.from,
      to: stats.to,
      headline: str(raw.headline, fallback.headline),
      summary: str(raw.summary, fallback.summary),
      themes: Array.isArray(raw.themes) ? raw.themes.filter((t): t is string => typeof t === 'string').slice(0, 3) : [],
      spending: str(raw.spending, fallback.spending),
      todos: str(raw.todos, fallback.todos),
      mood: ['up', 'flat', 'down', 'unknown'].includes(str(raw.mood)) ? (raw.mood as Insight['mood']) : 'unknown',
      suggestion: str(raw.suggestion, fallback.suggestion),
      model: MODEL,
      generatedAt: nowISO(),
    };
    return { insight, warning: null };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { insight: fallback, warning: `模型调用失败（${message}），已退回本地统计版` };
  }
}
