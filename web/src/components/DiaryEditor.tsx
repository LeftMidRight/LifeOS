import { useEffect, useRef, useState } from 'react';

interface Props {
  dayKey: string;
  /** 已有的日记内容；为空表示新写 */
  initial: string;
  dayLabel: string;
  onClose: () => void;
  onSave: (text: string) => Promise<void>;
}

/**
 * 全屏日记编辑器。
 *
 * 三个刻意的选择：
 *  1. 铺满视口、没有侧边栏和标签栏 —— 写东西的时候不该看见导航；
 *  2. 衬线字、行高 2.0、每行 760px —— 长文阅读的舒适区，不是表单的密度；
 *  3. 草稿实时存 localStorage —— 没保存就关掉不会丢，重进自动恢复。
 */
export default function DiaryEditor({ dayKey, initial, dayLabel, onClose, onSave }: Props) {
  const draftKey = `lifeos:draft:${dayKey}`;

  const [text, setText] = useState(() => {
    try {
      return localStorage.getItem(draftKey) ?? initial;
    } catch {
      return initial;
    }
  });
  const [saving, setSaving] = useState(false);
  const [restored] = useState(() => {
    try {
      const draft = localStorage.getItem(draftKey);
      return Boolean(draft && draft !== initial);
    } catch {
      return false;
    }
  });
  const areaRef = useRef<HTMLTextAreaElement>(null);
  // 用 ref 保证 keydown 回调总是调用当前渲染的 save，避免保存旧的 text/saving。
  const saveRef = useRef<() => Promise<void>>(save);

  useEffect(() => {
    saveRef.current = save;
  });

  useEffect(() => {
    areaRef.current?.focus();
    areaRef.current?.setSelectionRange(text.length, text.length);
    // 只在挂载时聚焦一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    try {
      if (text.trim()) localStorage.setItem(draftKey, text);
      else localStorage.removeItem(draftKey);
    } catch {
      /* 隐私模式下 localStorage 可能不可用，不影响写作 */
    }
  }, [text, draftKey]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
        event.preventDefault();
        void saveRef.current();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function save() {
    const value = text.trim();
    if (!value || saving) return;
    setSaving(true);
    try {
      await onSave(value);
      try {
        localStorage.removeItem(draftKey);
      } catch {
        /* 忽略 */
      }
      onClose();
    } catch {
      // 保存失败由父级提示；编辑器保持打开，草稿还在，不会白写一场
    } finally {
      setSaving(false);
    }
  }

  const charCount = text.trim().length;

  return (
    <div className="editor-overlay" role="dialog" aria-modal="true" aria-label="写日记">
      <header className="editor-head">
        <div className="editor-date">
          <strong>{dayLabel}</strong>
          {restored && <span className="editor-restored">已恢复未保存的草稿</span>}
        </div>
        <div className="editor-actions">
          <span className="editor-count">{charCount} 字</span>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            关闭
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => void save()} disabled={saving || charCount === 0}>
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </header>

      <textarea
        ref={areaRef}
        className="editor-area"
        value={text}
        spellCheck={false}
        placeholder={'今天发生了什么？\n\n想到什么写什么，不用组织语言。'}
        onChange={(event) => setText(event.target.value)}
      />

      <footer className="editor-foot">Esc 退出 · ⌘ / Ctrl + Enter 保存 · 草稿自动保留在这台设备</footer>
    </div>
  );
}
