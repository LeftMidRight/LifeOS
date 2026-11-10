import type { Entry, Insight, Stats } from '../../shared/schema.ts';

const BASE = import.meta.env.VITE_API_BASE ?? '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  });

  if (!res.ok) {
    let message = `请求失败（HTTP ${res.status}）`;
    try {
      const body = (await res.json()) as { error?: string; detail?: string };
      message = body.detail || body.error || message;
    } catch {
      /* 响应不是 JSON，用默认文案 */
    }
    throw new Error(message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface EntryInput {
  kind: Entry['kind'];
  content: string;
  occurredAt?: string;
  amount?: number | null;
  category?: string | null;
  status?: Entry['status'];
  dueAt?: string | null;
  mood?: number | null;
  energy?: number | null;
  tags?: string[];
  source?: Entry['source'];
  meta?: Record<string, unknown>;
}

export interface HealthInfo {
  ok: boolean;
  version: string;
  db: string;
  llm: { configured: boolean; model: string; baseUrl: string };
  now: string;
}

export interface InsightResponse {
  insight: Insight;
  warning: string | null;
  stats: Stats;
}

export type ChatScope = 'daily' | 'weekly';
export type ChatScopeFilter = ChatScope | 'all';

export interface ChatSessionSummary {
  id: string;
  scope: ChatScope;
  periodStart: string;
  periodEnd: string;
  messageCount: number;
  updatedAt: string;
}

export interface ChatSession extends ChatSessionSummary {
  createdAt: string;
  latestSequence: number;
}

export interface ChatMessage {
  id: string;
  sessionId: string;
  sequence: number;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
}

export interface ChatView {
  session: ChatSession | null;
  messages: ChatMessage[];
  hasMore: boolean;
  beforeSequence: number | null;
  insight: Insight | null;
  stats: Stats;
}

export interface ChatPage {
  items: ChatSessionSummary[];
  nextCursor: string | null;
}

export interface ChatSendResult {
  session: ChatSession;
  messages: ChatMessage[];
}

export interface ChatSendInput {
  scope?: ChatScope;
  sessionId?: string;
  message: string;
}

export const api = {
  health: () => request<HealthInfo>('/api/health'),

  list: (params: { from?: string; to?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.from) qs.set('from', params.from);
    if (params.to) qs.set('to', params.to);
    qs.set('limit', String(params.limit ?? 1000));
    return request<{ items: Entry[]; count: number }>(`/api/entries?${qs.toString()}`);
  },

  create: (input: EntryInput) => request<Entry>('/api/entries', { method: 'POST', body: JSON.stringify(input) }),

  update: (id: string, patch: Partial<EntryInput>) =>
    request<Entry>(`/api/entries/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),

  remove: (id: string) => request<void>(`/api/entries/${id}`, { method: 'DELETE' }),

  insight: (scope: 'daily' | 'weekly') => request<InsightResponse>(`/api/insights?scope=${scope}`),

  chatList: (params: { scope?: ChatScopeFilter; limit?: number; cursor?: string } = {}) => {
    const qs = new URLSearchParams();
    qs.set('scope', params.scope ?? 'daily');
    qs.set('limit', String(params.limit ?? 50));
    if (params.cursor) qs.set('cursor', params.cursor);
    return request<ChatPage>(`/api/review-chats?${qs.toString()}`);
  },

  chatCurrent: (scope: ChatScope) =>
    request<ChatView>(`/api/review-chats/current?scope=${scope}`),

  chatSession: (id: string, params: { beforeSequence?: number; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.beforeSequence) qs.set('beforeSequence', String(params.beforeSequence));
    if (params.limit) qs.set('limit', String(params.limit));
    const suffix = qs.size > 0 ? `?${qs.toString()}` : '';
    return request<ChatView>(`/api/review-chats/${encodeURIComponent(id)}${suffix}`);
  },

  sendChat: (input: ChatSendInput) => {
    const body: Record<string, unknown> = { message: input.message };
    if (input.sessionId) body.sessionId = input.sessionId;
    else if (input.scope) body.scope = input.scope;
    return request<ChatSendResult>('/api/review-chats/messages', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  deleteChat: (id: string) =>
    request<void>(`/api/review-chats/${encodeURIComponent(id)}`, { method: 'DELETE' }),
};
