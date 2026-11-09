import { useEffect, useState } from 'react';
import type { Entry, Kind } from '../../../shared/schema.ts';
import { CATEGORIES, KINDS, KIND_LABEL } from '../../../shared/schema.ts';
import { api, type EntryInput } from '../api.ts';
import type { Notify } from './types.ts';
import { IconClose } from './Icons.tsx';

interface Props {
  entry: Entry;
  onClose: () => void;
  onSaved: () => Promise<void>;
  notify: Notify;
}

/** 编辑弹窗。刻意只放「规则猜不准、必须人来改」的字段，不做大而全的表单。 */
export default function EntryEditor({ entry, onClose, onSaved, notify }: Props) {
  const [kind, setKind] = useState<Kind>(entry.kind);
  const [content, setContent] = useState(entry.content);
  const [amount, setAmount] = useState(entry.amount === null ? '' : String(entry.amount));
  const [category, setCategory] = useState(entry.category ?? '其他');
  const [mood, setMood] = useState(entry.mood === null ? '' : String(entry.mood));
  const [tags, setTags] = useState(entry.tags.join(', '));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function save() {
    if (!content.trim() || saving) return;
    setSaving(true);
    try {
      const patch: Partial<EntryInput> = {
        kind,
        content: content.trim(),
        tags: tags
          .split(/[,，\s]+/)
          .map((t) => t.replace(/^#/, '').trim())
          .filter(Boolean)
          .slice(0, 20),
        mood: mood ? Number(mood) : null,
        amount: kind === 'expense' && amount ? Number(amount) : null,
        category: kind === 'expense' ? category : null,
        status: kind === 'todo' ? (entry.status ?? 'open') : null,
      };
      await api.update(entry.id, patch);
      await onSaved();
      notify('已保存');
      onClose();
    } catch (error) {
      notify(error instanceof Error ? error.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="编辑记录">
        <div className="modal-head">
          <h2>编辑记录</h2>
          <button className="icon-btn" onClick={onClose} aria-label="关闭">
            <IconClose size={16} />
          </button>
        </div>

        <div className="modal-body">
          <div className="field">
            <label htmlFor="edit-kind">类型</label>
            <select id="edit-kind" className="select" value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABEL[k]}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="edit-content">内容</label>
            <textarea
              id="edit-content"
              className="textarea"
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
          </div>

          {kind === 'expense' && (
            <div className="field-row">
              <div className="field">
                <label htmlFor="edit-amount">金额</label>
                <input
                  id="edit-amount"
                  className="input"
                  type="number"
                  step="0.01"
                  min="0"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-category">分类</label>
                <select id="edit-category" className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          <div className="field-row">
            <div className="field">
              <label htmlFor="edit-mood">心情（1-5，可空）</label>
              <input
                id="edit-mood"
                className="input"
                type="number"
                min="1"
                max="5"
                value={mood}
                onChange={(e) => setMood(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="edit-tags">标签（逗号分隔）</label>
              <input id="edit-tags" className="input" value={tags} onChange={(e) => setTags(e.target.value)} />
            </div>
          </div>
        </div>

        <div className="modal-foot">
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            取消
          </button>
          <button className="btn btn-primary btn-sm" onClick={save} disabled={saving || !content.trim()}>
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
}
