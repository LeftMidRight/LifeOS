import { useCallback, useEffect, useRef, useState } from 'react';
import { formatMoney, relativeTime, toDayKey } from '../../../shared/date.ts';
import type {
  ChatMessage,
  ChatScope,
  ChatScopeFilter,
  ChatSessionSummary,
  ChatView,
  InsightResponse,
} from '../api.ts';
import { api } from '../api.ts';
import { IconRefresh, IconSparkle } from './Icons.tsx';

type Scope = ChatScope;

interface ReviewData {
  insight: InsightResponse['insight'] | null;
  stats: InsightResponse['stats'];
  warning: string | null;
}

const MOOD_LABEL: Record<string, string> = {
  up: '状态在往上走',
  flat: '状态比较平稳',
  down: '状态偏低',
  unknown: '看不出来',
};

const HISTORY_FILTERS: { key: ChatScopeFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'daily', label: '日回顾' },
  { key: 'weekly', label: '周回顾' },
];

function mergeMessages(previous: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const byId = new Map<string, ChatMessage>();
  for (const message of [...previous, ...incoming]) byId.set(message.id, message);
  return [...byId.values()].sort((a, b) => a.sequence - b.sequence);
}

function periodLabel(summary: ChatSessionSummary): string {
  const kind = summary.scope === 'daily' ? '日回顾' : '周回顾';
  // periodStart 是 UTC 边界；按浏览器本地日期展示，避免 UTC+ 时区显示成前一天。
  return `${toDayKey(new Date(summary.periodStart))} · ${kind} · ${summary.messageCount} 条消息`;
}

interface Props {
  /** 后端 health 明确返回已配置模型时才能发送；未知状态一律按未配置处理。 */
  llmConfigured: boolean;
}

/**
 * 回顾视图。
 *
 * 上半部分是 AI 对一段时间记录的收拢判断；下半部分是这个周期的对话。
 * 日/周各自独立记忆，服务端长期保存，可从历史列表重新打开并继续聊。
 */
export default function ReviewView({ llmConfigured }: Props) {
  const [scope, setScope] = useState<Scope>('daily');
  const [data, setData] = useState<ReviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [chat, setChat] = useState<ChatView | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [loadingEarlier, setLoadingEarlier] = useState(false);

  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const [history, setHistory] = useState<ChatSessionSummary[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [historyFilter, setHistoryFilter] = useState<ChatScopeFilter>('all');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<ChatSessionSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const requestId = useRef(0);
  const historyRequestId = useRef(0);
  const messageEndRef = useRef<HTMLDivElement>(null);

  const loadHistory = useCallback(async (filter: ChatScopeFilter) => {
    const id = ++historyRequestId.current;
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const page = await api.chatList({ scope: filter, limit: 20 });
      if (id !== historyRequestId.current) return;
      setHistory(page.items);
      setHistoryCursor(page.nextCursor);
    } catch (err) {
      if (id !== historyRequestId.current) return;
      setHistoryError(err instanceof Error ? err.message : '读取历史会话失败');
    } finally {
      if (id === historyRequestId.current) setHistoryLoading(false);
    }
  }, []);

  const loadCurrent = useCallback(async (target: Scope) => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    setChatLoading(true);
    setChatError(null);
    setSelectedSessionId(null);
    setSendError(null);
    setChat(null);
    try {
      // 先刷新本周期摘要快照，再读取只读的当前聊天，保证对话上下文和页面摘要一致。
      const result = await api.insight(target);
      if (id !== requestId.current) return;
      setData(result);
      const view = await api.chatCurrent(target);
      if (id !== requestId.current) return;
      setChat(view);
    } catch (err) {
      if (id !== requestId.current) return;
      setError(err instanceof Error ? err.message : '生成失败');
    } finally {
      if (id === requestId.current) {
        setLoading(false);
        setChatLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadCurrent(scope);
  }, [scope, loadCurrent]);

  useEffect(() => {
    void loadHistory(historyFilter);
  }, [historyFilter, loadHistory]);

  useEffect(() => {
    // 只滚动消息容器内部，避免整页跳动。
    messageEndRef.current?.scrollIntoView({ block: 'end' });
  }, [chat?.messages.length]);

  const insight = data?.insight;
  const stats = data?.stats;

  async function selectSession(sessionId: string) {
    const id = ++requestId.current;
    setChatLoading(true);
    setChatError(null);
    setSendError(null);
    try {
      const view = await api.chatSession(sessionId, { limit: 100 });
      if (id !== requestId.current) return;
      setChat(view);
      setSelectedSessionId(sessionId);
      setData({
        insight: view.insight,
        stats: view.stats,
        warning: null,
      });
    } catch (err) {
      if (id !== requestId.current) return;
      setChatError(err instanceof Error ? err.message : '读取会话失败');
    } finally {
      if (id === requestId.current) setChatLoading(false);
    }
  }

  async function loadEarlier() {
    if (!chat?.session || chat.beforeSequence === null || loadingEarlier) return;
    const id = requestId.current;
    setLoadingEarlier(true);
    setChatError(null);
    try {
      const view = await api.chatSession(chat.session.id, {
        beforeSequence: chat.beforeSequence,
        limit: 100,
      });
      if (id !== requestId.current) return;
      setChat((previous) =>
        previous === null
          ? view
          : {
              ...previous,
              messages: mergeMessages(view.messages, previous.messages),
              hasMore: view.hasMore,
              beforeSequence: view.beforeSequence,
            },
      );
    } catch (err) {
      setChatError(err instanceof Error ? err.message : '加载更早消息失败');
    } finally {
      setLoadingEarlier(false);
    }
  }

  async function send() {
    const text = draft.trim();
    if (!text || sending || !llmConfigured) return;
    const id = requestId.current;
    setSending(true);
    setSendError(null);
    try {
      const result = selectedSessionId
        ? await api.sendChat({ sessionId: selectedSessionId, message: text })
        : await api.sendChat({ scope, message: text });
      // 发送期间用户可能切换了周期或历史会话；旧响应不能污染新视图。
      if (id !== requestId.current) return;
      setChat((previous) => ({
        session: result.session,
        messages: mergeMessages(previous?.messages ?? [], result.messages),
        hasMore: previous?.hasMore ?? false,
        beforeSequence: previous?.beforeSequence ?? null,
        insight: previous?.insight ?? null,
        stats: previous?.stats ?? (data?.stats as ChatView['stats']),
      }));
      setDraft('');
      void loadHistory(historyFilter);
    } catch (err) {
      setSendError(err instanceof Error ? err.message : '发送失败');
    } finally {
      setSending(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setDeleteError(null);
    const targetId = deleteTarget.id;
    try {
      await api.deleteChat(targetId);
      setDeleteTarget(null);
      await loadHistory(historyFilter);
      if (chat?.session?.id === targetId) {
        await loadCurrent(scope);
      }
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : '删除失败');
    } finally {
      setDeleting(false);
    }
  }

  function requestDelete(summary: ChatSessionSummary) {
    setDeleteError(null);
    setDeleteTarget(summary);
  }

  const canSend = llmConfigured && !sending && draft.trim().length > 0;

  return (
    <div>
      <div className="segmented">
        <button className={scope === 'daily' ? 'active' : ''} onClick={() => setScope('daily')}>
          今天
        </button>
        <button className={scope === 'weekly' ? 'active' : ''} onClick={() => setScope('weekly')}>
          本周
        </button>
      </div>

      {loading && (
        <div className="empty" style={{ marginTop: 20 }}>
          正在读你的记录…
        </div>
      )}

      {error && !loading && (
        <div className="warning" style={{ marginTop: 20 }}>
          {error}
          <div style={{ marginTop: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => void loadCurrent(scope)}>
              重试
            </button>
          </div>
        </div>
      )}

      {data && !loading && (
        <>
          {insight ? (
            <>
              <div className="review-hero" style={{ marginTop: 20 }}>
                <h2 className="review-headline">{insight.headline}</h2>
                <p className="review-summary">{insight.summary}</p>
                {insight.themes.length > 0 && (
                  <div className="theme-list">
                    {insight.themes.map((theme) => (
                      <span className="theme" key={theme}>
                        {theme}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid-3">
                <div className="stat-card">
                  <p className="stat-label">花钱</p>
                  <p className="stat-text">
                    {formatMoney(stats?.totalSpent ?? 0)}
                    <br />
                    {insight.spending}
                  </p>
                </div>
                <div className="stat-card">
                  <p className="stat-label">待办</p>
                  <p className="stat-text">
                    {stats ? `完成 ${stats.doneTodos} · 未完成 ${stats.openTodos}` : '—'}
                    <br />
                    {insight.todos}
                  </p>
                </div>
                <div className="stat-card">
                  <p className="stat-label">状态</p>
                  <p className="stat-text">
                    {MOOD_LABEL[insight.mood] ?? '看不出来'}
                    <br />
                    共 {stats?.entryCount ?? 0} 条记录
                  </p>
                </div>
              </div>

              <div className="suggestion">
                <IconSparkle size={17} />
                <p>{insight.suggestion}</p>
              </div>
            </>
          ) : (
            <div className="warning" style={{ marginTop: 20 }}>
              这个周期没有保存的回顾摘要，只能查看聊天记录。
            </div>
          )}

          <div className="review-foot">
            <span>
              {insight
                ? `${insight.model === 'local' ? '本地统计版' : `模型 · ${insight.model}`} · ${relativeTime(insight.generatedAt)}`
                : `共 ${stats?.entryCount ?? 0} 条记录`}
            </span>
            {!selectedSessionId && (
              <button className="btn btn-ghost btn-sm" onClick={() => void loadCurrent(scope)}>
                <IconRefresh size={14} />
                重新生成
              </button>
            )}
          </div>

          {data.warning && <div className="warning">{data.warning}</div>}
        </>
      )}

      <section className="chat-panel" aria-label="回顾聊天">
        <div className="chat-panel-head">
          <div>
            <h3 className="chat-title">
              {selectedSessionId ? '历史回顾对话' : scope === 'daily' ? '今天聊聊' : '这周聊聊'}
            </h3>
            <p className="chat-privacy">
              聊天会把本周期的记录和对话发送到已配置的模型服务。
            </p>
          </div>
          {selectedSessionId && (
            <button className="btn btn-ghost btn-sm" onClick={() => void loadCurrent(scope)}>
              回到当前
            </button>
          )}
        </div>

        {chatError && <div className="warning">{chatError}</div>}

        {chatLoading && <div className="empty">正在读取对话…</div>}

        {!chatLoading && chat && (
          <div className="chat-messages" aria-live="polite">
            {chat.hasMore && chat.beforeSequence !== null && (
              <button
                className="btn btn-ghost btn-sm chat-more"
                onClick={() => void loadEarlier()}
                disabled={loadingEarlier}
              >
                {loadingEarlier ? '加载中…' : '加载更早消息'}
              </button>
            )}

            {chat.messages.length === 0 && (
              <p className="chat-empty">
                这个周期还没有对话。问问 AI 这段时间有什么值得注意的。
              </p>
            )}

            {chat.messages.map((message) => (
              <div
                className={`chat-message chat-message-${message.role}`}
                key={message.id}
                data-testid="chat-message"
              >
                {message.content}
              </div>
            ))}
            <div ref={messageEndRef} />
          </div>
        )}

        {!llmConfigured && (
          <div className="warning">未配置模型，暂时不能对话；你仍可以查看历史回顾。</div>
        )}

        {sendError && <div className="warning">{sendError}</div>}

        <div className="chat-compose">
          <textarea
            className="textarea chat-input"
            aria-label="聊天输入"
            placeholder={
              llmConfigured
                ? '问点什么… Enter 发送，Shift+Enter 换行'
                : '配置 LIFEOS_LLM_API_KEY 后即可对话'
            }
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void send();
              }
            }}
            disabled={!llmConfigured || sending}
            rows={3}
          />
          <button className="btn btn-primary btn-sm" onClick={() => void send()} disabled={!canSend}>
            {sending ? '发送中…' : '发送'}
          </button>
        </div>
      </section>

      <section className="chat-history" aria-label="历史回顾">
        <div className="chat-history-head">
          <h3 className="chat-title">历史回顾</h3>
          <div className="segmented segmented-sm">
            {HISTORY_FILTERS.map((filter) => (
              <button
                key={filter.key}
                className={historyFilter === filter.key ? 'active' : ''}
                onClick={() => setHistoryFilter(filter.key)}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>

        {historyError && <div className="warning">{historyError}</div>}

        {history.length === 0 && !historyLoading && (
          <p className="chat-empty">还没有保存过的回顾对话。</p>
        )}

        <ul className="chat-history-list">
          {history.map((summary) => (
            <li key={summary.id} className="chat-history-item">
              <button
                className="chat-history-open"
                onClick={() => void selectSession(summary.id)}
                aria-current={chat?.session?.id === summary.id ? 'true' : undefined}
              >
                <span>{periodLabel(summary)}</span>
                <span className="chat-history-time">{relativeTime(summary.updatedAt)}</span>
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => requestDelete(summary)}
                aria-label="删除会话"
                disabled={sending || deleting}
              >
                删除
              </button>
            </li>
          ))}
        </ul>

        {historyCursor && (
          <button
            className="btn btn-ghost btn-sm"
            disabled={historyLoading}
            onClick={async () => {
              const id = ++historyRequestId.current;
              setHistoryLoading(true);
              try {
                const page = await api.chatList({
                  scope: historyFilter,
                  limit: 20,
                  cursor: historyCursor,
                });
                if (id !== historyRequestId.current) return;
                setHistory((previous) => [...previous, ...page.items]);
                setHistoryCursor(page.nextCursor);
              } catch (err) {
                if (id !== historyRequestId.current) return;
                setHistoryError(err instanceof Error ? err.message : '加载更多失败');
              } finally {
                if (id === historyRequestId.current) setHistoryLoading(false);
              }
            }}
          >
            {historyLoading ? '加载中…' : '加载更多'}
          </button>
        )}
      </section>

      {deleteTarget && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget && !deleting) setDeleteTarget(null);
          }}
        >
          <div
            className="modal modal-confirm"
            role="dialog"
            aria-modal="true"
            aria-label="删除这段回顾对话"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-head">
              <h2>删除这段回顾对话？</h2>
            </div>
            <div className="modal-body">
              <p>删除后聊天记录会从服务器移除，但不会删除日记、记账或回顾摘要。</p>
              <p className="modal-preview">{periodLabel(deleteTarget)}</p>
              {deleteError && <div className="warning">{deleteError}</div>}
            </div>
            <div className="modal-foot">
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
              >
                取消
              </button>
              <button
                className="btn btn-danger btn-sm"
                onClick={() => void confirmDelete()}
                disabled={deleting}
              >
                {deleting ? '删除中…' : '删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
