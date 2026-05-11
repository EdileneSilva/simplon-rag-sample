import { afterEach, describe, expect, it, vi } from 'vitest';
import { createConversation, sendMessage, ApiClientError } from './client';

const BASE = 'http://api.test';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('createConversation', () => {
  it('returns the conversation id on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ conversation_id: 'abc-123' }), { status: 200 })
      )
    );

    const id = await createConversation(BASE);

    expect(id).toBe('abc-123');
    expect(fetch).toHaveBeenCalledWith(`${BASE}/api/v1/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
  });

  it('throws ApiClientError with kind=http on non-2xx', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('boom', { status: 500 })));
    await expect(createConversation(BASE)).rejects.toMatchObject({ kind: 'http', status: 500 });
  });

  it('throws ApiClientError with kind=network when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(createConversation(BASE)).rejects.toMatchObject({ kind: 'network' });
  });
});

describe('sendMessage', () => {
  it('posts JSON content and returns content + sources', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ content: 'Hello', sources: ['s1', 's2'] }), { status: 200 })
      )
    );

    const result = await sendMessage(BASE, 'conv-1', 'Hi');

    expect(result).toEqual({ content: 'Hello', sources: ['s1', 's2'] });
    expect(fetch).toHaveBeenCalledWith(`${BASE}/api/v1/conversations/conv-1/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: 'Hi' })
    });
  });

  it('defaults missing sources to an empty array', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ content: 'Hi' }), { status: 200 }))
    );
    const result = await sendMessage(BASE, 'c', 'q');
    expect(result.sources).toEqual([]);
  });
});

it('ApiClientError is an Error subclass', () => {
  const e = new ApiClientError({ kind: 'http', status: 404, message: 'x' });
  expect(e).toBeInstanceOf(Error);
  expect(e.kind).toBe('http');
});
