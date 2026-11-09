import { useCallback, useEffect, useRef, useState } from 'react';
import { formatMoney, relativeTime } from '../../../shared/date.ts';
import { api, type InsightResponse } from '../api.ts';
import { IconRefresh, IconSparkle } from './Icons.tsx';

type Scope = 'daily' | 'weekly';

const MOOD_LABEL: Record<string, string> = {
  up: '状态在往上走',
  flat: '状态比较平稳',
  down: '状态偏低',
  unknown: '看不出来',
};

/**
 * 回顾视图。
 *
 * 这是整个 LifeOS 里 AI 唯一该出现的地方：不是聊天，是「定时把散落的记录收拢成一段判断」。
 * 没配模型时自动退化成统计版摘要，所以这个页面永远有内容。
 */
export default function ReviewView() {
  const [scope, setScope] = useState<Scope>('daily');
  const [data, setData] = useState<InsightResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  const load = useCallback(async (target: Scope) => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const result = await api.insight(target);
      if (id === requestId.current) setData(result);
    } catch (err) {
      if (id === requestId.current) setError(err instanceof Error ? err.message : '生成失败');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(scope);
  }, [scope, load]);

  const insight = data?.insight;
  const stats = data?.stats;

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
            <button className="btn btn-ghost btn-sm" onClick={() => void load(scope)}>
              重试
            </button>
          </div>
        </div>
      )}

      {insight && !loading && (
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

          <div className="review-foot">
            <span>
              {insight.model === 'local' ? '本地统计版' : `模型 · ${insight.model}`} · {relativeTime(insight.generatedAt)}
            </span>
            <button className="btn btn-ghost btn-sm" onClick={() => void load(scope)}>
              <IconRefresh size={14} />
              重新生成
            </button>
          </div>

          {data?.warning && <div className="warning">{data.warning}</div>}
        </>
      )}
    </div>
  );
}
