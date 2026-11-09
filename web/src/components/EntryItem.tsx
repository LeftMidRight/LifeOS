import type { Entry } from '../../../shared/schema.ts';
import { KIND_LABEL } from '../../../shared/schema.ts';
import { formatClock, formatMoney, humanDay } from '../../../shared/date.ts';
import { IconEdit, IconTrash } from './Icons.tsx';

interface Props {
  entry: Entry;
  onEdit?: (entry: Entry) => void;
  onDelete?: (entry: Entry) => void;
}

export default function EntryItem({ entry, onEdit, onDelete }: Props) {
  const isDone = entry.status === 'done';

  return (
    <article className={`entry${isDone ? ' done' : ''}`}>
      <div className="entry-time">{formatClock(entry.occurredAt)}</div>

      <div className="entry-body">
        <div className="entry-head">
          <span className={`kind-chip ${entry.kind}`}>
            <span className="badge-dot" />
            {KIND_LABEL[entry.kind]}
          </span>
          {entry.kind === 'todo' && entry.dueAt && (
            <span className="chip">{isDone ? '已完成' : humanDay(entry.dueAt)}</span>
          )}
        </div>

        <p className="entry-content">{entry.content}</p>

        <div className="entry-meta">
          {entry.kind === 'expense' && entry.amount !== null && (
            <span className="entry-amount">{formatMoney(entry.amount, entry.currency)}</span>
          )}
          {entry.kind === 'expense' && entry.category && <span>{entry.category}</span>}
          {entry.mood !== null && <span>心情 {entry.mood}/5</span>}
          {entry.tags.map((tag) => (
            <span className="tag" key={tag}>
              #{tag}
            </span>
          ))}
        </div>
      </div>

      <div className="entry-actions">
        {onEdit && (
          <button className="icon-btn" onClick={() => onEdit(entry)} aria-label="编辑">
            <IconEdit size={15} />
          </button>
        )}
        {onDelete && (
          <button className="icon-btn danger" onClick={() => onDelete(entry)} aria-label="删除">
            <IconTrash size={15} />
          </button>
        )}
      </div>
    </article>
  );
}
