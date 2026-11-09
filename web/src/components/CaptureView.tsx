import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { parseCapture } from '../../../shared/capture.ts';
import type { Kind } from '../../../shared/schema.ts';
import { KIND_LABEL } from '../../../shared/schema.ts';
import { humanDay, toDayKey } from '../../../shared/date.ts';
import { api } from '../api.ts';
import EntryItem from './EntryItem.tsx';
import { PRIMARY_KINDS, type ViewProps } from './types.ts';

const EXAMPLES = ['午饭 32 元', '记得明天交房租', '今天有点累，但还不错', '打车 48 #通勤'];

/**
 * 快速捕捉。
 * 整个产品的入口就这一个框：不选类型、不选分类，打完字直接回车。
 * 类型是「猜」出来的，而且猜错了能一键改正 —— 这才是低于 5 秒的记录体验。
 */
export default function CaptureView({ entries, refresh, notify }: ViewProps) {
  const [text, setText] = useState('');
  const [kindOverride, setKindOverride] = useState<Kind | null>(null);
  const [amountOverride, setAmountOverride] = useState('');
  const [showFix, setShowFix] = useState(false);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const parsed = useMemo(() => (text.trim() ? parseCapture(text, new Date()) : null), [text]);
  const effectiveKind = kindOverride ?? parsed?.kind ?? 'thought';

  useEffect(() => {
    setKindOverride(null);
    setAmountOverride('');
    setShowFix(false);
  }, [text]);

  const today = toDayKey(new Date());
  const todayEntries = entries.filter((entry) => toDayKey(entry.occurredAt) === today).slice(0, 8);
  const todaySpent = todayEntries.reduce((sum, entry) => sum + (entry.kind === 'expense' ? (entry.amount ?? 0) : 0), 0);

  async function submit() {
    const value = text.trim();
    if (!value || !parsed || busy) return;

    setBusy(true);
    try {
      const kind = effectiveKind;
      const amount = kind === 'expense' ? (amountOverride ? Number(amountOverride) : parsed.amount) : null;

      const created = await api.create({
        kind,
        content: parsed.content || value,
        occurredAt: new Date().toISOString(),
        amount,
        category: kind === 'expense' ? (parsed.category ?? '其他') : null,
        status: kind === 'todo' ? 'open' : null,
        dueAt: kind === 'todo' ? parsed.dueAt : null,
        tags: parsed.tags,
        source: 'capture',
        meta: { note: parsed.note, confidence: parsed.confidence },
      });

      setText('');
      inputRef.current?.focus();
      await refresh();

      const label = kind === 'expense' && amount !== null ? `${KIND_LABEL[kind]} ¥${amount}` : KIND_LABEL[kind];
      notify(`已记下 · ${label}`, {
        label: '撤销',
        run: async () => {
          await api.remove(created.id);
          await refresh();
        },
      });
    } catch (error) {
      notify(error instanceof Error ? error.message : '保存失败');
    } finally {
      setBusy(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      void submit();
    }
  }

  return (
    <div>
      <div className="capture-box">
        <textarea
          ref={inputRef}
          className="capture-input"
          value={text}
          autoFocus
          placeholder={'现在在想什么？\n花的钱、冒出的念头、要做的事，都写在这里'}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="capture-bar">
          <span className="hint">⌘ / Ctrl + Enter 记下</span>
          <button className="btn btn-primary" onClick={submit} disabled={!text.trim() || busy}>
            {busy ? '记下中…' : '记下'}
          </button>
        </div>
      </div>

      {!text && (
        <div className="chip-row" style={{ marginTop: 12 }}>
          <span className="muted" style={{ fontSize: 12.5 }}>
            试试：
          </span>
          {EXAMPLES.map((example) => (
            <button key={example} className="chip" onClick={() => setText(example)}>
              {example}
            </button>
          ))}
        </div>
      )}

      {parsed && (
        <div className="preview">
          <div className="chip-row">
            <button className={`kind-chip ${effectiveKind}`} onClick={() => setShowFix((value) => !value)}>
              <span className="badge-dot" />
              {KIND_LABEL[effectiveKind]}
            </button>

            {effectiveKind === 'expense' && (amountOverride || parsed.amount !== null) && (
              <span className="chip">¥{amountOverride || parsed.amount}</span>
            )}
            {effectiveKind === 'expense' && parsed.category && <span className="chip">{parsed.category}</span>}
            {effectiveKind === 'todo' && parsed.dueAt && <span className="chip">截止 {humanDay(parsed.dueAt)}</span>}
            {parsed.tags.map((tag) => (
              <span className="chip" key={tag}>
                #{tag}
              </span>
            ))}
            <button className="chip" onClick={() => setShowFix((value) => !value)}>
              {showFix ? '收起' : '改'}
            </button>
          </div>

          <p className="preview-note">{parsed.note}</p>
          {parsed.confidence < 0.7 && <p className="preview-warn">这条不太确定，建议确认一下类型</p>}

          {showFix && (
            <div className="fix-row">
              {PRIMARY_KINDS.map((kind) => (
                <button
                  key={kind}
                  className={`chip${effectiveKind === kind ? ' active' : ''}`}
                  onClick={() => setKindOverride(kind)}
                >
                  {KIND_LABEL[kind]}
                </button>
              ))}
              {effectiveKind === 'expense' && (
                <input
                  className="fix-input"
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="金额"
                  value={amountOverride}
                  onChange={(event) => setAmountOverride(event.target.value)}
                />
              )}
            </div>
          )}
        </div>
      )}

      <div className="today-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          今天
        </h2>
        <span className="day-sum">
          {todayEntries.length} 条
          {todaySpent > 0 ? ` · 花了 ¥${todaySpent.toFixed(todaySpent % 1 === 0 ? 0 : 2)}` : ''}
        </span>
      </div>

      {todayEntries.length === 0 ? (
        <div className="empty">
          今天还没有记录。
          <br />
          上面那个框，想到什么就写什么。
        </div>
      ) : (
        <div>
          {todayEntries.map((entry) => (
            <EntryItem key={entry.id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  );
}
