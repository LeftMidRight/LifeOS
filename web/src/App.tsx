import { useCallback, useEffect, useState } from 'react';
import type { Entry } from '../../shared/schema.ts';
import { toDayKey } from '../../shared/date.ts';
import { api, type HealthInfo } from './api.ts';
import CaptureView from './components/CaptureView.tsx';
import TimelineView from './components/TimelineView.tsx';
import LedgerView from './components/LedgerView.tsx';
import TodosView from './components/TodosView.tsx';
import ReviewView from './components/ReviewView.tsx';
import DiaryView from './components/DiaryView.tsx';
import { IconBook, IconCheck, IconPen, IconSparkle, IconTimeline, IconWallet } from './components/Icons.tsx';
import type { Notify, ToastAction } from './components/types.ts';

const NAV = [
  { key: 'todos', label: '待办', title: '待办', sub: '只留今天能做掉的事', Icon: IconCheck },
  { key: 'capture', label: '捕捉', title: '捕捉', sub: '一句话，记下此刻', Icon: IconPen },
  { key: 'timeline', label: '时间线', title: '时间线', sub: '所有记录按天排开', Icon: IconTimeline },
  { key: 'diary', label: '日记', title: '日记', sub: '选一天，慢慢写', Icon: IconBook },
  { key: 'ledger', label: '记账', title: '记账', sub: '这个月的钱去哪了', Icon: IconWallet },
  { key: 'review', label: '回顾', title: '回顾', sub: '让 AI 读一遍你的记录', Icon: IconSparkle },
] as const;

type Tab = (typeof NAV)[number]['key'];

interface ToastItem {
  id: number;
  message: string;
  action?: ToastAction;
}

export default function App() {
  const [tab, setTab] = useState<Tab>('todos');
  const [entries, setEntries] = useState<Entry[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);
  const [syncedAt, setSyncedAt] = useState<Date | null>(null);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const notify: Notify = useCallback((message, action) => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev.slice(-2), { id, message, action }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== id));
    }, action ? 6500 : 3000);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const from = new Date(Date.now() - 400 * 86_400_000).toISOString();
      const result = await api.list({ from, limit: 2000 });
      setEntries(result.items);
      setSyncedAt(new Date());
      setStatus('ready');
      setError(null);
    } catch (err) {
      setStatus((prev) => (prev === 'ready' ? 'ready' : 'error'));
      setError(err instanceof Error ? err.message : '无法连接服务');
    }
  }, []);

  useEffect(() => {
    void refresh();
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, [refresh]);

  // 手机和电脑看的是同一份数据。切回页面时拉一次，就不用手动刷新。
  useEffect(() => {
    const onVisible = () => {
      if (!document.hidden) void refresh();
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);
    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
    };
  }, [refresh]);

  const current = NAV.find((item) => item.key === tab) ?? NAV[0];
  const today = toDayKey(new Date());
  const todayCount = entries.filter((entry) => toDayKey(entry.occurredAt) === today).length;
  const openTodos = entries.filter((entry) => entry.kind === 'todo' && entry.status === 'open').length;

  function countFor(key: Tab): number | null {
    if (key === 'capture') return todayCount || null;
    if (key === 'todos') return openTodos || null;
    return null;
  }

  const viewProps = { entries, refresh, notify };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">L</span>
          <div>
            <div className="brand-name">LifeOS</div>
            <div className="brand-sub">personal log</div>
          </div>
        </div>

        <nav className="nav">
          {NAV.map((item) => {
            const count = countFor(item.key);
            return (
              <button
                key={item.key}
                className={`nav-item${tab === item.key ? ' active' : ''}`}
                onClick={() => setTab(item.key)}
              >
                <item.Icon size={17} />
                {item.label}
                {count !== null && <span className="nav-count">{count}</span>}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          {status === 'error' ? (
            <>
              <span className="status-dot off" />
              服务未连接
            </>
          ) : (
            <>
              <span className="status-dot" />
              已连接 · 手机电脑同一份数据
            </>
          )}
          <br />
          {health?.llm.configured ? `模型 · ${health.llm.model}` : '模型未配置（回顾为统计版）'}
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h1 className="page-title">{current.title}</h1>
            <p className="page-sub">{current.sub}</p>
          </div>
          <div className="topbar-right">
            {syncedAt ? `${syncedAt.getHours().toString().padStart(2, '0')}:${syncedAt
              .getMinutes()
              .toString()
              .padStart(2, '0')} 同步` : '连接中…'}
            <br />
            共 {entries.length} 条
          </div>
        </header>

        {status === 'loading' && <div className="empty">正在读取…</div>}

        {status === 'error' && (
          <div className="warning">
            连不上服务：{error}
            <div style={{ marginTop: 10 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => void refresh()}>
                重试
              </button>
            </div>
          </div>
        )}

        {status === 'ready' && (
          <>
            {tab === 'capture' && <CaptureView {...viewProps} />}
            {tab === 'timeline' && <TimelineView {...viewProps} />}
            {tab === 'diary' && <DiaryView {...viewProps} />}
            {tab === 'ledger' && <LedgerView {...viewProps} />}
            {tab === 'todos' && <TodosView {...viewProps} />}
            {tab === 'review' && <ReviewView llmConfigured={health?.llm.configured === true} />}
          </>
        )}
      </main>

      <nav className="tabbar">
        {NAV.map((item) => (
          <button
            key={item.key}
            className={`tab${tab === item.key ? ' active' : ''}`}
            onClick={() => setTab(item.key)}
          >
            <item.Icon size={19} />
            {item.label}
          </button>
        ))}
      </nav>

      <div className="toast-wrap">
        {toasts.map((toast) => (
          <div className="toast" key={toast.id}>
            <span>{toast.message}</span>
            {toast.action && (
              <button
                onClick={() => {
                  void toast.action?.run();
                  setToasts((prev) => prev.filter((item) => item.id !== toast.id));
                }}
              >
                {toast.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
