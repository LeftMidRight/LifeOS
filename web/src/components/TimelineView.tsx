import { useMemo, useState } from 'react';
import type { Entry, Kind } from '../../../shared/schema.ts';
import { humanDay, toDayKey } from '../../../shared/date.ts';
import { api } from '../api.ts';
import EntryItem from './EntryItem.tsx';
import EntryEditor from './EntryEditor.tsx';
import type { ViewProps } from './types.ts';
import { IconSearch } from './Icons.tsx';

const FILTERS: Array<{ key: 'all' | Kind; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'journal', label: '日记' },
  { key: 'thought', label: '闪念' },
  { key: 'expense', label: '记账' },
  { key: 'todo', label: '待办' },
];

/** 时间线：所有记录按天倒序排开。这里是「看得见自己」的地方。 */
export default function TimelineView({ entries, refresh, notify }: ViewProps) {
  const [filter, setFilter] = useState<'all' | Kind>('all');
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState<Entry | null>(null);

  async function remove(entry: Entry) {
    try {
      await api.remove(entry.id);
      await refresh();
      notify('已删除');
    } catch (error) {
      notify(error instanceof Error ? error.message : '删除失败');
    }
  }

  const groups = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    const filtered = entries.filter((entry) => {
      if (filter !== 'all' && entry.kind !== filter) return false;
      if (!keyword) return true;
      return (
        entry.content.toLowerCase().includes(keyword) || entry.tags.some((tag) => tag.toLowerCase().includes(keyword))
      );
    });

    const map = new Map<string, Entry[]>();
    for (const entry of filtered) {
      const key = toDayKey(entry.occurredAt);
      const list = map.get(key);
      if (list) list.push(entry);
      else map.set(key, [entry]);
    }
    return [...map.entries()];
  }, [entries, filter, query]);

  return (
    <div>
      <div className="timeline-tools">
        <div className="chip-row">
          {FILTERS.map((item) => (
            <button
              key={item.key}
              className={`chip${filter === item.key ? ' active' : ''}`}
              onClick={() => setFilter(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="search">
          <IconSearch size={16} />
          <input
            value={query}
            placeholder="搜索内容或标签…"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </div>

      {groups.length === 0 ? (
        <div className="empty" style={{ marginTop: 26 }}>
          {query || filter !== 'all' ? '没有匹配的记录' : '还没有任何记录'}
        </div>
      ) : (
        groups.map(([day, list]) => {
          const spent = list.reduce((sum, entry) => sum + (entry.kind === 'expense' ? (entry.amount ?? 0) : 0), 0);
          return (
            <section className="day-group" key={day}>
              <div className="day-head">
                <h2 className="day-title">{humanDay(list[0]?.occurredAt ?? day)}</h2>
                <span className="day-sum">
                  {list.length} 条{spent > 0 ? ` · ¥${spent.toFixed(spent % 1 === 0 ? 0 : 2)}` : ''}
                </span>
              </div>
              {list.map((entry) => (
                <EntryItem
                  key={entry.id}
                  entry={entry}
                  onEdit={setEditing}
                  onDelete={(item) => void remove(item)}
                />
              ))}
            </section>
          );
        })
      )}

      {editing && (
        <EntryEditor
          entry={editing}
          onClose={() => setEditing(null)}
          onSaved={refresh}
          notify={notify}
        />
      )}
    </div>
  );
}
