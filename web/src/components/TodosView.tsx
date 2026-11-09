import { useMemo } from 'react';
import type { Entry } from '../../../shared/schema.ts';
import { humanDay } from '../../../shared/date.ts';
import { api } from '../api.ts';
import type { ViewProps } from './types.ts';
import { IconCheck, IconTrash } from './Icons.tsx';

function dueInfo(entry: Entry): { text: string; overdue: boolean } | null {
  if (!entry.dueAt) return null;
  const due = new Date(entry.dueAt);
  const overdue = entry.status === 'open' && due.getTime() < Date.now();
  return { text: humanDay(entry.dueAt), overdue };
}

/** 待办视图。刻意只保留「今天能做掉的事」这一个心智模型，不做项目 / 看板 / 优先级。 */
export default function TodosView({ entries, refresh, notify }: ViewProps) {
  const { open, done } = useMemo(() => {
    const todos = entries.filter((entry) => entry.kind === 'todo');
    const openList = todos
      .filter((entry) => entry.status === 'open')
      .sort((a, b) => {
        const aDue = a.dueAt ? new Date(a.dueAt).getTime() : Number.MAX_SAFE_INTEGER;
        const bDue = b.dueAt ? new Date(b.dueAt).getTime() : Number.MAX_SAFE_INTEGER;
        if (aDue !== bDue) return aDue - bDue;
        return b.occurredAt.localeCompare(a.occurredAt);
      });
    const doneList = todos
      .filter((entry) => entry.status === 'done')
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, 20);
    return { open: openList, done: doneList };
  }, [entries]);

  async function toggle(entry: Entry) {
    try {
      await api.update(entry.id, { status: entry.status === 'done' ? 'open' : 'done' });
      await refresh();
    } catch (error) {
      notify(error instanceof Error ? error.message : '更新失败');
    }
  }

  async function remove(entry: Entry) {
    try {
      await api.remove(entry.id);
      await refresh();
      notify('已删除');
    } catch (error) {
      notify(error instanceof Error ? error.message : '删除失败');
    }
  }

  return (
    <div>
      {open.length === 0 && done.length === 0 && (
        <div className="empty">
          还没有待办。
          <br />
          在「捕捉」里写「记得明天交房租」，会自动落到这里。
        </div>
      )}

      {open.length > 0 && (
        <div className="todo-group">
          <h2 className="section-title">进行中 · {open.length}</h2>
          {open.map((entry) => {
            const info = dueInfo(entry);
            return (
              <div className="todo-row" key={entry.id}>
                <button className="checkbox" onClick={() => void toggle(entry)} aria-label="标记完成" />
                <div>
                  <div className="todo-text">{entry.content}</div>
                  <div className="todo-due">
                    {info ? (
                      <span className={info.overdue ? 'overdue' : undefined}>
                        {info.overdue ? '已逾期 · ' : '截止 '}
                        {info.text}
                      </span>
                    ) : (
                      '没有截止时间'
                    )}
                    {entry.tags.length > 0 && ` · ${entry.tags.map((tag) => `#${tag}`).join(' ')}`}
                  </div>
                </div>
                <button className="icon-btn danger" onClick={() => void remove(entry)} aria-label="删除">
                  <IconTrash size={15} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {done.length > 0 && (
        <div className="todo-group">
          <h2 className="section-title">已完成 · {done.length}</h2>
          {done.map((entry) => {
            const info = dueInfo(entry);
            return (
              <div className="todo-row done" key={entry.id}>
                <button className="checkbox checked" onClick={() => void toggle(entry)} aria-label="取消完成">
                  <IconCheck size={12} />
                </button>
                <div>
                  <div className="todo-text">{entry.content}</div>
                  {info && <div className="todo-due">{info.text}</div>}
                </div>
                <button className="icon-btn danger" onClick={() => void remove(entry)} aria-label="删除">
                  <IconTrash size={15} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
