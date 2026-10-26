// Pure state transitions for the chat widget. Kept out of useChat so the
// history invariant below can be tested without a React harness.
//
// `turns` is what the widget shows; `history` is what is sent back to the LLM.
// They are deliberately separate: an error is shown to the user as a turn but
// must never enter `history`, or the next request would hand the model a
// "The assistant is temporarily unavailable" line as if it had said it.
// `history` is only ever replaced by the server's copy on a successful reply.

import type { ChatMessage } from '@/services/chat.service';

export interface Turn {
  role: 'user' | 'assistant';
  content: string;
  error?: boolean;
}

export interface ChatState {
  turns: Turn[];
  history: ChatMessage[];
}

export const initialChatState: ChatState = { turns: [], history: [] };

// Matches UNAVAILABLE_MESSAGE in backend/app/api/chat.py, for failures that
// never reach the backend (offline, backend down) and so carry no detail.
export const FALLBACK_ERROR = 'The assistant is temporarily unavailable, please try again.';

export function withUserTurn(state: ChatState, message: string): ChatState {
  return { ...state, turns: [...state.turns, { role: 'user', content: message }] };
}

export function withReply(state: ChatState, reply: string, history: ChatMessage[]): ChatState {
  return { turns: [...state.turns, { role: 'assistant', content: reply }], history };
}

// The user's message stays in `turns` so their question doesn't vanish;
// `history` is untouched.
export function withError(state: ChatState, message: string): ChatState {
  return {
    ...state,
    turns: [...state.turns, { role: 'assistant', content: message, error: true }],
  };
}

export function requestBody(state: ChatState, message: string) {
  return { message, history: state.history };
}

export function errorMessageFrom(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' && detail ? detail : FALLBACK_ERROR;
}
