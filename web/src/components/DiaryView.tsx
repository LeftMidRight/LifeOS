import { useMemo, useState } from 'react';
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

/**
 * 日记视图：一天一篇。
 *
 * 为什么不是「再做一个独立的日记表」：日记在这个系统里就是 kind=journal 的记录，
 * 所以今天在「捕捉」里随手写的一大段话，打开日记页会直接出现，编辑后就是正式日记。
 * 一条流的好处在这里兑现 —— 不需要「导入」「合并」这种动作。
 */
export default function DiaryView({ entries, refresh, notify }: ViewProps) {
  const today = toDayKey(new Date());
  const [dayKey, setDayKey] = useState(today);
  const [editing, setEditing] = useState(false);

  const dayEntries = useMemo(() => entries.filter((entry) => toDayKey(entry.occurredAt) === dayKey), [entries, dayKey]);

  const diary = useMemo(() => {
    const journals = dayEntries.filter((entry) => entry.kind === 'journal');
    if (journals.length === 0) return null;
    return [...journals].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0] ?? null;
  }, [dayEntries]);

  // 日记视图只展示当天的日记；闪念/记账/待办等全部类型在「时间线」查看。
  // 保存成功后不再 await refresh，避免刷新慢时把编辑器卡在「保存中…」。

  function shift(delta: number) {
    const next = toDayKey(addDays(dayDate(dayKey), delta));
    if (next > today) return;
    setDayKey(next);
  }

  async function removeDiary() {
    if (!diary) return;
    try {
      await api.remove(diary.id);
      await refresh();
      notify('日记已删除');
    } catch (error) {
      notify(error instanceof Error ? error.message : '删除失败');
    }
  }

  async function saveDiary(value: string) {
    try {
      if (diary) {
        await api.update(diary.id, { content: value });
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
      // 写入已经成功，先让编辑器关闭；列表刷新放到后台。
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

      {diary ? (
        <article className="diary-paper">
          <div className="diary-meta">
            <span>{formatClock(diary.occurredAt)}</span>
            <span>{diary.content.length} 字</span>
            {diary.updatedAt !== diary.createdAt && <span>已编辑</span>}
          </div>
          <div className="diary-body">{diary.content}</div>
          <div className="diary-actions">
            <button className="btn btn-ghost btn-sm" onClick={() => void removeDiary()}>
              删除
            </button>
            <button className="btn btn-primary btn-sm" onClick={() => setEditing(true)}>
              编辑
            </button>
          </div>
        </article>
      ) : (
        <div className="diary-empty">
          <p className="diary-empty-title">{fullDayLabel(dayKey)}</p>
          <p className="diary-empty-sub">这一天还没有日记。</p>
          <button className="btn btn-primary" onClick={() => setEditing(true)}>
            写这一天
          </button>
        </div>
      )}

      {editing && (
        <DiaryEditor
          dayKey={dayKey}
          dayLabel={fullDayLabel(dayKey)}
          initial={diary?.content ?? ''}
          onClose={() => setEditing(false)}
          onSave={saveDiary}
        />
      )}
    </div>
  );
}
