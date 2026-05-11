export type Role = 'user' | 'assistant';

export interface Message {
  id: string;
  role: Role;
  content: string;
  sources: string[];
  createdAt: number;
}

export type ChatStatus = 'idle' | 'connecting' | 'sending' | 'error';

export type ApiError =
  | { kind: 'network'; message: string }
  | { kind: 'http'; status: number; message: string };
