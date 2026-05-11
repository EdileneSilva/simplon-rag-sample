import type { ApiError } from '../types';

export class ApiClientError extends Error {
  readonly kind: ApiError['kind'];
  readonly status?: number;

  constructor(error: ApiError) {
    super(error.message);
    this.name = 'ApiClientError';
    this.kind = error.kind;
    if (error.kind === 'http') this.status = error.status;
  }
}

async function call<T>(input: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(input, init);
  } catch (err) {
    throw new ApiClientError({
      kind: 'network',
      message: err instanceof Error ? err.message : 'Network error'
    });
  }
  if (!response.ok) {
    throw new ApiClientError({
      kind: 'http',
      status: response.status,
      message: `HTTP ${response.status}`
    });
  }
  return (await response.json()) as T;
}

export async function createConversation(baseUrl: string): Promise<string> {
  const data = await call<{ conversation_id: string }>(`${baseUrl}/api/v1/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  });
  return data.conversation_id;
}

export async function sendMessage(
  baseUrl: string,
  conversationId: string,
  content: string
): Promise<{ content: string; sources: string[] }> {
  const data = await call<{ content?: string; sources?: string[] }>(
    `${baseUrl}/api/v1/conversations/${conversationId}/messages`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content })
    }
  );
  return {
    content: data.content ?? '',
    sources: data.sources ?? []
  };
}
