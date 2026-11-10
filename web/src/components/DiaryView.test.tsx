import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Entry } from '../../../shared/schema.ts';
import { api } from '../api.ts';
import DiaryView from './DiaryView.tsx';

vi.mock('../api.ts', () => ({
  api: { remove: vi.fn(), create: vi.fn(), update: vi.fn() },
}));

function makeDiary(overrides: Partial<Entry> = {}): Entry {
  const now = new Date().toISOString();
  return {
    id: 'diary-1',
    kind: 'journal',
    content: '今天的日记',
    title: null,
    occurredAt: now,
    createdAt: now,
    updatedAt: now,
    amount: null,
    currency: 'CNY',
    category: null,
    status: null,
    dueAt: null,
    mood: null,
    energy: null,
    tags: [],
    meta: {},
    source: 'manual',
    ...overrides,
  };
}

function renderDiary(entry: Entry = makeDiary()) {
  const refresh = vi.fn().mockResolvedValue(undefined);
  const notify = vi.fn();
  render(<DiaryView entries={[entry]} refresh={refresh} notify={notify} />);
  return { refresh, notify };
}

function deleteButton() {
  return screen.getByRole('button', { name: '删除' });
}

describe('DiaryView 删除确认', () => {
  beforeEach(() => {
    vi.mocked(api.remove).mockReset().mockResolvedValue(undefined);
  });

  it('点击删除只打开确认弹窗，不直接删除', async () => {
    const user = userEvent.setup();
    renderDiary();

    await user.click(deleteButton());

    expect(screen.getByRole('dialog', { name: /删除日记/ })).toBeVisible();
    expect(api.remove).not.toHaveBeenCalled();
  });

  it('取消后关闭弹窗且不删除', async () => {
    const user = userEvent.setup();
    renderDiary();

    await user.click(deleteButton());
    await user.click(screen.getByRole('button', { name: '取消' }));

    expect(screen.queryByRole('dialog', { name: /删除日记/ })).not.toBeInTheDocument();
    expect(api.remove).not.toHaveBeenCalled();
  });

  it('按 Escape 关闭弹窗且不删除', async () => {
    const user = userEvent.setup();
    renderDiary();

    await user.click(deleteButton());
    await user.keyboard('{Escape}');

    expect(screen.queryByRole('dialog', { name: /删除日记/ })).not.toBeInTheDocument();
    expect(api.remove).not.toHaveBeenCalled();
  });

  it('点击遮罩关闭弹窗且不删除', async () => {
    const user = userEvent.setup();
    renderDiary();

    await user.click(deleteButton());
    const dialog = screen.getByRole('dialog', { name: /删除日记/ });
    await user.click(dialog.parentElement as HTMLElement);

    expect(screen.queryByRole('dialog', { name: /删除日记/ })).not.toBeInTheDocument();
    expect(api.remove).not.toHaveBeenCalled();
  });

  it('点击弹窗内部不会误关', async () => {
    const user = userEvent.setup();
    renderDiary();

    await user.click(deleteButton());
    const dialog = screen.getByRole('dialog', { name: /删除日记/ });
    await user.click(within(dialog).getByText(/确定删除这篇日记/));

    expect(screen.getByRole('dialog', { name: /删除日记/ })).toBeVisible();
  });

  it('确认后只删除目标日记并刷新列表', async () => {
    const user = userEvent.setup();
    const { refresh, notify } = renderDiary();

    await user.click(deleteButton());
    const dialog = screen.getByRole('dialog', { name: /删除日记/ });
    await user.click(within(dialog).getByRole('button', { name: '删除' }));

    await waitFor(() => expect(api.remove).toHaveBeenCalledWith('diary-1'));
    expect(api.remove).toHaveBeenCalledTimes(1);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledWith('日记已删除');
    expect(screen.queryByRole('dialog', { name: /删除日记/ })).not.toBeInTheDocument();
  });

  it('删除请求进行中时按钮禁用，避免重复提交', async () => {
    const user = userEvent.setup();
    let resolveRemove: (value: void) => void = () => {};
    vi.mocked(api.remove).mockReturnValue(
      new Promise<void>((resolve) => {
        resolveRemove = resolve;
      }),
    );
    renderDiary();

    await user.click(deleteButton());
    const dialog = screen.getByRole('dialog', { name: /删除日记/ });
    await user.click(within(dialog).getByRole('button', { name: '删除' }));

    expect(within(dialog).getByRole('button', { name: '删除中…' })).toBeDisabled();
    resolveRemove();
    await waitFor(() => expect(screen.queryByRole('dialog', { name: /删除日记/ })).not.toBeInTheDocument());
  });

  it('删除失败时保留弹窗并显示错误', async () => {
    const user = userEvent.setup();
    vi.mocked(api.remove).mockRejectedValue(new Error('网络断了'));
    renderDiary();

    await user.click(deleteButton());
    const dialog = screen.getByRole('dialog', { name: /删除日记/ });
    await user.click(within(dialog).getByRole('button', { name: '删除' }));

    expect(await screen.findByText('网络断了')).toBeVisible();
    expect(screen.getByRole('dialog', { name: /删除日记/ })).toBeVisible();
  });
});
