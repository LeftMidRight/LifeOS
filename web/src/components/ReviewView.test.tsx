import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {
  ChatMessage,
  ChatPage,
  ChatSendResult,
  ChatSession,
  ChatView,
  InsightPreview,
  InsightResponse,
} from '../api.ts';
import { api } from '../api.ts';
import ReviewView from './ReviewView.tsx';

vi.mock('../api.ts', () => ({
  api: {
    insight: vi.fn(),
    insightPreview: vi.fn(),
    chatList: vi.fn(),
    chatCurrent: vi.fn(),
    chatSession: vi.fn(),
    sendChat: vi.fn(),
    deleteChat: vi.fn(),
  },
}));

const stats = {
  from: '2026-11-10T00:00:00.000Z',
  to: '2026-11-11T00:00:00.000Z',
  totalSpent: 0,
  byCategory: [],
  byKind: {},
  openTodos: 0,
  doneTodos: 0,
  avgMood: null,
  entryCount: 1,
};

const insight = {
  scope: 'daily' as const,
  from: stats.from,
  to: stats.to,
  headline: '今天还不错',
  summary: '今天写了一篇日记。',
  themes: [],
  spending: '没有记账',
  todos: '没有待办',
  mood: 'flat' as const,
  suggestion: '继续保持',
  model: 'deepseek-chat',
  generatedAt: stats.from,
};

function insightResponse(): InsightResponse {
  return { insight, warning: null, stats };
}

function makePreview(overrides: Partial<InsightPreview> = {}): InsightPreview {
  return {
    scope: 'daily',
    from: stats.from,
    to: stats.to,
    stats,
    payload: { scope: 'daily', entries: [{ text: '今天的日记' }] },
    payloadText: '{\n  "scope": "daily"\n}',
    insight,
    entryCount: 1,
    ...overrides,
  };
}

function makeSession(id = 'chat-1', scope: 'daily' | 'weekly' = 'daily'): ChatSession {
  return {
    id,
    scope,
    periodStart: stats.from,
    periodEnd: stats.to,
    messageCount: 2,
    updatedAt: stats.from,
    createdAt: stats.from,
    latestSequence: 2,
  };
}

function makeMessage(sequence: number, role: 'user' | 'assistant', content: string): ChatMessage {
  return {
    id: `m-${sequence}`,
    sessionId: 'chat-1',
    sequence,
    role,
    content,
    createdAt: stats.from,
  };
}

function makeView(overrides: Partial<ChatView> = {}): ChatView {
  return {
    session: makeSession(),
    messages: [makeMessage(1, 'user', '我想聊聊今天'), makeMessage(2, 'assistant', '今天感觉如何？')],
    hasMore: false,
    beforeSequence: null,
    insight,
    stats,
    ...overrides,
  };
}

function mockBase() {
  vi.mocked(api.insight).mockResolvedValue(insightResponse());
  vi.mocked(api.insightPreview).mockResolvedValue(makePreview());
  vi.mocked(api.chatList).mockResolvedValue({ items: [], nextCursor: null });
  vi.mocked(api.chatCurrent).mockResolvedValue(makeView());
  vi.mocked(api.chatSession).mockResolvedValue(makeView());
  vi.mocked(api.sendChat).mockResolvedValue({
    session: makeSession(),
    messages: [makeMessage(3, 'user', '新问题'), makeMessage(4, 'assistant', '新回答')],
  });
  vi.mocked(api.deleteChat).mockResolvedValue(undefined);
}

function renderReview(llmConfigured = true) {
  render(<ReviewView llmConfigured={llmConfigured} />);
}

describe('ReviewView 回顾聊天', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockBase();
  });

  it('加载当前周期的摘要和聊天', async () => {
    renderReview();

    expect(await screen.findByText('今天还不错')).toBeVisible();
    expect(screen.getByText('今天感觉如何？')).toBeVisible();
    await waitFor(() => expect(api.insightPreview).toHaveBeenCalledWith('daily'));
    expect(api.insight).not.toHaveBeenCalled();
    expect(api.chatCurrent).toHaveBeenCalledWith('daily');
  });

  it('切换到本周时重新加载且不混杂今天的消息', async () => {
    vi.mocked(api.chatCurrent).mockImplementation(async (scope) =>
      scope === 'weekly'
        ? makeView({
            session: makeSession('weekly-1', 'weekly'),
            messages: [makeMessage(1, 'assistant', '这是本周的消息')],
          })
        : makeView(),
    );
    const user = userEvent.setup();
    renderReview();
    await screen.findByText('今天感觉如何？');

    await user.click(screen.getByRole('button', { name: '本周' }));

    expect(await screen.findByText('这是本周的消息')).toBeVisible();
    expect(screen.queryByText('今天感觉如何？')).not.toBeInTheDocument();
    expect(api.chatCurrent).toHaveBeenLastCalledWith('weekly');
    expect(api.insightPreview).toHaveBeenLastCalledWith('weekly');
    expect(api.insight).not.toHaveBeenCalled();
  });

  it('选择历史会话后展示历史摘要与消息，不重新生成摘要', async () => {
    vi.mocked(api.chatList).mockResolvedValue({
      items: [
        {
          id: 'old-chat',
          scope: 'daily',
          periodStart: '2026-11-01T00:00:00.000Z',
          periodEnd: '2026-11-02T00:00:00.000Z',
          messageCount: 2,
          updatedAt: '2026-11-01T12:00:00.000Z',
        },
      ],
      nextCursor: null,
    });
    vi.mocked(api.chatSession).mockResolvedValue(
      makeView({
        session: makeSession('old-chat'),
        messages: [makeMessage(1, 'assistant', '旧会话里的回答')],
        insight: { ...insight, headline: '旧周期的回顾' },
      }),
    );
    const user = userEvent.setup();
    renderReview();
    await screen.findByText('今天还不错');

    const history = await screen.findByRole('region', { name: '历史回顾' });
    await user.click(within(history).getByRole('button', { name: /2026/ }));

    expect(await screen.findByText('旧会话里的回答')).toBeVisible();
    expect(screen.getByText('旧周期的回顾')).toBeVisible();
    expect(api.chatSession).toHaveBeenCalledWith('old-chat', expect.anything());
    // 历史会话只读快照，不触发生成（预览也不算生成）。
    expect(api.insight).not.toHaveBeenCalled();
  });

  it('加载更早消息时把结果插到列表前面', async () => {
    vi.mocked(api.chatCurrent).mockResolvedValue(
      makeView({ hasMore: true, beforeSequence: 3 })
    );
    vi.mocked(api.chatSession).mockResolvedValue(
      makeView({
        messages: [{ ...makeMessage(0, 'user', '更早的问题'), id: 'm-older' }],
        hasMore: false,
        beforeSequence: null,
      })
    );
    const user = userEvent.setup();
    renderReview();
    await screen.findByText('今天感觉如何？');

    await user.click(screen.getByRole('button', { name: '加载更早消息' }));

    expect(await screen.findByText('更早的问题')).toBeVisible();
    expect(api.chatSession).toHaveBeenCalledWith('chat-1', { beforeSequence: 3, limit: 100 });
    const messages = screen.getAllByTestId('chat-message');
    expect(within(messages[0]).getByText('更早的问题')).toBeVisible();
  });

  it('Enter 发送当前周期消息并清空输入', async () => {
    const user = userEvent.setup();
    renderReview();
    const input = await screen.findByRole('textbox', { name: '聊天输入' });
    await user.type(input, '新问题{Enter}');

    await waitFor(() =>
      expect(api.sendChat).toHaveBeenCalledWith({ scope: 'daily', message: '新问题' })
    );
    expect(await screen.findByText('新回答')).toBeVisible();
    expect(input).toHaveValue('');
  });

  it('Shift+Enter 只换行，不发送', async () => {
    const user = userEvent.setup();
    renderReview();
    const input = await screen.findByRole('textbox', { name: '聊天输入' });

    await user.type(input, '第一行{Shift>}{Enter}{/Shift}第二行');

    expect(api.sendChat).not.toHaveBeenCalled();
    expect(input).toHaveValue('第一行\n第二行');
  });

  it('发送失败时保留输入并显示错误', async () => {
    vi.mocked(api.sendChat).mockRejectedValue(new Error('模型服务暂时不可用'));
    const user = userEvent.setup();
    renderReview();
    const input = await screen.findByRole('textbox', { name: '聊天输入' });

    await user.type(input, '会失败的问题{Enter}');

    expect(await screen.findByText('模型服务暂时不可用')).toBeVisible();
    expect(input).toHaveValue('会失败的问题');
    expect(screen.queryByText('新回答')).not.toBeInTheDocument();
  });

  it('删除历史会话需要确认，取消不会删除', async () => {
    vi.mocked(api.chatList).mockResolvedValue({
      items: [
        {
          id: 'old-chat',
          scope: 'daily',
          periodStart: '2026-11-01T00:00:00.000Z',
          periodEnd: '2026-11-02T00:00:00.000Z',
          messageCount: 2,
          updatedAt: '2026-11-01T12:00:00.000Z',
        },
      ],
      nextCursor: null,
    });
    const user = userEvent.setup();
    renderReview();
    const history = await screen.findByRole('region', { name: '历史回顾' });

    await user.click(within(history).getByRole('button', { name: '删除会话' }));
    expect(screen.getByRole('dialog', { name: /删除这段回顾对话/ })).toBeVisible();
    await user.click(screen.getByRole('button', { name: '取消' }));

    expect(api.deleteChat).not.toHaveBeenCalled();
  });

  it('未配置模型时禁用发送但允许浏览历史', async () => {
    renderReview(false);

    expect(await screen.findByRole('textbox', { name: '聊天输入' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重新生成' })).toBeDisabled();
    expect(screen.getByText('查看发送内容')).toBeVisible();
    expect(screen.getByText(/未配置模型/)).toBeVisible();
    expect(screen.getByRole('region', { name: '历史回顾' })).toBeVisible();
  });

  it('展示聊天数据会发送到模型服务的提示', async () => {
    renderReview();
    expect(
      await screen.findByText(/聊天会把本周期的记录和对话发送到已配置的模型服务/)
    ).toBeVisible();
  });

  it('点击发送给大模型才生成回顾', async () => {
    vi.mocked(api.insightPreview).mockResolvedValue(makePreview({ insight: null }));
    vi.mocked(api.insight).mockResolvedValue({
      insight: { ...insight, headline: '新生成的回顾' },
      warning: null,
      stats,
    });
    const user = userEvent.setup();
    renderReview();

    expect(await screen.findByText(/还没有生成过回顾/)).toBeVisible();
    expect(api.insight).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: '发送给大模型生成回顾' }));

    expect(await screen.findByText('新生成的回顾')).toBeVisible();
    expect(api.insight).toHaveBeenCalledWith('daily');
  });

  it('可以查看将发送给模型的内容', async () => {
    renderReview();

    const summary = await screen.findByText('查看发送内容');
    expect(summary).toBeVisible();
    expect(summary.closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText(/将发送 1 条记录/)).toBeInTheDocument();
    expect(screen.getByText(/"scope": "daily"/)).toBeInTheDocument();
  });

  it('历史列表按浏览器本地日期显示周期', async () => {
    // 本地 2026-11-10 0 点；在 UTC+8 下其 UTC 日期是 11-09。
    const localMidnight = new Date(2026, 10, 10).toISOString();
    vi.mocked(api.chatList).mockResolvedValue({
      items: [
        {
          id: 'local-date-chat',
          scope: 'daily',
          periodStart: localMidnight,
          periodEnd: localMidnight,
          messageCount: 2,
          updatedAt: localMidnight,
        },
      ],
      nextCursor: null,
    });
    renderReview();

    const history = await screen.findByRole('region', { name: '历史回顾' });
    expect(within(history).getByRole('button', { name: /2026-11-10/ })).toBeVisible();
  });

  it('发送响应迟到时，如果已切换周期则丢弃', async () => {
    let resolveSend!: (value: ChatSendResult) => void;
    vi.mocked(api.sendChat).mockReturnValue(
      new Promise<ChatSendResult>((resolve) => {
        resolveSend = resolve;
      })
    );
    vi.mocked(api.chatCurrent).mockImplementation(async (scope) =>
      scope === 'weekly'
        ? makeView({
            session: makeSession('weekly-1', 'weekly'),
            messages: [makeMessage(1, 'assistant', '本周视图')],
          })
        : makeView()
    );
    const user = userEvent.setup();
    renderReview();
    await screen.findByText('今天感觉如何？');
    await user.type(screen.getByRole('textbox', { name: '聊天输入' }), '旧周期的消息{Enter}');
    await waitFor(() => expect(api.sendChat).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole('button', { name: '本周' }));
    await screen.findByText('本周视图');
    await act(async () => {
      resolveSend({
        session: makeSession(),
        messages: [makeMessage(3, 'user', '旧周期的消息'), makeMessage(4, 'assistant', '迟到的回答')],
      });
    });

    expect(screen.queryByText('迟到的回答')).not.toBeInTheDocument();
    expect(screen.getByText('本周视图')).toBeVisible();
  });

  it('加载更早消息迟到时，如果已切换周期则丢弃', async () => {
    vi.mocked(api.chatCurrent).mockImplementation(async (scope) =>
      scope === 'weekly'
        ? makeView({
            session: makeSession('weekly-1', 'weekly'),
            messages: [makeMessage(1, 'assistant', '本周视图')],
          })
        : makeView({ hasMore: true, beforeSequence: 3 })
    );
    let resolveEarlier!: (value: ChatView) => void;
    vi.mocked(api.chatSession).mockReturnValue(
      new Promise<ChatView>((resolve) => {
        resolveEarlier = resolve;
      })
    );
    const user = userEvent.setup();
    renderReview();
    await screen.findByText('今天感觉如何？');
    await user.click(screen.getByRole('button', { name: '加载更早消息' }));

    await user.click(screen.getByRole('button', { name: '本周' }));
    await screen.findByText('本周视图');
    await act(async () => {
      resolveEarlier(
        makeView({
          messages: [{ ...makeMessage(0, 'user', '更早的问题'), id: 'm-older' }],
          hasMore: false,
          beforeSequence: null,
        })
      );
    });

    expect(screen.queryByText('更早的问题')).not.toBeInTheDocument();
    expect(screen.getByText('本周视图')).toBeVisible();
  });

  it('历史筛选结果迟到时，不会覆盖更新的筛选', async () => {
    let resolveAll!: (value: ChatPage) => void;
    vi.mocked(api.chatList).mockImplementation((params = {}) =>
      params.scope === 'all'
        ? new Promise<ChatPage>((resolve) => {
            resolveAll = resolve;
          })
        : Promise.resolve({ items: [], nextCursor: null })
    );
    const user = userEvent.setup();
    renderReview();
    const history = await screen.findByRole('region', { name: '历史回顾' });
    await user.click(within(history).getByRole('button', { name: '日回顾' }));
    await waitFor(() => expect(api.chatList).toHaveBeenLastCalledWith({ scope: 'daily', limit: 20 }));

    await act(async () => {
      resolveAll({
        items: [
          {
            id: 'stale-chat',
            scope: 'weekly',
            periodStart: '2026-11-01T00:00:00.000Z',
            periodEnd: '2026-11-02T00:00:00.000Z',
            messageCount: 2,
            updatedAt: '2026-11-01T12:00:00.000Z',
          },
        ],
        nextCursor: null,
      });
    });

    expect(screen.queryByText(/2026-11-01/)).not.toBeInTheDocument();
  });
});
