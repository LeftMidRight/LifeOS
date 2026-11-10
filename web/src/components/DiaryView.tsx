import { useMemo, useState } from 'react';
import type { Entry } from '../../../shared/schema.ts';
import { addDays, formatClock, humanDay, toDayKey, weekdayName } from '../../../shared/date.ts';
import { api } from '../api.ts';
import DiaryEditor from './DiaryEditor.tsx';
import type { ViewProps } from './types.ts';
import { IconChevronLeft, IconChevronRight } from './Icons.tsx';

/** dayKey（YYYY-MM-DD）→ 本地当天 0 点。不能用 new Date('2026-11-09')，那会被当成 UTC。 */
function dayDate(dayKey: string): Date {
  const [y, m, d] = dayKey.split('-').map(Number);
  return new Date(y ?? 1970, (m ?? 1) - 1, d ?? 1);
}

function fullDayLabel(dayKey: string): string {
  const d = dayDate(dayKey);
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${weekdayName(d)}`;
}

/** 编辑器状态：null = 关闭；'new' = 新写一篇；entry = 编辑这一篇 */
type Editing = { mode: 'new' } | { mode: 'edit'; entry: Entry } | null;

/**
 * 日记视图：当天的日记按时间倒序列成记录列表，和「捕捉」是同一种心智模型——
 * 写一篇、保存，它就成为下面的一条记录；一天可以写多篇，每篇都能继续编辑。
 * 日记仍然是 kind=journal 的一条流，不做独立的日记表；全屏编辑器只负责写，保存后立即关闭。
 */
export default function DiaryView({ entries, refresh, notify }: ViewProps) {
  const today = toDayKey(new Date());
  const [dayKey, setDayKey] = useState(today);
  const [editing, setEditing] = useState<Editing>(null);

  const dayEntries = useMemo(() => entries.filter((entry) => toDayKey(entry.occurredAt) === dayKey), [entries, dayKey]);

  const diaries = useMemo(
    () =>
      dayEntries
        .filter((entry) => entry.kind === 'journal')
        .sort((a, b) => b.occurredAt.localeCompare(a.occurredAt) || b.createdAt.localeCompare(a.createdAt)),
    [dayEntries],
  );

  function shift(delta: number) {
    const next = toDayKey(addDays(dayDate(dayKey), delta));
    if (next > today) return;
    setDayKey(next);
  }

  async function removeDiary(entry: Entry) {
    try {
      await api.remove(entry.id);
      await refresh();
      notify('日记已删除');
    } catch (error) {
      notify(error instanceof Error ? error.message : '删除失败');
    }
  }

  async function saveDiary(value: string) {
    const current = editing;
    try {
      if (current?.mode === 'edit') {
        await api.update(current.entry.id, { content: value });
        notify('日记已更新');
      } else {
        const base = dayDate(dayKey);
        const at =
          dayKey === today
            ? new Date()
            : new Date(base.getFullYear(), base.getMonth(), base.getDate(), 21, 0, 0, 0);
        await api.create({
          kind: 'journal',
          content: value,
          occurredAt: at.toISOString(),
          source: 'manual',
          meta: { diary: true },
        });
        notify('日记已保存');
      }
      // 写入已经成功，让编辑器立刻关闭；列表刷新放到后台。
      void refresh();
    } catch (error) {
      notify(error instanceof Error ? error.message : '保存失败');
      throw error;
    }
  }

  return (
    <div>
      <div className="date-bar">
        <button className="icon-btn" onClick={() => shift(-1)} aria-label="前一天">
          <IconChevronLeft size={17} />
        </button>

        <label className="date-label">
          <span className="date-text">{humanDay(dayDate(dayKey))}</span>
          <input
            className="date-input"
            type="date"
            value={dayKey}
            max={today}
            onChange={(event) => {
              if (event.target.value) setDayKey(event.target.value);
            }}
            aria-label="选择日期"
          />
        </label>

        <button
          className="icon-btn"
          onClick={() => shift(1)}
          aria-label="后一天"
          disabled={dayKey >= today}
          style={{ opacity: dayKey >= today ? 0.3 : 1 }}
        >
          <IconChevronRight size={17} />
        </button>

        {dayKey !== today && (
          <button className="btn btn-ghost btn-sm" onClick={() => setDayKey(today)}>
            回到今天
          </button>
        )}
      </div>

      {diaries.length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 18 }}>
          <button className="btn btn-primary" onClick={() => setEditing({ mode: 'new' })}>
            ＋ 写日记
          </button>
        </div>
      )}

      {diaries.length === 0 ? (
        <div className="diary-empty">
          <p className="diary-empty-title">{fullDayLabel(dayKey)}</p>
          <p className="diary-empty-sub">这一天还没有日记。</p>
          <button className="btn btn-primary" onClick={() => setEditing({ mode: 'new' })}>
            写这一天
          </button>
        </div>
      ) : (
        diaries.map((entry) => (
          <article className="diary-paper" key={entry.id}>
            <div className="diary-meta">
              <span>{formatClock(entry.occurredAt)}</span>
              <span>{entry.content.length} 字</span>
              {entry.updatedAt !== entry.createdAt && <span>已编辑</span>}
            </div>
            <div className="diary-body">{entry.content}</div>
            <div className="diary-actions">
              <button className="btn btn-ghost btn-sm" onClick={() => void removeDiary(entry)}>
                删除
              </button>
              <button className="btn btn-primary btn-sm" onClick={() => setEditing({ mode: 'edit', entry })}>
                编辑
              </button>
            </div>
          </article>
        ))
      )}

      {editing && (
        <DiaryEditor
          draftKey={editing.mode === 'edit' ? `lifeos:draft:entry:${editing.entry.id}` : `lifeos:draft:new:${dayKey}`}
          initial={editing.mode === 'edit' ? editing.entry.content : ''}
          dayLabel={fullDayLabel(dayKey)}
          onClose={() => setEditing(null)}
          onSave={saveDiary}
        />
      )}
    </div>
  );
}
