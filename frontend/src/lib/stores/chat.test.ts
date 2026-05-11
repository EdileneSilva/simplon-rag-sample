import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'svelte';
import { createChatStore, STORAGE_KEY } from './chat.svelte';

const BASE = 'http://api.test';

function mockOnce(body: unknown, status = 200) {
  return vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(body), { status }));
}

beforeEach(() => {
  localStorage.clear();
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-05-11T12:00:00Z'));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('createChatStore', () => {
  it('init() creates a conversation and sets status to idle', async () => {
    vi.stubGlobal('fetch', mockOnce({ conversation_id: 'c-1' }));
    const chat = createChatStore(BASE);

    await chat.init();
    flushSync();

    expect(chat.conversationId).toBe('c-1');
    expect(chat.status).toBe('idle');
    expect(chat.messages).toEqual([]);
  });

  it('init() recovers state from localStorage without hitting the API', async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        conversationId: 'persisted',
        messages: [
          { id: 'm1', role: 'user', content: 'hi', sources: [], createdAt: 1 },
          { id: 'm2', role: 'assistant', content: 'hello', sources: ['s1'], createdAt: 2 }
        ]
      })
    );
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const chat = createChatStore(BASE);
    await chat.init();
    flushSync();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(chat.conversationId).toBe('persisted');
    expect(chat.messages).toHaveLength(2);
  });

  it('send() appends user then assistant message on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ conversation_id: 'c-1' })))
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ content: 'Bonjour', sources: ['s1'] }))
        )
    );

    const chat = createChatStore(BASE);
    await chat.init();
    await chat.send('Salut');
    flushSync();

    expect(chat.messages.map((m) => m.role)).toEqual(['user', 'assistant']);
    expect(chat.messages[1].content).toBe('Bonjour');
    expect(chat.messages[1].sources).toEqual(['s1']);
    expect(chat.status).toBe('idle');
  });

  it('send() sets status=error and keeps the user message on HTTP error', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ conversation_id: 'c-1' })))
        .mockResolvedValueOnce(new Response('boom', { status: 500 }))
    );

    const chat = createChatStore(BASE);
    await chat.init();
    await chat.send('Salut');
    flushSync();

    expect(chat.status).toBe('error');
    expect(chat.error?.kind).toBe('http');
    expect(chat.messages).toHaveLength(1);
    expect(chat.messages[0].role).toBe('user');
  });

  it('reset() clears messages, drops storage, and creates a new conversation', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ conversation_id: 'c-1' })))
        .mockResolvedValueOnce(new Response(JSON.stringify({ conversation_id: 'c-2' })))
    );

    const chat = createChatStore(BASE);
    await chat.init();
    chat.messages.push({
      id: 'm1',
      role: 'user',
      content: 'old',
      sources: [],
      createdAt: 1
    });
    await chat.reset();
    flushSync();

    expect(chat.conversationId).toBe('c-2');
    expect(chat.messages).toEqual([]);
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
