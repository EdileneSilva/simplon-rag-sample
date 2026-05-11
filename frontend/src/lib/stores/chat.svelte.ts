import { ApiClientError, createConversation, sendMessage } from '../api/client';
import type { ApiError, ChatStatus, Message } from '../types';

export const STORAGE_KEY = 'rag-chat:v1';

interface PersistedState {
  conversationId: string | null;
  messages: Message[];
}

function loadFromStorage(): PersistedState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedState;
    if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.messages)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveToStorage(state: PersistedState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Quota / serialization issues are non-fatal.
  }
}

function clearStorage(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

function toApiError(err: unknown): ApiError {
  if (err instanceof ApiClientError) {
    return err.kind === 'http'
      ? { kind: 'http', status: err.status ?? 0, message: err.message }
      : { kind: 'network', message: err.message };
  }
  return { kind: 'network', message: 'Unknown error' };
}

export function createChatStore(baseUrl: string) {
  let conversationId = $state<string | null>(null);
  let messages = $state<Message[]>([]);
  let status = $state<ChatStatus>('idle');
  let error = $state<ApiError | null>(null);
  // Non-reactive guard: when true, the next persistence effect run is
  // skipped without breaking the dependency tracking. Used by reset() so
  // that the freshly created conversation isn't persisted immediately.
  let skipNextSave = false;

  $effect.root(() => {
    $effect(() => {
      // Read reactive deps unconditionally so the effect re-runs on any change.
      const cid = conversationId;
      const msgs = messages;
      if (skipNextSave) {
        skipNextSave = false;
        return;
      }
      if (cid !== null) {
        saveToStorage({ conversationId: cid, messages: msgs });
      }
    });
  });

  async function init() {
    const persisted = loadFromStorage();
    if (persisted && persisted.conversationId) {
      conversationId = persisted.conversationId;
      messages = persisted.messages;
      status = 'idle';
      return;
    }
    status = 'connecting';
    error = null;
    try {
      conversationId = await createConversation(baseUrl);
      status = 'idle';
    } catch (err) {
      error = toApiError(err);
      status = 'error';
    }
  }

  async function send(content: string) {
    if (!conversationId) return;
    const trimmed = content.trim();
    if (!trimmed) return;

    messages.push({
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      sources: [],
      createdAt: Date.now()
    });
    status = 'sending';
    error = null;

    try {
      const response = await sendMessage(baseUrl, conversationId, trimmed);
      messages.push({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: response.content || 'Aucune réponse reçue.',
        sources: response.sources,
        createdAt: Date.now()
      });
      status = 'idle';
    } catch (err) {
      error = toApiError(err);
      status = 'error';
    }
  }

  async function reset() {
    clearStorage();
    messages = [];
    conversationId = null;
    error = null;
    status = 'connecting';
    try {
      conversationId = await createConversation(baseUrl);
      // Tell the persistence effect to skip its next run so that the
      // freshly created (empty) conversation does not re-populate storage.
      skipNextSave = true;
      status = 'idle';
    } catch (err) {
      error = toApiError(err);
      status = 'error';
    }
  }

  return {
    get conversationId() {
      return conversationId;
    },
    get messages() {
      return messages;
    },
    get status() {
      return status;
    },
    get error() {
      return error;
    },
    init,
    send,
    reset
  };
}
