import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api.ts';

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function mockFetch(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('review chat API client', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('lists sessions with encoded query parameters', async () => {
    const fetchMock = mockFetch(jsonResponse({ items: [], nextCursor: null }));

    await api.chatList({ scope: 'all', limit: 20, cursor: 'a|b' });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('/api/review-chats?');
    expect(url).toContain('scope=all');
    expect(url).toContain('limit=20');
    expect(url).toContain('cursor=a%7Cb');
  });

  it('loads the current period session', async () => {
    const fetchMock = mockFetch(jsonResponse({ session: null, messages: [] }));

    await api.chatCurrent('weekly');

    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/review-chats/current?scope=weekly');
  });

  it('loads a history session with message paging', async () => {
    const fetchMock = mockFetch(jsonResponse({ session: null, messages: [] }));

    await api.chatSession('chat-1', { beforeSequence: 12, limit: 100 });

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('/api/review-chats/chat-1?');
    expect(url).toContain('beforeSequence=12');
    expect(url).toContain('limit=100');
  });

  it('sends a current-period message with scope only', async () => {
    const fetchMock = mockFetch(jsonResponse({ session: {}, messages: [] }));

    await api.sendChat({ scope: 'daily', message: '你好' });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('/api/review-chats/messages');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ scope: 'daily', message: '你好' });
  });

  it('sends a history message with sessionId only', async () => {
    const fetchMock = mockFetch(jsonResponse({ session: {}, messages: [] }));

    await api.sendChat({ sessionId: 'chat-1', message: '续聊' });

    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body).toEqual({ sessionId: 'chat-1', message: '续聊' });
  });

  it('deletes a session and tolerates 204', async () => {
    const fetchMock = mockFetch(new Response(null, { status: 204 }));

    await expect(api.deleteChat('chat-1')).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE');
  });

  it('maps API errors to Error messages', async () => {
    mockFetch(jsonResponse({ error: '参数不合法', detail: 'cursor 不合法' }, 400));

    await expect(api.chatList({ scope: 'all', cursor: 'bad' })).rejects.toThrow('cursor 不合法');
  });
});
