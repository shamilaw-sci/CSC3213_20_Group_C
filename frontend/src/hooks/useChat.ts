import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ChatService } from '@/services/chat.service';
import {
  initialChatState, withUserTurn, withReply, withError, requestBody, errorMessageFrom,
  type ChatState,
} from '@/lib/chat-state';

export type { Turn } from '@/lib/chat-state';

export function useChat() {
  const [state, setState] = useState<ChatState>(initialChatState);

  const mutation = useMutation({
    mutationFn: (message: string) => {
      const body = requestBody(state, message);
      return ChatService.send(body.message, body.history);
    },
    onSuccess: (data) => {
      setState((s) => withReply(s, data.reply, data.history));
    },
    // Shown inline rather than as a toast: the toast vanished in seconds and
    // the old handler also deleted the user's message, so a failure looked
    // like nothing had happened at all.
    onError: (error) => {
      setState((s) => withError(s, errorMessageFrom(error)));
    },
  });

  const send = (message: string) => {
    setState((s) => withUserTurn(s, message));
    mutation.mutate(message);
  };

  const reset = () => setState(initialChatState);

  return { turns: state.turns, send, reset, isPending: mutation.isPending };
}
